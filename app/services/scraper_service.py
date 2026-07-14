from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import PipelineJob
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.answer_repository import AnswerRepository
from app.repositories.job_repository import JobRepository
from app.repositories.question_repository import QuestionRepository
from app.repositories.source_repository import SourceRepository
from app.services.stackexchange_client import StackExchangeClient, StackExchangeResult


class ScraperService:
    def __init__(
        self,
        db: Session,
        client: StackExchangeClient | None = None,
        settings: Settings | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.client = client or StackExchangeClient(self.settings)
        self.sources = SourceRepository(db)
        self.questions = QuestionRepository(db)
        self.answers = AnswerRepository(db)
        self.jobs = JobRepository(db)
        self.analytics = AnalyticsRepository(db)

    def scrape_source(
        self,
        source_id: int,
        *,
        job_type: str = "scrape_questions",
        stop_at_latest_seen: bool = False,
    ) -> tuple[PipelineJob, StackExchangeResult]:
        source = self.sources.get(source_id)
        if source is None:
            raise ValueError(f"Source {source_id} not found")

        job = self.jobs.start(job_type, source_id=source.id)
        self.db.commit()
        self.db.refresh(job)
        result = StackExchangeResult(items=[])

        try:
            latest_seen_at = (
                self.questions.latest_created_at_for_source(source.id)
                if stop_at_latest_seen
                else None
            )
            fetch_kwargs = {"created_after": latest_seen_at} if latest_seen_at is not None else {}
            result = self.client.fetch_questions(
                source.source_type,
                source.identifier,
                **fetch_kwargs,
            )
            job.questions_found = len(result.items)
            question_ids_for_answers: list[int] = []

            for item in result.items:
                try:
                    question, is_new = self.questions.upsert_from_api_item(source.id, item)
                    question_ids_for_answers.append(question.stackoverflow_question_id)
                    if is_new:
                        job.questions_new += 1
                    else:
                        job.questions_updated += 1
                except Exception:
                    job.items_failed += 1

            if source.include_answers and question_ids_for_answers:
                answers_result = self.client.fetch_answers(question_ids_for_answers)
                by_stack_id = {
                    question.stackoverflow_question_id: question.id
                    for question in self.questions.list(source_id=source.id, limit=1000)
                }
                for answer_item in answers_result.items:
                    question_id = by_stack_id.get(answer_item.get("question_id"))
                    if question_id is None:
                        job.items_failed += 1
                        continue
                    try:
                        self.answers.upsert_from_api_item(question_id, answer_item)
                    except Exception:
                        job.items_failed += 1

            now = datetime.utcnow()
            source.last_scraped = now
            self.analytics.refresh_source_cache(source.id, now=now)
            self.jobs.finish(job)
            self.db.commit()
            self.db.refresh(job)
            return job, result
        except Exception as exc:
            self.db.rollback()
            job = self.jobs.get(job.id) or job
            self.jobs.fail(job, exc, source_id=source.id)
            self.db.commit()
            self.db.refresh(job)
            return job, result

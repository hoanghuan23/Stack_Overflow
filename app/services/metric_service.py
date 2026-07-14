from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import PipelineJob, Question, SourceQuestion
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.job_repository import JobRepository
from app.repositories.question_repository import QuestionRepository
from app.services.stackexchange_client import StackExchangeClient, StackExchangeResult


class MetricService:
    def __init__(
        self,
        db: Session,
        client: StackExchangeClient | None = None,
        settings: Settings | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.client = client or StackExchangeClient(self.settings)
        self.questions = QuestionRepository(db)
        self.jobs = JobRepository(db)
        self.analytics = AnalyticsRepository(db)

    def run_due_updates(self, limit: int = 100) -> tuple[PipelineJob, int, StackExchangeResult]:
        job = self.jobs.start("update_metrics")
        self.db.commit()
        self.db.refresh(job)
        result = StackExchangeResult(items=[])
        processed = 0

        try:
            due_questions = self.questions.due_for_metric_update(limit=limit)
            stack_ids = [question.stackoverflow_question_id for question in due_questions]
            by_stack_id: dict[int, Question] = {
                question.stackoverflow_question_id: question for question in due_questions
            }
            result = self.client.fetch_question_metrics(stack_ids)
            affected_question_ids: set[int] = set()
            for item in result.items:
                question = by_stack_id.get(item.get("question_id"))
                if question is None:
                    job.items_failed += 1
                    continue
                self.questions.update_metrics_from_api_item(question, item, job.id)
                affected_question_ids.add(question.id)
                processed += 1

            affected_source_ids: set[int] = set()
            if affected_question_ids:
                affected_source_ids = set(
                    self.db.scalars(
                        select(SourceQuestion.source_id).where(
                            SourceQuestion.question_id.in_(affected_question_ids)
                        )
                    )
                )
            for source_id in affected_source_ids:
                self.analytics.refresh_source_cache(source_id)

            job.questions_found = len(due_questions)
            job.questions_updated = processed
            self.jobs.finish(job)
            self.db.commit()
            self.db.refresh(job)
            return job, processed, result
        except Exception as exc:
            self.db.rollback()
            job = self.jobs.get(job.id) or job
            self.jobs.fail(job, exc)
            self.db.commit()
            self.db.refresh(job)
            return job, processed, result

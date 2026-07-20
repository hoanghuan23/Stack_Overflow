from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import PipelineJob, Question, Source, SourceQuestion
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.job_repository import JobRepository
from app.repositories.question_repository import QuestionRepository
from app.services.stackexchange_client import StackExchangeClient, StackExchangeResult


logger = logging.getLogger("stackoverflow_api.metrics")


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

    def run_due_updates(
        self,
        limit: int = 100,
        source_id: int | None = None,
    ) -> tuple[PipelineJob, int, StackExchangeResult]:
        job = self.jobs.start("update_metrics", source_id=source_id)
        self.db.commit()
        self.db.refresh(job)
        result = StackExchangeResult(items=[])
        processed = 0

        try:
            due_questions = self.questions.due_for_metric_update(limit=limit, source_id=source_id)
            stack_ids = [question.stackoverflow_question_id for question in due_questions]
            due_question_ids = [question.id for question in due_questions]
            if due_question_ids:
                source_query = (
                    select(
                        Source.id,
                        Source.identifier,
                        func.count(SourceQuestion.question_id),
                    )
                    .join(SourceQuestion, SourceQuestion.source_id == Source.id)
                    .where(SourceQuestion.question_id.in_(due_question_ids))
                    .group_by(Source.id, Source.identifier)
                    .order_by(Source.id)
                )
                if source_id is not None:
                    source_query = source_query.where(Source.id == source_id)
                source_counts = self.db.execute(source_query)
                for current_source_id, identifier, posts in source_counts:
                    logger.info(
                        "Bat dau cap nhat metrics | source=%s id=%s posts=%s",
                        identifier,
                        current_source_id,
                        posts,
                    )
            else:
                logger.info("Khong co metrics den han | limit=%s", limit)

            by_stack_id: dict[int, Question] = {
                question.stackoverflow_question_id: question for question in due_questions
            }
            result = self.client.fetch_question_metrics(stack_ids)
            affected_question_ids: set[int] = set()
            returned_stack_ids: set[int] = set()
            for item in result.items:
                stack_id = item.get("question_id")
                question = by_stack_id.get(stack_id)
                if question is None:
                    job.items_failed += 1
                    continue
                returned_stack_ids.add(stack_id)
                self.questions.update_metrics_from_api_item(question, item, job.id)
                affected_question_ids.add(question.id)
                processed += 1

            for question in due_questions:
                if question.stackoverflow_question_id in returned_stack_ids:
                    continue
                self.questions.mark_metric_lookup_missing(question)
                job.items_failed += 1

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
            logger.info(
                "Hoan tat cap nhat metrics | found=%s updated=%s failed=%s",
                job.questions_found,
                job.questions_updated,
                job.items_failed,
            )
            return job, processed, result
        except Exception as exc:
            self.db.rollback()
            job = self.jobs.get(job.id) or job
            self.jobs.fail(job, exc)
            self.db.commit()
            self.db.refresh(job)
            logger.exception(
                "Loi cap nhat metrics | found=%s updated=%s failed=%s",
                job.questions_found,
                job.questions_updated,
                job.items_failed,
            )
            return job, processed, result

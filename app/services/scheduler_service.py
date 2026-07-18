from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Source
from app.services.metric_service import MetricService
from app.services.scraper_service import ScraperService


class SchedulerService:
    def __init__(self, db: Session):
        self.db = db

    def run_due_sources(self) -> list[int]:
        now = datetime.utcnow()
        sources = self.db.scalars(
            select(Source).where(
                Source.is_active == True,  # noqa: E712
                Source.is_accessible == True,  # noqa: E712
                (Source.next_scrape == None) | (Source.next_scrape <= now),  # noqa: E711
            )
        )
        job_ids: list[int] = []
        scraper = ScraperService(self.db)
        for source in sources:
            job, _ = scraper.scrape_source(
                source.id,
                job_type="scrape_new_questions",
                stop_at_latest_seen=True,
            )
            job_ids.append(job.id)
        return job_ids

    def run_due_metrics(self, limit: int = 100) -> int | None:
        metrics = MetricService(self.db)
        if not metrics.questions.due_for_metric_update(limit=1):
            self.db.commit()
            return None
        job, _, _ = metrics.run_due_updates(limit=limit)
        return job.id

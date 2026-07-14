from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PipelineJob, PipelineLog


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, job_id: int) -> PipelineJob | None:
        return self.db.get(PipelineJob, job_id)

    def list(self) -> list[PipelineJob]:
        return list(self.db.scalars(select(PipelineJob).order_by(PipelineJob.created_at.desc())))

    def start(self, job_type: str, source_id: int | None = None) -> PipelineJob:
        job = PipelineJob(
            job_type=job_type,
            source_id=source_id,
            status="running",
            started_at=datetime.utcnow(),
        )
        self.db.add(job)
        self.db.flush()
        return job

    def finish(self, job: PipelineJob, status: str = "done") -> PipelineJob:
        job.status = status
        job.finished_at = datetime.utcnow()
        self.db.flush()
        return job

    def fail(
        self,
        job: PipelineJob,
        exc: Exception,
        source_id: int | None = None,
    ) -> PipelineJob:
        message = str(exc)
        job.status = "failed"
        job.error_message = message
        job.finished_at = datetime.utcnow()
        self.db.add(
            PipelineLog(
                job_id=job.id,
                source_id=source_id,
                log_level="ERROR",
                message=message,
                error_type=type(exc).__name__,
                error_details=repr(exc),
            )
        )
        self.db.flush()
        return job

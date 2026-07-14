from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.schemas import MetricRunResult
from app.db.session import get_db
from app.services.metric_service import MetricService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.post("/due/run", response_model=MetricRunResult)
def run_due_metrics(
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    job, processed, result = MetricService(db).run_due_updates(limit=limit)
    return MetricRunResult(
        job=job,
        questions_processed=processed,
        quota_max=result.quota_max,
        quota_remaining=result.quota_remaining,
    )

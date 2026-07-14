from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.schemas import PipelineJobRead
from app.db.session import get_db
from app.repositories.job_repository import JobRepository

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[PipelineJobRead])
def list_jobs(db: Session = Depends(get_db)):
    return JobRepository(db).list()


@router.get("/{job_id}", response_model=PipelineJobRead)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = JobRepository(db).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job

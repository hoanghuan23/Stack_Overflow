from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.schemas import ScrapeResult, SourceCreate, SourceRead
from app.db.session import get_db
from app.repositories.source_repository import SourceRepository
from app.services.scraper_service import ScraperService
from app.services.source_service import SourceService

router = APIRouter(prefix="/sources", tags=["sources"])


def get_scraper_service(db: Session = Depends(get_db)) -> ScraperService:
    return ScraperService(db)


@router.post("", response_model=SourceRead)
def create_source(
    payload: SourceCreate,
    db: Session = Depends(get_db),
    scraper: ScraperService = Depends(get_scraper_service),
):
    try:
        source = SourceService(db).create_source(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="source already exists") from exc

    scraper.scrape_source(source.id)
    db.refresh(source)
    return source


@router.get("", response_model=list[SourceRead])
def list_sources(db: Session = Depends(get_db)):
    return SourceRepository(db).list()


@router.get("/{source_id}", response_model=SourceRead)
def get_source(source_id: int, db: Session = Depends(get_db)):
    source = SourceRepository(db).get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    return source


@router.post("/{source_id}/scrape", response_model=ScrapeResult)
def scrape_source(source_id: int, db: Session = Depends(get_db)):
    try:
        job, result = ScraperService(db).scrape_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScrapeResult(
        job=job,
        quota_max=result.quota_max,
        quota_remaining=result.quota_remaining,
    )

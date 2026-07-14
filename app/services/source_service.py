from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Source
from app.db.schemas import SourceCreate
from app.repositories.source_repository import SourceRepository


class SourceService:
    def __init__(self, db: Session):
        self.db = db
        self.sources = SourceRepository(db)

    def create_source(self, payload: SourceCreate) -> Source:
        identifier = payload.identifier
        if payload.source_type == "latest":
            identifier = identifier or "latest"
        elif not identifier:
            raise ValueError("identifier is required for tag and keyword sources")

        assert identifier is not None
        existing = self.sources.get_by_identity(payload.source_type, identifier)
        if existing:
            return existing
        source = self.sources.create(
            payload.source_type,
            identifier,
            include_answers=payload.include_answers,
        )
        self.db.commit()
        self.db.refresh(source)
        return source

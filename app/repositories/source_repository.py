from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Source


class SourceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, source_id: int) -> Source | None:
        return self.db.get(Source, source_id)

    def list(self) -> list[Source]:
        return list(self.db.scalars(select(Source).order_by(Source.id.desc())))

    def get_by_identity(self, source_type: str, identifier: str) -> Source | None:
        return self.db.scalar(
            select(Source).where(
                Source.source_type == source_type,
                Source.identifier == identifier,
            )
        )

    def create(
        self,
        source_type: str,
        identifier: str,
        include_answers: bool = False,
    ) -> Source:
        source = Source(
            source_type=source_type,
            identifier=identifier,
            include_answers=include_answers,
        )
        self.db.add(source)
        self.db.flush()
        return source

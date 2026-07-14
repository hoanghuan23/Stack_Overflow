from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Tag
from app.db.schemas import TagRead
from app.db.session import get_db

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagRead])
def list_tags(db: Session = Depends(get_db)):
    return list(db.scalars(select(Tag).order_by(Tag.tag_name.asc())))

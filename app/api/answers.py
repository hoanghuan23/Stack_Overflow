from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.schemas import AnswerRead
from app.db.session import get_db
from app.repositories.answer_repository import AnswerRepository

router = APIRouter(prefix="/answers", tags=["answers"])


@router.get("", response_model=list[AnswerRead])
def list_answers(db: Session = Depends(get_db)):
    return AnswerRepository(db).list()

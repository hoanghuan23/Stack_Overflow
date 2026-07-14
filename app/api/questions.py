from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.schemas import QuestionRead
from app.db.session import get_db
from app.repositories.question_repository import QuestionRepository

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("", response_model=list[QuestionRead])
def list_questions(
    source_id: int | None = None,
    tag: str | None = None,
    is_answered: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="created", pattern="^(created|hot|score|views|answers)$"),
    db: Session = Depends(get_db),
):
    return QuestionRepository(db).list(
        source_id=source_id,
        tag=tag,
        is_answered=is_answered,
        limit=limit,
        offset=offset,
        sort=sort,
    )


@router.get("/{question_id}", response_model=QuestionRead)
def get_question(question_id: int, db: Session = Depends(get_db)):
    question = QuestionRepository(db).get(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")
    return question

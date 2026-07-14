from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Answer
from app.repositories.question_repository import unix_to_datetime


class AnswerRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self) -> list[Answer]:
        return list(self.db.scalars(select(Answer).order_by(Answer.answer_created_at.desc())))

    def upsert_from_api_item(self, question_id: int, item: dict) -> tuple[Answer, bool]:
        stackoverflow_id = int(item["answer_id"])
        answer = self.db.scalar(
            select(Answer).where(Answer.stackoverflow_answer_id == stackoverflow_id)
        )
        is_new = answer is None
        if answer is None:
            answer = Answer(
                question_id=question_id,
                stackoverflow_answer_id=stackoverflow_id,
                answer_created_at=unix_to_datetime(item.get("creation_date")) or datetime.utcnow(),
            )
            self.db.add(answer)

        owner = item.get("owner") or {}
        answer.author_user_id = owner.get("user_id")
        answer.author_display_name = owner.get("display_name")
        answer.is_accepted = bool(item.get("is_accepted", False))
        answer.score = int(item.get("score", 0))
        answer.answer_body = item.get("body")
        answer.last_activity_at = unix_to_datetime(item.get("last_activity_date"))
        self.db.flush()
        return answer, is_new

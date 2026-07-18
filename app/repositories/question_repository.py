from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session, aliased

from app.db.models import Question, QuestionMetric, QuestionTag, SourceQuestion, Tag

METRIC_TRACKING_WINDOW = timedelta(hours=24)


def unix_to_datetime(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.utcfromtimestamp(value)


def calculate_metric_tier(answer_count: int, score: int, view_count: int) -> str:
    engagement = answer_count * 5 + max(score, 0) * 2 
    if engagement >= 50 or (answer_count >= 10 and view_count >= 5000):
        return "hot"
    if engagement >= 25 or answer_count >=5:
        return "high"
    if engagement >= 8 or answer_count >=2:
        return "medium"
    if engagement >= 0 or view_count >= 500:
        return "low"
    return "very_low"


def next_metric_update_for_tier(tier: str, now: datetime | None = None) -> datetime:
    base = now or datetime.utcnow()
    minutes_by_tier = {
        "hot": 30,
        "high": 90,
        "medium": 240,
        "low": 360,
        "very_low": 720,
    }
    return base + timedelta(minutes=minutes_by_tier[tier])


def metric_tracking_until(question_created_at: datetime) -> datetime:
    return question_created_at + METRIC_TRACKING_WINDOW


def should_track_metrics(question_created_at: datetime, now: datetime | None = None) -> bool:
    return metric_tracking_until(question_created_at) > (now or datetime.utcnow())


class QuestionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, question_id: int) -> Question | None:
        return self.db.get(Question, question_id)

    def list(
        self,
        *,
        source_id: int | None = None,
        tag: str | None = None,
        is_answered: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = "created",
    ) -> list[Question]:
        stmt: Select[tuple[Question]] = select(Question)
        if source_id is not None:
            stmt = stmt.join(SourceQuestion, SourceQuestion.question_id == Question.id).where(
                SourceQuestion.source_id == source_id
            )
        if tag:
            stmt = (
                stmt.join(QuestionTag, QuestionTag.question_id == Question.id)
                .join(Tag, Tag.id == QuestionTag.tag_id)
                .where(Tag.tag_name == tag)
            )
        if is_answered is not None:
            stmt = stmt.where(Question.is_answered == is_answered)

        latest_metric_id = (
            select(
                QuestionMetric.question_id,
                func.max(QuestionMetric.id).label("metric_id"),
            )
            .group_by(QuestionMetric.question_id)
            .subquery()
        )
        latest_metric = aliased(QuestionMetric)
        stmt = (
            stmt.outerjoin(latest_metric_id, latest_metric_id.c.question_id == Question.id)
            .outerjoin(latest_metric, latest_metric.id == latest_metric_id.c.metric_id)
        )

        order_map = {
            "hot": (
                latest_metric.answer_count.desc().nullslast(),
                latest_metric.score.desc().nullslast(),
                latest_metric.view_count.desc().nullslast(),
            ),
            "score": (latest_metric.score.desc().nullslast(),),
            "views": (latest_metric.view_count.desc().nullslast(),),
            "answers": (latest_metric.answer_count.desc().nullslast(),),
            "created": (Question.question_created_at.desc(),),
        }
        stmt = stmt.order_by(*order_map.get(sort, order_map["created"])).limit(limit).offset(offset)
        return list(self.db.scalars(stmt))

    def due_for_metric_update(self, limit: int = 100, source_id: int | None = None) -> list[Question]:
        now = datetime.utcnow()
        self.deactivate_expired_metric_tracking(now)
        created_after = now - METRIC_TRACKING_WINDOW
        stmt = select(Question)
        stmt = stmt.where(
            Question.is_tracked == True,  # noqa: E712
            Question.question_created_at >= created_after,
            (Question.tracking_until == None) | (Question.tracking_until > now),  # noqa: E711
            (Question.next_metric_update == None) | (Question.next_metric_update <= now),  # noqa: E711
        )
        if source_id is not None:
            stmt = stmt.join(SourceQuestion, SourceQuestion.question_id == Question.id).where(
                SourceQuestion.source_id == source_id
            )
        stmt = stmt.order_by(Question.next_metric_update.asc().nullsfirst(), Question.id.asc()).limit(limit)
        return list(self.db.scalars(stmt))

    def deactivate_expired_metric_tracking(self, now: datetime | None = None) -> int:
        current_time = now or datetime.utcnow()
        cutoff = current_time - METRIC_TRACKING_WINDOW
        result = self.db.execute(
            update(Question)
            .where(
                Question.is_tracked == True,  # noqa: E712
                Question.question_created_at < cutoff,
            )
            .values(
                is_tracked=False,
                next_metric_update=None,
            )
        )
        self.db.flush()
        return int(result.rowcount or 0)

    def latest_created_at_for_source(self, source_id: int) -> datetime | None:
        return self.db.scalar(
            select(func.max(Question.question_created_at))
            .join(SourceQuestion, SourceQuestion.question_id == Question.id)
            .where(SourceQuestion.source_id == source_id)
        )

    def upsert_from_api_item(self, source_id: int, item: dict) -> tuple[Question, bool]:
        stackoverflow_id = int(item["question_id"])
        question = self.db.scalar(
            select(Question).where(Question.stackoverflow_question_id == stackoverflow_id)
        )
        is_new = question is None
        if question is None:
            question = Question(
                stackoverflow_question_id=stackoverflow_id,
                source_id=source_id,
                title=item.get("title", ""),
                link=item.get("link", ""),
                last_activity_at=unix_to_datetime(item.get("last_activity_date")) or datetime.utcnow(),
                question_created_at=unix_to_datetime(item.get("creation_date")) or datetime.utcnow(),
            )
            self.db.add(question)

        owner = item.get("owner") or {}
        question.title = item.get("title", question.title)
        question.link = item.get("link", question.link)
        question.author_user_id = owner.get("user_id")
        question.author_display_name = owner.get("display_name")
        question.author_link = owner.get("link")
        question.is_answered = bool(item.get("is_answered", question.is_answered))
        question.last_activity_at = unix_to_datetime(item.get("last_activity_date")) or question.last_activity_at
        question.question_created_at = unix_to_datetime(item.get("creation_date")) or question.question_created_at
        question.last_edited_at = unix_to_datetime(item.get("last_edit_date"))
        now = datetime.utcnow()
        question.tracking_until = metric_tracking_until(question.question_created_at)
        question.is_tracked = should_track_metrics(question.question_created_at, now)
        answer_count = int(item.get("answer_count", 0))
        score = int(item.get("score", 0))
        view_count = int(item.get("view_count", 0))
        question.metric_tier = calculate_metric_tier(answer_count, score, view_count)
        question.last_metric_update = now
        if not question.is_tracked:
            question.next_metric_update = None
        elif question.next_metric_update is None:
            question.next_metric_update = next_metric_update_for_tier(
                question.metric_tier,
                question.last_metric_update,
            )
        self.db.flush()
        self._record_metric(question.id, view_count, answer_count, score, job_id=None)

        self._link_source_question(source_id, question.id)
        self._sync_tags(question.id, item.get("tags", []))
        return question, is_new

    def update_metrics_from_api_item(
        self,
        question: Question,
        item: dict,
        job_id: int | None,
    ) -> Question:
        question.is_answered = bool(item.get("is_answered", question.is_answered))
        view_count = int(item.get("view_count", question.view_count))
        answer_count = int(item.get("answer_count", question.answer_count))
        score = int(item.get("score", question.score))
        question.last_activity_at = unix_to_datetime(item.get("last_activity_date")) or question.last_activity_at
        question.last_metric_update = datetime.utcnow()
        question.metric_tier = calculate_metric_tier(answer_count, score, view_count)
        question.next_metric_update = next_metric_update_for_tier(
            question.metric_tier, question.last_metric_update
        )
        self._record_metric(question.id, view_count, answer_count, score, job_id=job_id)
        self.db.flush()
        return question

    def _record_metric(
        self,
        question_id: int,
        view_count: int,
        answer_count: int,
        score: int,
        job_id: int | None,
    ) -> None:
        self.db.add(
            QuestionMetric(
                question_id=question_id,
                view_count=view_count,
                answer_count=answer_count,
                score=score,
                job_id=job_id,
            )
        )

    def _link_source_question(self, source_id: int, question_id: int) -> None:
        mapping = self.db.get(SourceQuestion, {"source_id": source_id, "question_id": question_id})
        if mapping is None:
            self.db.add(SourceQuestion(source_id=source_id, question_id=question_id))
        else:
            mapping.last_seen_at = datetime.utcnow()
        self.db.flush()

    def _sync_tags(self, question_id: int, tags: list[str]) -> None:
        for tag_name in tags:
            tag = self.db.scalar(select(Tag).where(Tag.tag_name == tag_name))
            if tag is None:
                tag = Tag(tag_name=tag_name)
                self.db.add(tag)
                self.db.flush()
            mapping = self.db.get(QuestionTag, {"question_id": question_id, "tag_id": tag.id})
            if mapping is None:
                self.db.add(QuestionTag(question_id=question_id, tag_id=tag.id))
        self.db.flush()

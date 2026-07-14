from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AnalyticsCache, Question, QuestionMetric, Source, SourceQuestion


MINUTES_BY_SOURCE_TIER = {
    5: 15,
    4: 30,
    3: 60,
    2: 180,
    1: 360,
}


@dataclass(frozen=True)
class SourceAnalyticsSnapshot:
    cache: AnalyticsCache
    tier: int
    next_scrape: datetime


def calculate_source_tier(
    total_questions: int,
    total_answers: int,
    total_views: int,
    total_score: int,
) -> int:
    activity_score = (
        total_questions * 3
        + total_answers * 5
        + max(total_score, 0) * 2
        + math.log10(total_views + 1) * 3
    )

    if activity_score >= 150:
        return 5
    if activity_score >= 70:
        return 4
    if activity_score >= 30:
        return 3
    if activity_score >= 10:
        return 2
    return 1


class AnalyticsRepository:
    def __init__(self, db: Session):
        self.db = db

    def refresh_source_cache(
        self,
        source_id: int,
        today: date | None = None,
        now: datetime | None = None,
    ) -> SourceAnalyticsSnapshot:
        source = self.db.get(Source, source_id)
        if source is None:
            raise ValueError(f"Source {source_id} not found")

        current_date = today or date.today()
        current_time = now or datetime.utcnow()
        totals = self._source_totals(source_id)
        previous_total = self._previous_total_questions(source_id, current_date)
        growth_rate = 0.0
        if previous_total:
            growth_rate = (totals["total_questions"] - previous_total) / previous_total

        cache = self.db.scalar(
            select(AnalyticsCache).where(
                AnalyticsCache.source_id == source_id,
                AnalyticsCache.date == current_date,
            )
        )
        if cache is None:
            cache = AnalyticsCache(source_id=source_id, date=current_date)
            self.db.add(cache)

        cache.total_questions = totals["total_questions"]
        cache.total_answers = totals["total_answers"]
        cache.total_views = totals["total_views"]
        cache.total_score = totals["total_score"]
        cache.avg_answers_per_question = (
            totals["total_answers"] / totals["total_questions"]
            if totals["total_questions"]
            else 0.0
        )
        cache.top_question_id = totals["top_question_id"]
        cache.growth_rate = growth_rate
        cache.cached_at = current_time

        tier = calculate_source_tier(
            cache.total_questions,
            cache.total_answers,
            cache.total_views,
            cache.total_score,
        )
        source.schedule_tier = tier
        minutes = source.schedule_override_minutes or MINUTES_BY_SOURCE_TIER[tier]
        source.next_scrape = current_time + timedelta(minutes=minutes)

        self.db.flush()
        return SourceAnalyticsSnapshot(cache=cache, tier=tier, next_scrape=source.next_scrape)

    def _source_totals(self, source_id: int) -> dict[str, int | None]:
        latest_metric_id = (
            select(
                QuestionMetric.question_id,
                func.max(QuestionMetric.id).label("metric_id"),
            )
            .group_by(QuestionMetric.question_id)
            .subquery()
        )
        latest_metric = (
            select(
                Question.id.label("question_id"),
                QuestionMetric.answer_count,
                QuestionMetric.view_count,
                QuestionMetric.score,
            )
            .join(SourceQuestion, SourceQuestion.question_id == Question.id)
            .outerjoin(latest_metric_id, latest_metric_id.c.question_id == Question.id)
            .outerjoin(QuestionMetric, QuestionMetric.id == latest_metric_id.c.metric_id)
            .where(SourceQuestion.source_id == source_id)
            .subquery()
        )

        row = self.db.execute(
            select(
                func.count(latest_metric.c.question_id),
                func.coalesce(func.sum(latest_metric.c.answer_count), 0),
                func.coalesce(func.sum(latest_metric.c.view_count), 0),
                func.coalesce(func.sum(latest_metric.c.score), 0),
            )
        ).one()
        top_question_id = self.db.scalar(
            select(latest_metric.c.question_id)
            .order_by(
                latest_metric.c.score.desc().nullslast(),
                latest_metric.c.answer_count.desc().nullslast(),
                latest_metric.c.view_count.desc().nullslast(),
                latest_metric.c.question_id.asc(),
            )
            .limit(1)
        )

        return {
            "total_questions": int(row[0] or 0),
            "total_answers": int(row[1] or 0),
            "total_views": int(row[2] or 0),
            "total_score": int(row[3] or 0),
            "top_question_id": top_question_id,
        }

    def _previous_total_questions(self, source_id: int, current_date: date) -> int:
        previous = self.db.scalar(
            select(AnalyticsCache.total_questions)
            .where(
                AnalyticsCache.source_id == source_id,
                AnalyticsCache.date < current_date,
            )
            .order_by(AnalyticsCache.date.desc())
            .limit(1)
        )
        return int(previous or 0)

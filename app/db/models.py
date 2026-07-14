from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('tag', 'keyword', 'latest')",
            name="ck_sources_source_type",
        ),
        UniqueConstraint("source_type", "identifier"),
        Index("idx_sources_next_scrape", "is_active", "is_accessible", "next_scrape"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    identifier: Mapped[str] = mapped_column(String(300), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_accessible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_answers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_scraped: Mapped[datetime | None] = mapped_column(DateTime)
    next_scrape: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_tier: Mapped[int | None] = mapped_column(Integer)
    schedule_override_minutes: Mapped[int | None] = mapped_column(Integer)

    questions: Mapped[list["Question"]] = relationship(back_populates="source")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("stackoverflow_question_id"),
        UniqueConstraint("link"),
        Index("idx_questions_created", "question_created_at"),
        Index("idx_questions_metric_due", "is_tracked", "next_metric_update"),
        Index("idx_questions_source", "source_id"),
        CheckConstraint(
            "metric_tier IN ('hot', 'high', 'medium', 'low', 'very_low')",
            name="ck_questions_metric_tier",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stackoverflow_question_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[int | None] = mapped_column(Integer)
    author_display_name: Mapped[str | None] = mapped_column(String(200))
    author_link: Mapped[str | None] = mapped_column(Text)
    is_answered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    question_created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_edited_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    is_tracked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tracking_until: Mapped[datetime | None] = mapped_column(DateTime)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_metric_update: Mapped[datetime | None] = mapped_column(DateTime)
    next_metric_update: Mapped[datetime | None] = mapped_column(DateTime)
    metric_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="very_low")

    source: Mapped[Source | None] = relationship(back_populates="questions")
    metrics: Mapped[list["QuestionMetric"]] = relationship(
        back_populates="question",
        order_by="desc(QuestionMetric.id)",
    )

    @property
    def latest_metric(self) -> QuestionMetric | None:
        return self.metrics[0] if self.metrics else None

    @property
    def view_count(self) -> int:
        return self.latest_metric.view_count if self.latest_metric else 0

    @property
    def answer_count(self) -> int:
        return self.latest_metric.answer_count if self.latest_metric else 0

    @property
    def score(self) -> int:
        return self.latest_metric.score if self.latest_metric else 0


class SourceQuestion(Base):
    __tablename__ = "source_questions"
    __table_args__ = (Index("idx_source_questions_question", "question_id"),)

    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("tag_name"), Index("idx_tags_name", "tag_name"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class QuestionTag(Base):
    __tablename__ = "question_tags"
    __table_args__ = (Index("idx_question_tags_tag", "tag_id"),)

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class AnalyticsCache(Base):
    __tablename__ = "analytics_cache"
    __table_args__ = (
        UniqueConstraint("source_id", "date"),
        Index("idx_analytics_cache_source_date", "source_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_answers_per_question: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    top_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL")
    )
    growth_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    cached_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('scrape_questions', 'scrape_new_questions', 'update_metrics', 'scrape_answers')",
            name="ck_pipeline_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed')",
            name="ck_pipeline_jobs_status",
        ),
        Index("idx_pipeline_jobs_source_time", "source_id", "started_at"),
        Index("idx_pipeline_jobs_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(30), nullable=False, default="scrape_questions")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    questions_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    questions_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    questions_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class QuestionMetric(Base):
    __tablename__ = "question_metrics"
    __table_args__ = (
        Index("idx_question_metrics_question_time", "question_id", "recorded_at"),
        Index("idx_question_metrics_recorded_at", "recorded_at"),
        Index("idx_question_metrics_hot", "answer_count", "score", "view_count"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))

    question: Mapped[Question] = relationship(back_populates="metrics")


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("stackoverflow_answer_id"),
        Index("idx_answers_question_time", "question_id", "answer_created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    stackoverflow_answer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    author_user_id: Mapped[int | None] = mapped_column(Integer)
    author_display_name: Mapped[str | None] = mapped_column(String(200))
    is_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answer_body: Mapped[str | None] = mapped_column(Text)
    answer_created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"
    __table_args__ = (
        CheckConstraint("log_level IN ('ERROR', 'WARNING')", name="ck_pipeline_logs_level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    log_level: Mapped[str] = mapped_column(String(20), nullable=False, default="ERROR")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

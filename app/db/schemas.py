from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SourceType = Literal["tag", "keyword", "latest"]


class SourceCreate(BaseModel):
    source_type: SourceType
    identifier: str | None = None
    include_answers: bool = False

    @field_validator("identifier")
    @classmethod
    def strip_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    identifier: str
    is_active: bool
    is_accessible: bool
    include_answers: bool
    created_at: datetime
    last_scraped: datetime | None
    next_scrape: datetime | None
    schedule_tier: int | None
    schedule_override_minutes: int | None


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stackoverflow_question_id: int
    source_id: int | None
    title: str
    link: str
    author_user_id: int | None
    author_display_name: str | None
    author_link: str | None
    is_answered: bool
    view_count: int
    answer_count: int
    score: int
    last_activity_at: datetime
    question_created_at: datetime
    last_edited_at: datetime | None
    is_tracked: bool
    tracking_until: datetime | None
    is_deleted: bool
    last_metric_update: datetime | None
    next_metric_update: datetime | None
    metric_tier: str


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tag_name: str
    created_at: datetime


class AnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int
    stackoverflow_answer_id: int
    author_user_id: int | None
    author_display_name: str | None
    is_accepted: bool
    score: int
    answer_body: str | None
    answer_created_at: datetime
    last_activity_at: datetime | None


class PipelineJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    source_id: int | None
    status: str
    questions_found: int
    questions_new: int
    questions_updated: int
    items_failed: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ScrapeResult(BaseModel):
    job: PipelineJobRead
    quota_max: int | None = None
    quota_remaining: int | None = None


class MetricRunResult(BaseModel):
    job: PipelineJobRead
    questions_processed: int = 0
    quota_max: int | None = None
    quota_remaining: int | None = None


class HealthRead(BaseModel):
    status: str = "ok"


class QuestionSort(str):
    CREATED = "created"
    HOT = "hot"
    SCORE = "score"
    VIEWS = "views"
    ANSWERS = "answers"


class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

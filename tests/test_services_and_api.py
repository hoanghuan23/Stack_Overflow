from __future__ import annotations

from datetime import date, datetime, timedelta

from app.db.models import (
    AnalyticsCache,
    Answer,
    PipelineJob,
    PipelineLog,
    Question,
    QuestionMetric,
    SourceQuestion,
    Tag,
)
from app.repositories.analytics_repository import AnalyticsRepository, calculate_source_tier
from app.services.scraper_service import ScraperService
from app.services.stackexchange_client import StackExchangeResult


QUESTION_ITEM = {
    "question_id": 79978475,
    "title": "How to test a crawler?",
    "link": "https://stackoverflow.com/questions/79978475/how-to-test-a-crawler",
    "tags": ["python", "fastapi"],
    "owner": {
        "user_id": 1,
        "display_name": "Ada",
        "link": "https://stackoverflow.com/users/1/ada",
    },
    "is_answered": False,
    "view_count": 10,
    "answer_count": 0,
    "score": 1,
    "creation_date": 1_700_000_000,
    "last_activity_date": 1_700_000_100,
}


class FakeStackExchangeClient:
    def __init__(self, *, fail: bool = False):
        self.fail = fail

    def fetch_questions(self, source_type: str, identifier: str):
        if self.fail:
            raise RuntimeError("api failed")
        return StackExchangeResult(
            items=[QUESTION_ITEM],
            quota_max=300,
            quota_remaining=299,
        )

    def fetch_answers(self, stackoverflow_question_ids: list[int]):
        return StackExchangeResult(
            items=[
                {
                    "answer_id": 10,
                    "question_id": 79978475,
                    "owner": {"user_id": 2, "display_name": "Grace"},
                    "is_accepted": True,
                    "score": 5,
                    "body": "<p>Use tests.</p>",
                    "link": "https://stackoverflow.com/a/10",
                    "creation_date": 1_700_000_200,
                    "last_activity_date": 1_700_000_300,
                }
            ]
        )

    def fetch_question_metrics(self, stackoverflow_question_ids: list[int]):
        item = dict(QUESTION_ITEM)
        item.update({"is_answered": True, "view_count": 5000, "answer_count": 10, "score": 20})
        return StackExchangeResult(items=[item], quota_remaining=250)


def test_health_and_create_sources(client, db_session):
    from app.api.sources import get_scraper_service

    client.app.dependency_overrides[get_scraper_service] = lambda: ScraperService(
        db_session,
        client=FakeStackExchangeClient(),  # type: ignore[arg-type]
    )
    assert client.get("/health").json() == {"status": "ok"}
    source_schema = client.get("/openapi.json").json()["components"]["schemas"]["SourceCreate"]
    assert "scrape_now" not in source_schema["properties"]

    for payload in [
        {"source_type": "tag", "identifier": "python"},
        {"source_type": "keyword", "identifier": "memory leak"},
        {"source_type": "latest"},
    ]:
        response = client.post("/sources", json=payload)
        assert response.status_code == 200
        assert response.json()["source_type"] == payload["source_type"]

    response = client.get("/sources")
    assert response.status_code == 200
    assert len(response.json()) == 3
    assert db_session.query(PipelineJob).count() == 3
    assert db_session.query(Question).count() == 1


def test_scrape_upserts_questions_tags_mappings_and_answers(db_session):
    from app.db.models import Source

    source = Source(source_type="tag", identifier="python", include_answers=True)
    db_session.add(source)
    db_session.commit()

    service = ScraperService(db_session, client=FakeStackExchangeClient())  # type: ignore[arg-type]
    job, result = service.scrape_source(source.id)
    second_job, _ = service.scrape_source(source.id)

    assert job.status == "done"
    assert result.quota_remaining == 299
    assert second_job.questions_new == 0
    assert second_job.questions_updated == 1
    assert db_session.query(Question).count() == 1
    assert db_session.query(QuestionMetric).count() == 2
    assert db_session.query(Tag).count() == 2
    assert db_session.query(SourceQuestion).count() == 1
    assert db_session.query(Answer).count() == 1


def test_scrape_refreshes_daily_analytics_cache_and_schedule(db_session):
    from app.db.models import Source

    source = Source(source_type="tag", identifier="python")
    db_session.add(source)
    db_session.commit()

    service = ScraperService(db_session, client=FakeStackExchangeClient())  # type: ignore[arg-type]
    job, _ = service.scrape_source(source.id)
    first_next_scrape = source.next_scrape
    second_job, _ = service.scrape_source(source.id)

    cache = db_session.query(AnalyticsCache).one()
    assert job.status == "done"
    assert second_job.status == "done"
    assert db_session.query(AnalyticsCache).count() == 1
    assert cache.source_id == source.id
    assert cache.date == date.today()
    assert cache.total_questions == 1
    assert cache.total_answers == 0
    assert cache.total_views == 10
    assert cache.total_score == 1
    assert cache.avg_answers_per_question == 0
    assert cache.growth_rate == 0
    assert cache.top_question_id == db_session.query(Question).one().id
    assert source.schedule_tier == 1
    assert first_next_scrape is not None
    assert source.next_scrape is not None
    assert timedelta(minutes=350) < source.next_scrape - source.last_scraped < timedelta(minutes=370)


def test_scrape_failure_marks_job_failed_and_logs(db_session):
    from app.db.models import Source

    source = Source(source_type="latest", identifier="latest")
    db_session.add(source)
    db_session.commit()

    job, _ = ScraperService(
        db_session,
        client=FakeStackExchangeClient(fail=True),  # type: ignore[arg-type]
    ).scrape_source(source.id)

    assert job.status == "failed"
    assert "api failed" in (job.error_message or "")
    assert db_session.query(PipelineLog).count() == 1


def test_metric_run_updates_question_and_snapshot(client, db_session):
    from app.db.models import Source
    from app.services.metric_service import MetricService

    source = Source(source_type="tag", identifier="python")
    db_session.add(source)
    db_session.commit()
    ScraperService(db_session, client=FakeStackExchangeClient()).scrape_source(source.id)  # type: ignore[arg-type]
    scraped_question = db_session.query(Question).one()
    scraped_question.next_metric_update = None
    db_session.commit()

    job, processed, result = MetricService(
        db_session,
        client=FakeStackExchangeClient(),  # type: ignore[arg-type]
    ).run_due_updates()

    question = db_session.query(Question).one()
    assert job.status == "done"
    assert processed == 1
    assert result.quota_remaining == 250
    assert question.metric_tier == "hot"
    assert question.is_answered is True
    assert question.view_count == 5000
    assert question.answer_count == 10
    assert question.score == 20
    assert db_session.query(QuestionMetric).count() == 2

    cache = db_session.query(AnalyticsCache).one()
    assert cache.total_questions == 1
    assert cache.total_answers == 10
    assert cache.total_views == 5000
    assert cache.total_score == 20
    assert cache.avg_answers_per_question == 10
    assert cache.top_question_id == question.id
    assert source.schedule_tier == 4
    assert source.next_scrape is not None
    assert source.last_scraped is not None
    assert timedelta(minutes=20) < source.next_scrape - datetime.utcnow() < timedelta(minutes=40)


def test_analytics_cache_handles_empty_source_override_and_growth(db_session):
    from app.db.models import Source

    source = Source(
        source_type="tag",
        identifier="empty",
        schedule_override_minutes=42,
    )
    db_session.add(source)
    db_session.flush()
    db_session.add(
        AnalyticsCache(
            source_id=source.id,
            date=date(2026, 1, 1),
            total_questions=4,
        )
    )
    db_session.commit()

    now = datetime(2026, 1, 2, 12, 0, 0)
    snapshot = AnalyticsRepository(db_session).refresh_source_cache(
        source.id,
        today=date(2026, 1, 2),
        now=now,
    )

    assert calculate_source_tier(0, 0, 0, 0) == 1
    assert snapshot.cache.total_questions == 0
    assert snapshot.cache.total_answers == 0
    assert snapshot.cache.total_views == 0
    assert snapshot.cache.total_score == 0
    assert snapshot.cache.avg_answers_per_question == 0
    assert snapshot.cache.top_question_id is None
    assert snapshot.cache.growth_rate == -1
    assert source.schedule_tier == 1
    assert source.next_scrape == now + timedelta(minutes=42)


def test_questions_and_jobs_api(client, db_session):
    from app.db.models import Source

    source = Source(source_type="tag", identifier="python")
    db_session.add(source)
    db_session.commit()
    ScraperService(db_session, client=FakeStackExchangeClient()).scrape_source(source.id)  # type: ignore[arg-type]

    questions = client.get("/questions", params={"tag": "python", "sort": "hot"}).json()
    assert len(questions) == 1
    assert questions[0]["stackoverflow_question_id"] == 79978475
    assert questions[0]["is_answered"] is False
    assert questions[0]["view_count"] == 10
    assert questions[0]["answer_count"] == 0
    assert questions[0]["score"] == 1

    answered_questions = client.get("/questions", params={"is_answered": True}).json()
    assert answered_questions == []

    jobs = client.get("/jobs").json()
    assert len(jobs) == 1
    assert client.get(f"/jobs/{jobs[0]['id']}").status_code == 200

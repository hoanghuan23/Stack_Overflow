from __future__ import annotations

from app.core.config import Settings
from app.services.stackexchange_client import StackExchangeAPIError, StackExchangeClient


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, params: dict, timeout: int):
        self.calls.append((url, params))
        return FakeResponse(self.payloads.pop(0))


def make_client(session: FakeSession, sleeps: list[int] | None = None) -> StackExchangeClient:
    sleeps = sleeps if sleeps is not None else []
    return StackExchangeClient(
        settings=Settings(stackexchange_max_pages=3, stackexchange_timeout_seconds=7),
        session=session,  # type: ignore[arg-type]
        sleep=lambda seconds: sleeps.append(seconds),
    )


def test_fetch_questions_uses_tag_params():
    session = FakeSession([{"items": [], "has_more": False, "quota_remaining": 99}])
    client = make_client(session)

    result = client.fetch_questions("tag", "python")

    url, params = session.calls[0]
    assert url.endswith("/questions")
    assert params["tagged"] == "python"
    assert params["site"] == "stackoverflow"
    assert result.quota_remaining == 99


def test_fetch_questions_uses_keyword_endpoint():
    session = FakeSession([{"items": [], "has_more": False}])
    client = make_client(session)

    client.fetch_questions("keyword", "memory leak")

    url, params = session.calls[0]
    assert url.endswith("/search/advanced")
    assert params["q"] == "memory leak"


def test_fetch_questions_latest_has_no_tag_or_query():
    session = FakeSession([{"items": [], "has_more": False}])
    client = make_client(session)

    client.fetch_questions("latest", "latest")

    _, params = session.calls[0]
    assert "tagged" not in params
    assert "q" not in params


def test_fetch_questions_paginates_and_respects_backoff():
    sleeps: list[int] = []
    session = FakeSession(
        [
            {"items": [{"question_id": 1}], "has_more": True, "backoff": 2},
            {"items": [{"question_id": 2}], "has_more": False, "quota_max": 300},
        ]
    )
    client = make_client(session, sleeps)

    result = client.fetch_questions("latest", "latest")

    assert [item["question_id"] for item in result.items] == [1, 2]
    assert len(session.calls) == 2
    assert sleeps == [2]
    assert result.quota_max == 300


def test_fetch_questions_raises_api_error():
    session = FakeSession(
        [
            {
                "error_id": 400,
                "error_name": "bad_parameter",
                "error_message": "broken",
            }
        ]
    )
    client = make_client(session)

    try:
        client.fetch_questions("latest", "latest")
    except StackExchangeAPIError as exc:
        assert "bad_parameter" in str(exc)
    else:
        raise AssertionError("expected StackExchangeAPIError")

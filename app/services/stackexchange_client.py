from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import requests

from app.core.config import Settings, get_settings


class StackExchangeAPIError(RuntimeError):
    pass


@dataclass
class StackExchangeResult:
    items: list[dict]
    quota_max: int | None = None
    quota_remaining: int | None = None
    has_more: bool = False
    backoffs: list[int] = field(default_factory=list)


class StackExchangeClient:
    base_url = "https://api.stackexchange.com/2.3"

    def __init__(
        self,
        settings: Settings | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings or get_settings()
        self.session = session or requests.Session()
        self.sleep = sleep

    def fetch_questions(
        self,
        source_type: str,
        identifier: str,
        *,
        lookback_hours: int | None = None,
    ) -> StackExchangeResult:
        now = datetime.utcnow()
        from_time = now - timedelta(hours=lookback_hours or self.settings.lookback_hours)
        params: dict[str, str | int] = {
            "site": "stackoverflow",
            "sort": "creation",
            "order": "desc",
            "fromdate": int(from_time.timestamp()),
            "todate": int(now.timestamp()),
            "pagesize": 100,
        }
        endpoint = "/questions"
        if source_type == "tag":
            params["tagged"] = identifier
        elif source_type == "keyword":
            endpoint = "/search/advanced"
            params["q"] = identifier
        elif source_type == "latest":
            pass
        else:
            raise ValueError(f"Unsupported source_type: {source_type}")
        return self._paginated_get(endpoint, params)

    def fetch_question_metrics(self, stackoverflow_question_ids: list[int]) -> StackExchangeResult:
        if not stackoverflow_question_ids:
            return StackExchangeResult(items=[])
        ids = ";".join(str(item) for item in stackoverflow_question_ids)
        return self._paginated_get(
            f"/questions/{ids}",
            {
                "site": "stackoverflow",
                "pagesize": 100,
                "sort": "activity",
                "order": "desc",
            },
        )

    def fetch_answers(self, stackoverflow_question_ids: list[int]) -> StackExchangeResult:
        if not stackoverflow_question_ids:
            return StackExchangeResult(items=[])
        ids = ";".join(str(item) for item in stackoverflow_question_ids)
        return self._paginated_get(
            f"/questions/{ids}/answers",
            {
                "site": "stackoverflow",
                "pagesize": 100,
                "sort": "creation",
                "order": "desc",
                "filter": "withbody",
            },
        )

    def _paginated_get(self, endpoint: str, params: dict[str, str | int]) -> StackExchangeResult:
        items: list[dict] = []
        backoffs: list[int] = []
        quota_max: int | None = None
        quota_remaining: int | None = None
        has_more = False

        for page in range(1, self.settings.stackexchange_max_pages + 1):
            request_params = dict(params)
            request_params["page"] = page
            if self.settings.stackexchange_key:
                request_params["key"] = self.settings.stackexchange_key

            response = self.session.get(
                f"{self.base_url}{endpoint}",
                params=request_params,
                timeout=self.settings.stackexchange_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if "error_id" in payload:
                raise StackExchangeAPIError(
                    "Stack Exchange API error "
                    f"{payload['error_id']}: {payload.get('error_name')} - "
                    f"{payload.get('error_message')}"
                )

            items.extend(payload.get("items", []))
            quota_max = payload.get("quota_max", quota_max)
            quota_remaining = payload.get("quota_remaining", quota_remaining)
            has_more = bool(payload.get("has_more", False))

            backoff = payload.get("backoff")
            if backoff is not None:
                backoffs.append(int(backoff))
                self.sleep(int(backoff))

            if not has_more:
                break

        return StackExchangeResult(
            items=items,
            quota_max=quota_max,
            quota_remaining=quota_remaining,
            has_more=has_more,
            backoffs=backoffs,
        )

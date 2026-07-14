from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///data/stack_overflow.db"
    stackexchange_key: str | None = None
    lookback_hours: int = 24
    stackexchange_timeout_seconds: int = 30
    stackexchange_max_pages: int = 5
    default_scrape_interval_minutes: int = 60


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/stack_overflow.db"),
        stackexchange_key=os.getenv("STACKEXCHANGE_KEY") or None,
        lookback_hours=int(os.getenv("LOOKBACK_HOURS", "24")),
        stackexchange_timeout_seconds=int(
            os.getenv("STACKEXCHANGE_TIMEOUT_SECONDS", "30")
        ),
        stackexchange_max_pages=int(os.getenv("STACKEXCHANGE_MAX_PAGES", "5")),
        default_scrape_interval_minutes=int(
            os.getenv("DEFAULT_SCRAPE_INTERVAL_MINUTES", "60")
        ),
    )

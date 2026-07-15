from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from app.db.session import SessionLocal
from app.services.scheduler_service import SchedulerService

logger = logging.getLogger(__name__)


def run_scheduler_cycle() -> None:
    db = SessionLocal()
    try:
        scheduler = SchedulerService(db)
        scheduler.run_due_sources()
        scheduler.run_due_metrics()
    finally:
        db.close()


async def scheduler_loop(interval_seconds: int) -> None:
    while True:
        try:
            await asyncio.to_thread(run_scheduler_cycle)
        except Exception:
            logger.exception("Scheduled crawler cycle failed")
        await asyncio.sleep(interval_seconds)


async def stop_scheduler(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

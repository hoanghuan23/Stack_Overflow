from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import answers, health, jobs, metrics, questions, sources, tags
from app.core.config import get_settings
from app.db import models
from app.db.session import Base, engine
from app.services.scheduler_runner import scheduler_loop, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    scheduler_task: asyncio.Task[None] | None = None
    if settings.scheduler_interval_seconds > 0:
        scheduler_task = asyncio.create_task(
            scheduler_loop(settings.scheduler_interval_seconds)
        )
    try:
        yield
    finally:
        if scheduler_task is not None:
            await stop_scheduler(scheduler_task)


def create_app() -> FastAPI:
    app = FastAPI(title="Stack Overflow Crawler", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(sources.router)
    app.include_router(questions.router)
    app.include_router(tags.router)
    app.include_router(answers.router)
    app.include_router(metrics.router)
    app.include_router(jobs.router)
    return app


Base.metadata.create_all(bind=engine)
app = create_app()

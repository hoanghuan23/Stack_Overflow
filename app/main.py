from __future__ import annotations

from fastapi import FastAPI

from app.api import answers, health, jobs, metrics, questions, sources, tags
from app.db import models
from app.db.session import Base, engine


def create_app() -> FastAPI:
    app = FastAPI(title="Stack Overflow Crawler")
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

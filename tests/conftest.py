from __future__ import annotations

import pytest
import asyncio
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import create_app


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    class ASGITestClient:
        def __init__(self, app):
            self.app = app

        async def _request(self, method: str, url: str, **kwargs):
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as async_client:
                return await async_client.request(method, url, **kwargs)

        def get(self, url: str, **kwargs):
            return asyncio.run(self._request("GET", url, **kwargs))

        def post(self, url: str, **kwargs):
            return asyncio.run(self._request("POST", url, **kwargs))

    return ASGITestClient(app)

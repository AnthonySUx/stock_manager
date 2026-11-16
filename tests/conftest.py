"""Pytest configuration: test database and FastAPI client fixtures.

Tests run on in-memory SQLite by default. Set TEST_DATABASE_URL to run them
on another database, e.g. a throwaway MySQL database (all tables in it are
dropped after each test):

    TEST_DATABASE_URL="mysql+pymysql://root@localhost/stock_manager_test?unix_socket=/tmp/mysql.sock" pytest
"""

import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from stock_manager.api.db import get_session
from stock_manager.api.main import app
from stock_manager.api.models import Base
from stock_manager.api.schema_version import stamp_head

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or "sqlite://"
IS_SQLITE = TEST_DATABASE_URL.startswith("sqlite")

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    poolclass=StaticPool,
)


if IS_SQLITE:
    @event.listens_for(test_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _record):
        """Enforce foreign keys like MySQL does (SQLite has them off by default)."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture()
def db_session():
    """Provide a clean database session for each test."""
    Base.metadata.create_all(bind=test_engine)
    with test_engine.begin() as connection:
        # The API refuses to start unless the schema is at the newest Alembic
        # revision; the tables above match it (checked in test_migrations.py).
        stamp_head(connection)
    session = TestingSessionLocal()
    from stock_manager.api.category_services import seed_default_categories
    seed_default_categories(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


TEST_API_TOKEN = "test-api-token"


@pytest.fixture()
def client(db_session, monkeypatch):
    """Provide a FastAPI TestClient with an isolated SQLite database.

    The client sends the shared API token (issue #41) on every request.
    """
    # Must patch before TestClient enters startup lifespan
    monkeypatch.setattr("stock_manager.api.main.engine", test_engine)
    monkeypatch.setenv("API_TOKEN", TEST_API_TOKEN)
    monkeypatch.delenv("API_AUTH_DISABLED", raising=False)

    def override_get_session():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app, headers={"Authorization": f"Bearer {TEST_API_TOKEN}"}) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ─── AI (never calls the real provider) ──────────────────────────


@pytest.fixture(autouse=True)
def _fresh_ai_config():
    """Each test reads the AI settings from its own environment (#66)."""
    from stock_manager.api import ai_client

    ai_client._config = None
    yield
    ai_client._config = None


class FakeAI:
    """The AI provider as seen through httpx.MockTransport.

    - `reply`: message content returned by default (a JSON string).
    - `responses`: optional queue, one entry per call: an httpx.Response, an
      exception (raised as a transport error), or a content string.
    - `requests`: the JSON payloads sent to the provider.
    """

    def __init__(self):
        self.reply = json.dumps({"ideas": [{"title": "番茄炒蛋", "matched_ingredients": ["番茄"]}]})
        self.responses: list = []
        self.requests: list[dict] = []

    @property
    def prompts(self) -> list:
        """The user message of each request."""
        return [r["messages"][1]["content"] for r in self.requests]

    @property
    def system_prompts(self) -> list:
        return [r["messages"][0]["content"] for r in self.requests]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        item = self.responses.pop(0) if self.responses else self.reply
        if isinstance(item, Exception):
            raise item
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json={"choices": [{"message": {"content": item}}]})


@pytest.fixture()
def fake_ai(monkeypatch):
    """AI enabled, answered by FakeAI instead of the network."""
    from stock_manager.api import ai_client

    fake = FakeAI()
    monkeypatch.setenv("AI_RECIPE_ENABLED", "true")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_BASE_URL", "http://ai.invalid")
    for var in ("AI_MODEL", "AI_TEMPERATURE", "AI_TIMEOUT_SECONDS", "AI_MAX_RETRIES",
                "AI_TOTAL_TIMEOUT_SECONDS", "AI_IMAGE_TIMEOUT_SECONDS", "AI_IMAGE_TOTAL_TIMEOUT_SECONDS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(ai_client, "_transport", httpx.MockTransport(fake.handle))
    ai_client.reload_config()
    return fake

"""Pytest configuration: test database and FastAPI client fixtures.

Tests run on in-memory SQLite by default. Set TEST_DATABASE_URL to run them
on another database, e.g. a throwaway MySQL database (all tables in it are
dropped after each test):

    TEST_DATABASE_URL="mysql+pymysql://root@localhost/stock_manager_test?unix_socket=/tmp/mysql.sock" pytest
"""

import json
import os
from typing import Optional

import dotenv
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Tests never read the real .env: db.py loads it on import, which would turn on
# the real AI provider (and anything else configured there) for every test.
dotenv.load_dotenv = lambda *args, **kwargs: False

# Production requires an explicit database target. Tests install an explicit
# in-memory value before importing the application and replace its engine below.
os.environ.setdefault("DATABASE_URL", "sqlite://")

from stock_manager.api.db import get_session  # noqa: E402
from stock_manager.api.main import app, create_app  # noqa: E402
from stock_manager.api.models import Base  # noqa: E402
from stock_manager.api.schema_version import stamp_head  # noqa: E402

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


def _test_client(app, db_session, monkeypatch):
    """Use an isolated SQLite database and the test bearer token."""
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


@pytest.fixture()
def client(db_session, monkeypatch):
    yield from _test_client(app, db_session, monkeypatch)


@pytest.fixture()
def docs_client(db_session, monkeypatch):
    monkeypatch.setenv("API_DOCS_ENABLED", "true")
    yield from _test_client(create_app(), db_session, monkeypatch)


# ─── AI (never calls the real provider) ──────────────────────────


AI_ENV_VARS = (
    "AI_RECIPE_ENABLED", "AI_API_KEY", "AI_BASE_URL", "AI_VISION_ENABLED",
    "AI_IMAGE_DETAIL", "RECEIPT_PRODUCT_LOOKUP_PROVIDER",
    "AI_ASR_PROVIDER", "AI_ASR_TIMEOUT_SECONDS",
)


def _refuse_real_ai(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"test tried to call the real AI provider: {request.url}")


@pytest.fixture(autouse=True)
def _fresh_ai_config(monkeypatch):
    """Each test reads the AI settings from its own environment (#66).

    AI is off unless the test turns it on, and any AI request that is not
    answered by `fake_ai` fails the test instead of reaching the network.
    """
    from stock_manager.api import ai_client, asr_client

    for var in AI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(ai_client, "_transport", httpx.MockTransport(_refuse_real_ai))
    monkeypatch.setattr(asr_client, "_transport", httpx.MockTransport(_refuse_real_ai))
    ai_client._config = None
    yield
    ai_client._config = None


def sse_body(content: str, chunk_size: int = 5, finish_reason: str = "stop",
             usage: Optional[dict] = None, reasoning: str = "") -> bytes:
    """A streamed chat completion, as the provider sends it."""
    events = [{"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}]}]
    for i in range(0, len(reasoning), chunk_size):
        events.append({"choices": [{"index": 0, "delta": {"reasoning_content": reasoning[i:i + chunk_size]}}]})
    for i in range(0, len(content), chunk_size):
        events.append({"choices": [{"index": 0, "delta": {"content": content[i:i + chunk_size]}}]})
    events.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}]})
    events.append({"choices": [], "usage": usage or {"prompt_tokens": 100, "completion_tokens": 50}})
    lines = [f"data: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events] + ["data: [DONE]\n\n"]
    return "".join(lines).encode()


class FakeAI:
    """The AI provider as seen through httpx.MockTransport.

    - `reply`: message content returned by default (a JSON string).
    - `responses`: optional queue, one entry per call: an httpx.Response, an
      exception (raised as a transport error), or a content string.
    - `requests`: the JSON payloads sent to the provider.

    A content string is sent as server-sent events in small chunks when the
    request asks for a stream (the default), else as one JSON body.
    """

    def __init__(self):
        self.reply = json.dumps({"ideas": [{"title": "番茄炒蛋", "matched_ingredients": ["番茄"]}]})
        self.responses: list = []
        self.requests: list[dict] = []
        self.chunk_size = 5
        self.finish_reason = "stop"

    @property
    def prompts(self) -> list:
        """The user message of each request."""
        return [r["messages"][1]["content"] for r in self.requests]

    @property
    def system_prompts(self) -> list:
        return [r["messages"][0]["content"] for r in self.requests]

    def handle(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        self.requests.append(payload)
        item = self.responses.pop(0) if self.responses else self.reply
        if isinstance(item, Exception):
            raise item
        if isinstance(item, httpx.Response):
            return item
        if payload.get("stream"):
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"},
                content=sse_body(item, self.chunk_size, self.finish_reason),
            )
        return httpx.Response(200, json={"choices": [
            {"message": {"content": item}, "finish_reason": self.finish_reason}
        ]})


@pytest.fixture()
def fake_ai(monkeypatch):
    """AI enabled, answered by FakeAI instead of the network."""
    from stock_manager.api import ai_client

    fake = FakeAI()
    monkeypatch.setenv("AI_RECIPE_ENABLED", "true")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_BASE_URL", "http://ai.invalid")
    for var in ("AI_MODEL", "AI_TEMPERATURE", "AI_TIMEOUT_SECONDS", "AI_MAX_RETRIES",
                "AI_TOTAL_TIMEOUT_SECONDS", "AI_IMAGE_TIMEOUT_SECONDS", "AI_IMAGE_TOTAL_TIMEOUT_SECONDS",
                "AI_IMAGE_THINKING"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(ai_client, "_transport", httpx.MockTransport(fake.handle))
    ai_client.reload_config()
    return fake

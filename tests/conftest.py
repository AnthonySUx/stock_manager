"""Pytest configuration: test database and FastAPI client fixtures.

Tests run on in-memory SQLite by default. Set TEST_DATABASE_URL to run them
on another database, e.g. a throwaway MySQL database (all tables in it are
dropped after each test):

    TEST_DATABASE_URL="mysql+pymysql://root@localhost/stock_manager_test?unix_socket=/tmp/mysql.sock" pytest
"""

import os

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

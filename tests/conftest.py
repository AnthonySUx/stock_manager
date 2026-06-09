"""Pytest configuration: test database and FastAPI client fixtures."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from stock_manager.api.db import get_session
from stock_manager.api.main import app
from stock_manager.api.models import Base

TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture()
def db_session():
    """Provide a clean database session for each test."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    from stock_manager.api.category_services import seed_default_categories
    seed_default_categories(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client(db_session, monkeypatch):
    """Provide a FastAPI TestClient with an isolated SQLite database."""
    # Must patch before TestClient enters startup lifespan
    monkeypatch.setattr("stock_manager.api.main.engine", test_engine)

    def override_get_session():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()

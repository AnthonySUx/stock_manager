"""Database connection and session management for the API."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

# Load .env file from project root
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


def require_database_url(value: str | None, docker_host_port: str | None = None) -> str:
    """Return an explicit database URL or fail before connecting anywhere.

    A generic localhost fallback can silently connect to an unrelated MySQL
    instance when the Docker database is stopped. Requiring configuration
    turns that data-source switch into an actionable startup error.
    """
    url = (value or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required. Copy .env.example to .env and keep its "
            "Docker URL, or set DATABASE_URL explicitly for your database."
        )
    if docker_host_port:
        try:
            expected_port = int(docker_host_port)
        except ValueError as error:
            raise RuntimeError("MYSQL_HOST_PORT must be an integer") from error
        parsed = make_url(url)
        if parsed.host in {"127.0.0.1", "localhost"} and (parsed.port or 3306) != expected_port:
            raise RuntimeError(
                "DATABASE_URL port must match MYSQL_HOST_PORT. Update both values in .env "
                "so the API and Docker Compose use the same database."
            )
    return url


DATABASE_URL = require_database_url(
    os.getenv("DATABASE_URL"), docker_host_port=os.getenv("MYSQL_HOST_PORT")
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Session:
    """Dependency that yields a database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

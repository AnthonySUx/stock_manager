"""Database connection and session management for the API."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Load .env file from project root
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://stock_user:stock_password@127.0.0.1:3306/stock_manager",
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

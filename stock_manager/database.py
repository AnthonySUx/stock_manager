"""SQLite database setup for Stock Manager."""

from pathlib import Path
import sqlite3
from typing import Any

DEFAULT_DATABASE_PATH = Path("stock.db")
DEFAULT_REMINDER_DAYS = "2"


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        owner TEXT NOT NULL,
        purchase_date TEXT NOT NULL,
        quantity_value REAL NOT NULL,
        quantity_unit TEXT NOT NULL,
        location TEXT NOT NULL,
        unopened_expiration_date TEXT NOT NULL,
        opened_expiration_date TEXT,
        opened_date TEXT,
        current_expiration_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'consumed', 'expiring soon', 'expired')),
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS restock_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        quantity_value REAL,
        quantity_unit TEXT,
        source_item_id INTEGER,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'done')),
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        done_at TEXT,
        FOREIGN KEY (source_item_id) REFERENCES items (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


DEFAULT_SETTINGS = {
    "expiration_reminder_days": DEFAULT_REMINDER_DAYS,
    "shopping_weekday": "",
    "email_enabled": "false",
}


def initialize_database(database_path: Path = DEFAULT_DATABASE_PATH) -> Path:
    """Create the SQLite database and required tables if they do not exist."""
    resolved_path = database_path.expanduser().resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(resolved_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)

        connection.executemany(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES (?, ?)
            """,
            DEFAULT_SETTINGS.items(),
        )

    return resolved_path


def add_item(item: dict[str, Any], database_path: Path = DEFAULT_DATABASE_PATH) -> int:
    """Insert one stock item and return its database id."""
    resolved_path = initialize_database(database_path)

    with sqlite3.connect(resolved_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO items (
                name,
                category,
                owner,
                purchase_date,
                quantity_value,
                quantity_unit,
                location,
                unopened_expiration_date,
                opened_expiration_date,
                opened_date,
                current_expiration_date,
                status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["name"],
                item["category"],
                item["owner"],
                item["purchase_date"],
                item["quantity_value"],
                item["quantity_unit"],
                item["location"],
                item["unopened_expiration_date"],
                item["opened_expiration_date"],
                item["opened_date"],
                item["current_expiration_date"],
                item["status"],
                item["notes"],
            ),
        )

    return int(cursor.lastrowid)


def list_items(
    *,
    category: str | None = None,
    owner: str | None = None,
    location: str | None = None,
    status: str | None = None,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    """Return stock items that match the optional filters."""
    resolved_path = initialize_database(database_path)
    query = """
        SELECT
            id,
            name,
            category,
            owner,
            purchase_date,
            quantity_value,
            quantity_unit,
            location,
            current_expiration_date,
            status,
            notes
        FROM items
        WHERE 1 = 1
    """
    parameters: list[str] = []

    if category is not None:
        query += " AND lower(category) = lower(?)"
        parameters.append(category)
    if owner is not None:
        query += " AND lower(owner) = lower(?)"
        parameters.append(owner)
    if location is not None:
        query += " AND lower(location) = lower(?)"
        parameters.append(location)
    if status is not None:
        query += " AND status = ?"
        parameters.append(status)

    query += " ORDER BY id"

    with sqlite3.connect(resolved_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()

    return rows


def search_items(
    keyword: str,
    *,
    owner: str | None = None,
    location: str | None = None,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    """Return stock items matching a keyword and optional filters."""
    resolved_path = initialize_database(database_path)
    query = """
        SELECT
            id,
            name,
            category,
            owner,
            purchase_date,
            quantity_value,
            quantity_unit,
            location,
            current_expiration_date,
            status,
            notes
        FROM items
        WHERE (
            lower(name) LIKE lower(?)
            OR lower(category) LIKE lower(?)
            OR lower(owner) LIKE lower(?)
            OR lower(location) LIKE lower(?)
            OR lower(coalesce(notes, '')) LIKE lower(?)
        )
    """
    keyword_pattern = f"%{keyword}%"
    parameters: list[str] = [keyword_pattern] * 5

    if owner is not None:
        query += " AND lower(owner) = lower(?)"
        parameters.append(owner)
    if location is not None:
        query += " AND lower(location) = lower(?)"
        parameters.append(location)

    query += " ORDER BY id"

    with sqlite3.connect(resolved_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()

    return rows

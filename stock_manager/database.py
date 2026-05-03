"""SQLite database setup for Stock Manager."""

from datetime import date, timedelta
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


def _resolve_database_path(database_path: Path = DEFAULT_DATABASE_PATH) -> Path:
    """Return the absolute path used for a database file."""
    return database_path.expanduser().resolve()


def connect_database(database_path: Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with project-wide connection settings."""
    resolved_path = _resolve_database_path(database_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(resolved_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path: Path = DEFAULT_DATABASE_PATH) -> Path:
    """Create the SQLite database and required tables if they do not exist."""
    resolved_path = _resolve_database_path(database_path)

    with connect_database(resolved_path) as connection:
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

    with connect_database(resolved_path) as connection:
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


def get_item(item_id: int, database_path: Path = DEFAULT_DATABASE_PATH) -> sqlite3.Row | None:
    """Return one stock item by id, or None if it does not exist."""
    resolved_path = initialize_database(database_path)

    with connect_database(resolved_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT
                id,
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
            FROM items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()

    return row


def add_restock_item(item: dict[str, Any], database_path: Path = DEFAULT_DATABASE_PATH) -> int:
    """Insert one restock item and return its database id."""
    resolved_path = initialize_database(database_path)

    with connect_database(resolved_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO restock_items (
                name,
                category,
                quantity_value,
                quantity_unit,
                status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item["name"],
                item["category"],
                item["quantity_value"],
                item["quantity_unit"],
                item["status"],
                item["notes"],
            ),
        )

    return int(cursor.lastrowid)


def _get_expiration_warning_days(connection: sqlite3.Connection) -> int:
    """Return the configured expiration warning window in days."""
    row = connection.execute(
        """
        SELECT value
        FROM settings
        WHERE key = 'expiration_reminder_days'
        """
    ).fetchone()

    if row is None:
        return int(DEFAULT_REMINDER_DAYS)

    try:
        warning_days = int(row[0])
    except ValueError:
        return int(DEFAULT_REMINDER_DAYS)

    return max(warning_days, 0)


def _calculate_status(
    quantity_value: float,
    current_expiration_date: str,
    warning_days: int,
    today: date,
) -> str:
    """Calculate the current stock status from quantity and expiration date."""
    if quantity_value <= 0:
        return "consumed"

    if current_expiration_date == "infinite":
        return "active"

    try:
        expiration_date = date.fromisoformat(current_expiration_date)
    except ValueError:
        return "active"

    if expiration_date < today:
        return "expired"

    if expiration_date <= today + timedelta(days=warning_days):
        return "expiring soon"

    return "active"


def refresh_item_statuses(
    database_path: Path = DEFAULT_DATABASE_PATH,
    *,
    ensure_schema: bool = True,
) -> int:
    """Refresh item statuses and return the number of changed rows."""
    if ensure_schema:
        resolved_path = initialize_database(database_path)
    else:
        resolved_path = _resolve_database_path(database_path)

    today = date.today()
    changed_rows = 0

    with connect_database(resolved_path) as connection:
        warning_days = _get_expiration_warning_days(connection)
        rows = connection.execute(
            """
            SELECT id, quantity_value, current_expiration_date, status
            FROM items
            """
        ).fetchall()

        for item_id, quantity_value, current_expiration_date, current_status in rows:
            new_status = _calculate_status(
                quantity_value,
                current_expiration_date,
                warning_days,
                today,
            )
            if new_status == current_status:
                continue

            connection.execute(
                """
                UPDATE items
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_status, item_id),
            )
            changed_rows += 1

    return changed_rows


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
    refresh_item_statuses(resolved_path, ensure_schema=False)
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

    with connect_database(resolved_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()

    return rows


def search_items(
    keyword: str,
    *,
    category: str | None = None,
    owner: str | None = None,
    location: str | None = None,
    status: str | None = None,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    """Return stock items matching a keyword and optional filters."""
    resolved_path = initialize_database(database_path)
    refresh_item_statuses(resolved_path, ensure_schema=False)
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
    if category is not None:
        query += " AND lower(category) = lower(?)"
        parameters.append(category)
    if status is not None:
        query += " AND status = ?"
        parameters.append(status)

    query += " ORDER BY id"

    with connect_database(resolved_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()

    return rows


def list_restock_items(
    *,
    status: str | None = None,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    """Return restock items that match the optional status filter."""
    resolved_path = initialize_database(database_path)
    query = """
        SELECT
            id,
            name,
            category,
            quantity_value,
            quantity_unit,
            source_item_id,
            status,
            notes,
            created_at,
            done_at
        FROM restock_items
        WHERE 1 = 1
    """
    parameters: list[str] = []

    if status is not None:
        query += " AND status = ?"
        parameters.append(status)

    query += """
        ORDER BY
            CASE status WHEN 'pending' THEN 0 ELSE 1 END,
            id
    """

    with connect_database(resolved_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()

    return rows


def get_restock_item(item_id: int, database_path: Path = DEFAULT_DATABASE_PATH) -> sqlite3.Row | None:
    """Return one restock item by id, or None if it does not exist."""
    resolved_path = initialize_database(database_path)

    with connect_database(resolved_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT
                id,
                name,
                category,
                quantity_value,
                quantity_unit,
                source_item_id,
                status,
                notes,
                created_at,
                done_at
            FROM restock_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()

    return row


def mark_restock_item_done(item_id: int, database_path: Path = DEFAULT_DATABASE_PATH) -> bool:
    """Mark one restock item as done and return whether it changed."""
    resolved_path = initialize_database(database_path)

    with connect_database(resolved_path) as connection:
        cursor = connection.execute(
            """
            UPDATE restock_items
            SET status = 'done', done_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status != 'done'
            """,
            (item_id,),
        )

    return cursor.rowcount > 0


def update_restock_item_quantity(
    item_id: int,
    quantity_value: float,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> bool:
    """Update the remaining quantity for one pending restock item."""
    resolved_path = initialize_database(database_path)

    with connect_database(resolved_path) as connection:
        cursor = connection.execute(
            """
            UPDATE restock_items
            SET quantity_value = ?
            WHERE id = ? AND status = 'pending'
            """,
            (quantity_value, item_id),
        )

    return cursor.rowcount > 0


def delete_restock_item(item_id: int, database_path: Path = DEFAULT_DATABASE_PATH) -> bool:
    """Delete one restock item and return whether it existed."""
    resolved_path = initialize_database(database_path)

    with connect_database(resolved_path) as connection:
        cursor = connection.execute(
            """
            DELETE FROM restock_items
            WHERE id = ?
            """,
            (item_id,),
        )

    return cursor.rowcount > 0

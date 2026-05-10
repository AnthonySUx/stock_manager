"""User-level configuration for Stock Manager."""

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_DATABASE_PATH = Path("stock.db")
DEFAULT_REMINDER_DAYS = "2"

APP_CONFIG_DIR = Path(os.environ.get("STOCK_MANAGER_CONFIG_DIR", Path.home() / ".stock_manager"))
SETTINGS_CONFIG_PATH = APP_CONFIG_DIR / "settings.json"
LEGACY_DEFAULT_DATABASE_CONFIG_PATH = APP_CONFIG_DIR / "default_database"

DEFAULT_GLOBAL_SETTINGS = {
    "default_database": str(DEFAULT_DATABASE_PATH),
    "expiration_reminder_days": DEFAULT_REMINDER_DAYS,
}


def _load_settings_file() -> dict[str, Any]:
    """Load the global settings file, returning an empty dict if it is missing or invalid."""
    try:
        content = SETTINGS_CONFIG_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}

    try:
        settings = json.loads(content)
    except json.JSONDecodeError:
        return {}

    if not isinstance(settings, dict):
        return {}
    return settings


def load_global_settings() -> dict[str, str]:
    """Return global settings with defaults and legacy default-database migration."""
    settings = DEFAULT_GLOBAL_SETTINGS.copy()
    loaded_settings = _load_settings_file()

    for key in DEFAULT_GLOBAL_SETTINGS:
        value = loaded_settings.get(key)
        if value is not None:
            settings[key] = str(value)

    if (
        "default_database" not in loaded_settings
        and LEGACY_DEFAULT_DATABASE_CONFIG_PATH.exists()
    ):
        legacy_database = LEGACY_DEFAULT_DATABASE_CONFIG_PATH.read_text(encoding="utf-8").strip()
        if legacy_database:
            settings["default_database"] = legacy_database

    return settings


def save_global_settings(settings: dict[str, str]) -> None:
    """Persist supported global settings."""
    current_settings = load_global_settings()
    for key in DEFAULT_GLOBAL_SETTINGS:
        if key in settings:
            current_settings[key] = str(settings[key])

    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_CONFIG_PATH.write_text(
        json.dumps(current_settings, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def get_default_database_path() -> Path:
    """Return the configured default database path."""
    value = load_global_settings()["default_database"].strip()
    if not value:
        return DEFAULT_DATABASE_PATH
    return Path(value).expanduser()


def normalize_database_path(database_path: str) -> Path:
    """Return an absolute database path from user input."""
    configured_path = Path(database_path).expanduser()
    if not configured_path.is_absolute():
        configured_path = Path.cwd() / configured_path
    return configured_path.resolve()


def get_expiration_reminder_days() -> int:
    """Return the global expiration reminder window in days."""
    value = load_global_settings()["expiration_reminder_days"]
    try:
        days = int(value)
    except ValueError:
        return int(DEFAULT_REMINDER_DAYS)
    return max(days, 0)

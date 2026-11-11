"""Database schema version check at startup (#49).

The API no longer creates or alters tables itself. Schema changes are
Alembic migrations (`migrations/`), applied with `alembic upgrade head`.
At startup the API only checks that the database is at the newest
revision, and refuses to start otherwise, saying what to run.
"""
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
UPGRADE_HINT = (
    "Run `alembic upgrade head` (or `python3 -m alembic upgrade head`) in the project "
    "directory, then start the API again."
)


def alembic_config() -> Config:
    """Alembic config for this project (alembic.ini at the project root)."""
    return Config(str(ALEMBIC_INI))


def script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config())


def stamp_head(connection) -> None:
    """Record the newest revision without running migrations (tests only:
    their tables come from Base.metadata.create_all)."""
    MigrationContext.configure(connection).stamp(script_directory(), "head")


def check_schema_current(engine) -> None:
    """Raise RuntimeError unless the database is at the newest revision."""
    scripts = script_directory()
    head = scripts.get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
        tables = set(inspect(connection).get_table_names()) - {"alembic_version"}

    if current == head:
        return
    if current is None and tables:
        problem = (
            "The database was created before migrations were added (no Alembic revision). "
            "`alembic upgrade head` adopts it once: existing tables and data are kept."
        )
    elif current is None:
        problem = "The database has no tables yet."
    elif current not in {rev.revision for rev in scripts.walk_revisions()}:
        raise RuntimeError(
            f"Database schema revision {current!r} is not known to this code (is the code "
            f"older than the database?). Update the code, or check `alembic history`."
        )
    else:
        problem = f"The database is at schema revision {current!r}; this code needs {head!r}."
    raise RuntimeError(f"{problem} {UPGRADE_HINT}")

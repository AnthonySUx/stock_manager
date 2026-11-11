"""Issue #49: Alembic migrations and the startup schema check.

Runs on a throwaway SQLite file, or on TEST_DATABASE_URL when that points at
another database (it must be an empty, throwaway database: tables are
dropped).
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from stock_manager.api import schema_version
from stock_manager.api.models import Base
from tests.conftest import IS_SQLITE, TEST_DATABASE_URL

APP_TABLES = set(Base.metadata.tables)


def _drop_everything(engine):
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture()
def fresh_db(tmp_path):
    """(url, engine) for an empty database."""
    url = f"sqlite:///{tmp_path / 'migrations.db'}" if IS_SQLITE else TEST_DATABASE_URL
    engine = create_engine(url)
    _drop_everything(engine)
    yield url, engine
    _drop_everything(engine)
    engine.dispose()


def _alembic(url):
    config = schema_version.alembic_config()
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def _schema_diff(engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True, "compare_server_default": True})
        return compare_metadata(context, Base.metadata)


def _revision(engine):
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _head():
    return schema_version.script_directory().get_current_head()


# ─── Migrations ───────────────────────────────────────────────────


def test_upgrade_creates_exactly_the_model_schema(fresh_db):
    url, engine = fresh_db

    command.upgrade(_alembic(url), "head")

    assert set(inspect(engine).get_table_names()) == APP_TABLES | {"alembic_version"}
    assert _schema_diff(engine) == []
    assert _revision(engine) == _head()


def test_upgrade_adopts_a_database_created_before_alembic(fresh_db):
    url, engine = fresh_db
    Base.metadata.create_all(engine)  # what startup used to do
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO settings (`key`, value, updated_at) VALUES ('expiration_reminder_days', '5', CURRENT_TIMESTAMP)"
        ))

    command.upgrade(_alembic(url), "head")

    assert _revision(engine) == _head()
    assert _schema_diff(engine) == []
    with engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM settings")).scalar() == "5"


def test_upgrade_twice_is_a_no_op(fresh_db):
    url, engine = fresh_db
    command.upgrade(_alembic(url), "head")
    command.upgrade(_alembic(url), "head")
    assert _revision(engine) == _head()


def test_downgrade_to_base_removes_the_tables(fresh_db):
    url, engine = fresh_db
    command.upgrade(_alembic(url), "head")

    command.downgrade(_alembic(url), "base")

    assert set(inspect(engine).get_table_names()) - {"alembic_version"} == set()
    assert _revision(engine) is None


def test_offline_sql_creates_every_table(fresh_db, capsys):
    url, _ = fresh_db
    command.upgrade(_alembic(url), "head", sql=True)
    sql = capsys.readouterr().out
    for table in APP_TABLES:
        assert f"CREATE TABLE {table}" in sql


def test_migrations_have_a_single_head():
    assert len(schema_version.script_directory().get_heads()) == 1


# ─── Startup check ────────────────────────────────────────────────


class TestStartupCheck:
    def test_at_head_passes(self, fresh_db):
        url, engine = fresh_db
        command.upgrade(_alembic(url), "head")
        schema_version.check_schema_current(engine)

    def test_empty_database(self, fresh_db):
        _, engine = fresh_db
        with pytest.raises(RuntimeError, match="no tables yet.*alembic upgrade head"):
            schema_version.check_schema_current(engine)

    def test_database_created_before_alembic(self, fresh_db):
        _, engine = fresh_db
        Base.metadata.create_all(engine)
        with pytest.raises(RuntimeError, match="before migrations.*alembic upgrade head"):
            schema_version.check_schema_current(engine)

    def test_database_behind_head(self, fresh_db, monkeypatch):
        url, engine = fresh_db
        command.upgrade(_alembic(url), "head")
        real = schema_version.script_directory()
        current = real.get_current_head()

        class NewerScripts:
            def get_current_head(self):
                return "9999"

            def walk_revisions(self):
                return real.walk_revisions()

        monkeypatch.setattr(schema_version, "script_directory", lambda: NewerScripts())
        with pytest.raises(RuntimeError, match=f"revision '{current}'.*needs '9999'.*alembic upgrade head"):
            schema_version.check_schema_current(engine)

    def test_unknown_revision(self, fresh_db):
        _, engine = fresh_db
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('abc123')"))
        with pytest.raises(RuntimeError, match="'abc123' is not known"):
            schema_version.check_schema_current(engine)

    def test_api_refuses_to_start_on_an_old_database(self, fresh_db, monkeypatch):
        from stock_manager.api.main import app

        _, engine = fresh_db
        Base.metadata.create_all(engine)
        monkeypatch.setattr("stock_manager.api.main.engine", engine)
        monkeypatch.setenv("API_TOKEN", "t")

        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            with TestClient(app):
                pass
        # Startup must not have created or changed anything.
        assert _revision(engine) is None

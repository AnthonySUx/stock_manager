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
from sqlalchemy import Float, Numeric, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

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


def _schema_diff(engine, tables=None):
    def include_object(obj, name, type_, reflected, compare_to):
        if tables is None:
            return True
        return (name if type_ == "table" else obj.table.name) in tables

    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={
            "compare_type": True,
            "compare_server_default": True,
            "include_object": include_object,
        })
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
    assert "ALTER TABLE categories ADD COLUMN default_shelf_life_days INTEGER" in sql
    assert "UPDATE categories SET default_shelf_life_days" in sql


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


# ─── 0002 (#66) ───────────────────────────────────────────────────


def test_0002_converts_ai_saved_recipes_and_drops_the_ai_table(fresh_db):
    url, engine = fresh_db
    command.upgrade(_alembic(url), "0001")
    assert "ai_recipe_recommendations" in inspect(engine).get_table_names()
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO recipes (source_type, source_name, title, is_user_created, created_at, updated_at) "
            "VALUES ('ai_saved', 'AI', 'AI 菜', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
            "('howtocook', 'HowToCook', '口水鸡', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))

    command.upgrade(_alembic(url), "0002")

    assert "ai_recipe_recommendations" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT title, source_type, is_user_created FROM recipes ORDER BY title"
        )).all()
    assert [(r[0], r[1], bool(r[2])) for r in rows] == [
        ("AI 菜", "user", True), ("口水鸡", "howtocook", False),
    ]

    command.downgrade(_alembic(url), "0001")
    assert "ai_recipe_recommendations" in inspect(engine).get_table_names()
    assert _revision(engine) == "0001"


# ─── 0003 (legacy structured categories adoption) ────────────────


def test_0003_repairs_legacy_category_columns_without_losing_rows(fresh_db):
    url, engine = fresh_db
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE categories ("
            "id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, slug VARCHAR(100) NOT NULL UNIQUE, "
            "parent_id INTEGER, recipe_usage VARCHAR(20) NOT NULL DEFAULT 'never', "
            "is_system BOOLEAN NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0, "
            "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO categories (id, name, slug) VALUES "
            "(1, '食品', 'food'), (8, '其他', 'other'), (9, '蔬菜', 'vegetables'), "
            "(14, '乳制品', 'dairy')"
        ))
        connection.execute(text(
            "CREATE TABLE items ("
            "id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, category VARCHAR(100) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO items (id, name, category) VALUES "
            "(1, '牛奶', '乳制品'), (2, '番茄', '蔬菜'), (3, '旧记录', '不存在的分类')"
        ))
        connection.execute(text(
            "CREATE TABLE restock_items ("
            "id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, category VARCHAR(100))"
        ))
        connection.execute(text(
            "INSERT INTO restock_items (id, name, category) VALUES "
            "(1, '酸奶', '乳制品'), (2, '待分类', '不存在的分类')"
        ))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('0002')"))

    command.upgrade(_alembic(url), "0003")

    inspector = inspect(engine)
    assert {column["name"] for column in inspector.get_columns("items")} == {
        "id", "name", "category_id",
    }
    assert {column["name"] for column in inspector.get_columns("restock_items")} == {
        "id", "name", "category_id",
    }
    with engine.connect() as connection:
        items = connection.execute(text(
            "SELECT name, category_id FROM items ORDER BY id"
        )).all()
        restock = connection.execute(text(
            "SELECT name, category_id FROM restock_items ORDER BY id"
        )).all()
        uncategorized = connection.execute(text(
            "SELECT id FROM categories WHERE slug = 'uncategorized'"
        )).scalar_one()
    assert items == [("牛奶", 14), ("番茄", 9), ("旧记录", uncategorized)]
    assert restock == [("酸奶", 14), ("待分类", None)]
    assert _revision(engine) == "0003"


# ─── 0004 (category shelf-life defaults) ──────────────────────────


def _shelf_life_by_slug(engine):
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT slug, default_shelf_life_days FROM categories"))
        return dict(rows.tuples().all())


def test_0004_backfills_every_system_category(fresh_db):
    from stock_manager.api.category_services import DEFAULT_CATEGORIES

    url, engine = fresh_db
    config = _alembic(url)
    command.upgrade(config, "0003")
    categories = [{"name": name, "slug": slug} for name, slug, *_ in DEFAULT_CATEGORIES]
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO categories (name, slug, is_system) VALUES (:name, :slug, 1)"),
            categories,
        )

    command.upgrade(config, "0004")

    # PR 2 intake plan defaults. Other system categories should stay NULL.
    expected = dict.fromkeys(category["slug"] for category in categories)
    expected.update({
        "vegetables": 7,
        "fruit": 7,
        "meat": 3,
        "seafood": 2,
        "eggs": 30,
        "dairy": 7,
        "staples_grains": 180,
        "soy_products": 5,
        "seasonings_spices": 365,
        "baking": 180,
        "drinks": 180,
        "snacks": 90,
        "frozen_food": 90,
        "canned_packaged": 365,
        "ready_to_eat": 2,
        "baby_food": 30,
        "formula": 365,
        "pet_food": 180,
        "pet_treats": 180,
    })
    assert _shelf_life_by_slug(engine) == expected


def test_0004_upgrade_and_downgrade_preserve_categories(fresh_db):
    url, engine = fresh_db
    config = _alembic(url)
    command.upgrade(config, "0003")
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO categories (name, slug, is_system) VALUES "
            "('Vegetables', 'vegetables', 1), ('Formula', 'formula', 1), "
            "('Pet food', 'pet_food', 1), ('Medication', 'medicine', 1), "
            "('Custom drink', 'drinks', 0)"
        ))

    command.upgrade(config, "0004")
    expected = {"vegetables": 7, "formula": 365, "pet_food": 180, "medicine": None, "drinks": None}
    assert _revision(engine) == "0004"
    assert _shelf_life_by_slug(engine) == expected

    command.downgrade(config, "0003")
    assert _revision(engine) == "0003"
    assert "default_shelf_life_days" not in {c["name"] for c in inspect(engine).get_columns("categories")}
    with engine.connect() as connection:
        assert set(connection.execute(text("SELECT slug FROM categories")).scalars()) == expected.keys()

    command.upgrade(config, "0004")
    assert _shelf_life_by_slug(engine) == expected


def test_0004_adopts_existing_column_and_preserves_configured_values(fresh_db):
    url, engine = fresh_db
    config = _alembic(url)
    command.upgrade(config, "0003")
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE categories ADD COLUMN default_shelf_life_days INTEGER"))
        connection.execute(text(
            "INSERT INTO categories (name, slug, is_system, default_shelf_life_days) VALUES "
            "('Vegetables', 'vegetables', 1, 12), ('Eggs', 'eggs', 1, NULL), "
            "('Custom dairy', 'dairy', 0, NULL), ('Custom tea', 'custom-tea', 0, 50)"
        ))

    command.upgrade(config, "0004")

    assert _shelf_life_by_slug(engine) == {
        "vegetables": 12, "eggs": 30, "dairy": None, "custom-tea": 50,
    }


def test_0005_receipt_alias_schema_upgrades_and_downgrades(fresh_db):
    url, engine = fresh_db
    config = _alembic(url)
    command.upgrade(config, "0004")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO categories (name, slug) VALUES ('Existing', 'existing')"))
    assert "receipt_item_aliases" not in inspect(engine).get_table_names()

    command.upgrade(config, "0005")
    inspector = inspect(engine)
    assert _revision(engine) == "0005"
    assert _schema_diff(engine, tables={"receipt_item_aliases", "receipt_alias_names"}) == []
    assert "family_id" not in {column["name"] for column in inspector.get_columns("receipt_item_aliases")}
    assert {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("receipt_item_aliases")} == {
        ("store_key", "raw_name_normalized"),
    }
    alias_fk = inspector.get_foreign_keys("receipt_item_aliases")[0]
    assert (alias_fk["referred_table"], alias_fk["options"]["ondelete"]) == ("categories", "SET NULL")
    name_fk = inspector.get_foreign_keys("receipt_alias_names")[0]
    assert (name_fk["referred_table"], name_fk["options"]["ondelete"]) == ("receipt_item_aliases", "CASCADE")
    assert inspector.get_pk_constraint("receipt_alias_names")["constrained_columns"] == ["alias_id", "confirmed_item_name"]

    command.downgrade(config, "0004")
    assert _revision(engine) == "0004"
    assert {"receipt_alias_names", "receipt_item_aliases"}.isdisjoint(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.execute(text("SELECT name FROM categories WHERE slug = 'existing'")).scalar_one() == "Existing"


# ─── 0006 (status constraints) ───────────────────────────────────


def _seed_status_rows(engine):
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO categories (id, name, slug) VALUES (1, 'Food', 'food')"))
        connection.execute(text(
            "INSERT INTO items (id, name, category_id, owner, purchase_date, quantity_value, "
            "quantity_unit, location, unopened_expiration_date, current_expiration_date, status) "
            "VALUES (1, 'Tomato', 1, 'Alex', '2026-11-24', 2, 'pcs', 'Fridge', "
            "'infinite', 'infinite', 'active')"
        ))
        connection.execute(text(
            "INSERT INTO restock_items (id, name, category_id, source_item_id, status) VALUES "
            "(1, 'Tomato', 1, 1, 'pending'), (2, 'Milk', NULL, NULL, 'done')"
        ))


def _status_constraint_names(engine, table):
    return {check["name"] for check in inspect(engine).get_check_constraints(table)}


def test_0006_rejects_invalid_rows_before_changing_either_table(fresh_db):
    url, engine = fresh_db
    config = _alembic(url)
    command.upgrade(config, "0005")
    _seed_status_rows(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE items SET status = 'Active'"))
        connection.execute(text("UPDATE restock_items SET status = 'banana'"))

    with pytest.raises(RuntimeError, match=r"invalid status rows \(items: 1, restock_items: 2\)"):
        command.upgrade(config, "0006")

    assert _revision(engine) == "0005"
    assert "ck_items_status" not in _status_constraint_names(engine, "items")
    assert "ck_restock_items_status" not in _status_constraint_names(engine, "restock_items")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT status FROM items")).scalars().all() == ["Active"]
        assert connection.execute(text("SELECT status FROM restock_items")).scalars().all() == [
            "banana", "banana",
        ]


def test_0006_status_checks_upgrade_and_downgrade_preserve_rows(fresh_db):
    url, engine = fresh_db
    config = _alembic(url)
    command.upgrade(config, "0005")
    _seed_status_rows(engine)

    command.upgrade(config, "0006")
    assert _revision(engine) == "0006"
    for table, valid_values in (
        ("items", ("active", "expiring soon", "expired", "consumed")),
        ("restock_items", ("pending", "done")),
    ):
        assert f"ck_{table}_status" in _status_constraint_names(engine, table)
        update = text(f"UPDATE {table} SET status = :status WHERE id = 1")
        with engine.begin() as connection:
            for status in reversed(valid_values):
                connection.execute(update, {"status": status})
        for status in ("banana", valid_values[0].upper(), f"{valid_values[0]} "):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(update, {"status": status})

    with engine.connect() as connection:
        assert connection.execute(text("SELECT status, category_id FROM items")).one() == (
            "active", 1,
        )
        assert connection.execute(text(
            "SELECT status, category_id, source_item_id FROM restock_items ORDER BY id"
        )).all() == [("pending", 1, 1), ("done", None, None)]

    command.downgrade(config, "0005")
    assert _revision(engine) == "0005"
    with engine.begin() as connection:
        for table in ("items", "restock_items"):
            assert f"ck_{table}_status" not in _status_constraint_names(engine, table)
            connection.execute(text(f"UPDATE {table} SET status = 'legacy' WHERE id = 1"))
            assert connection.execute(text(
                f"SELECT status, category_id FROM {table} WHERE id = 1"
            )).one() == ("legacy", 1)
        assert connection.execute(text(
            "SELECT source_item_id FROM restock_items WHERE id = 1"
        )).scalar_one() == 1


def test_0007_upgrade_and_downgrade_preserve_status_checks_and_rows(fresh_db):
    url, engine = fresh_db
    config = _alembic(url)
    command.upgrade(config, "0006")
    _seed_status_rows(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE items SET quantity_value = 1.23456 WHERE id = 1"))
        connection.execute(text(
            "UPDATE restock_items SET quantity_value = 2.34567, "
            "created_at = '2026-11-20 10:00:00' WHERE id = 1"
        ))
        connection.execute(text(
            "INSERT INTO recipes (id, source_type, source_name, title, is_user_created) "
            "VALUES (1, 'user', 'User', 'Soup', 1)"
        ))
        connection.execute(text(
            "INSERT INTO recipe_favorites (id, recipe_id, note) VALUES "
            "(1, 1, 'First'), (2, 1, 'Duplicate')"
        ))

    command.upgrade(config, "0007")

    for revision in ("0007", "0006"):
        assert _revision(engine) == revision
        inspector = inspect(engine)
        for table, index, column in (
            ("items", "ix_items_status", "status"),
            ("restock_items", "ix_restock_items_status", "status"),
            ("recipes", "ix_recipes_source_type", "source_type"),
        ):
            indexes = {entry["name"]: entry["column_names"] for entry in inspector.get_indexes(table)}
            assert indexes == ({index: [column]} if revision == "0007" else {})
        for table in ("items", "restock_items"):
            assert f"ck_{table}_status" in _status_constraint_names(engine, table)
            quantity_type = next(
                column["type"] for column in inspector.get_columns(table)
                if column["name"] == "quantity_value"
            )
            if revision == "0007":
                assert isinstance(quantity_type, Numeric)
                assert (quantity_type.precision, quantity_type.scale) == (12, 3)
            else:
                assert isinstance(quantity_type, Float)
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text(f"UPDATE {table} SET status = 'banana' WHERE id = 1"))

        favorite_keys = inspector.get_unique_constraints("recipe_favorites")
        restock_columns = {col["name"]: col for col in inspector.get_columns("restock_items")}
        with engine.connect() as connection:
            assert connection.execute(text(
                "SELECT quantity_value, status FROM items WHERE id = 1"
            )).one() == (1.235, "active")
            assert connection.execute(text(
                "SELECT quantity_value, status, source_item_id FROM restock_items ORDER BY id"
            )).all() == [(2.346, "pending", 1), (None, "done", None)]
            assert connection.execute(text(
                "SELECT id, note FROM recipe_favorites"
            )).all() == [(1, "First")]
            if revision == "0007":
                assert restock_columns["updated_at"]["nullable"] is False
                assert connection.execute(text(
                    "SELECT updated_at = created_at FROM restock_items WHERE id = 1"
                )).scalar_one()
                assert {key["name"]: key["column_names"] for key in favorite_keys} == {
                    "uq_recipe_favorites_recipe_id": ["recipe_id"],
                }
            else:
                assert "updated_at" not in restock_columns
                assert favorite_keys == []

        if revision == "0007":
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text("INSERT INTO recipe_favorites (recipe_id) VALUES (1)"))
            command.downgrade(config, "0006")

    with engine.begin() as connection:
        connection.execute(text("INSERT INTO recipe_favorites (recipe_id) VALUES (1)"))
        assert connection.execute(text("SELECT COUNT(*) FROM recipe_favorites")).scalar_one() == 2


def test_0008_adds_and_removes_shopping_checked_at_and_keeps_rows(fresh_db):
    url, engine = fresh_db
    config = _alembic(url)
    command.upgrade(config, "0007")
    _seed_status_rows(engine)
    with engine.connect() as connection:
        before = connection.execute(text(
            "SELECT id, name, status, quantity_value FROM restock_items ORDER BY id"
        )).all()

    command.upgrade(config, "0008")
    command.upgrade(config, "0008")  # already applied: no-op
    columns = {col["name"]: col for col in inspect(engine).get_columns("restock_items")}
    assert columns["shopping_checked_at"]["nullable"] is True
    with engine.begin() as connection:
        assert connection.execute(text(
            "SELECT COUNT(*) FROM restock_items WHERE shopping_checked_at IS NOT NULL"
        )).scalar_one() == 0
        connection.execute(text(
            "UPDATE restock_items SET shopping_checked_at = '2026-11-25 10:00:00' WHERE id = 1"
        ))

    command.downgrade(config, "0007")
    assert _revision(engine) == "0007"
    assert "shopping_checked_at" not in {col["name"] for col in inspect(engine).get_columns("restock_items")}
    assert "ck_restock_items_status" in _status_constraint_names(engine, "restock_items")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE restock_items SET status = 'banana' WHERE id = 1"))
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT id, name, status, quantity_value FROM restock_items ORDER BY id"
        )).all() == before

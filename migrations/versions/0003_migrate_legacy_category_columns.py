"""Migrate legacy text category columns to category foreign keys.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17

Some databases created before structured categories were introduced were
adopted by the Alembic baseline even though ``items`` and ``restock_items``
still stored category names.  Their revision was therefore current while the
physical schema was not.  This migration repairs those databases in place and
is a no-op for databases that already use ``category_id``.
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _foreign_key_exists(table: str, column: str) -> bool:
    return any(
        column in foreign_key.get("constrained_columns", [])
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table)
    )


def _ensure_uncategorized() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO categories
                (name, slug, parent_id, recipe_usage, is_system, sort_order, created_at, updated_at)
            SELECT
                '未分类', 'uncategorized',
                (SELECT MIN(id) FROM categories WHERE slug = 'other'),
                'never', 1, 999, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            WHERE NOT EXISTS (SELECT 1 FROM categories WHERE slug = 'uncategorized')
            """
        )
    )


def _map_unique_category_names(table: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET category_id = (
                SELECT MIN(categories.id)
                FROM categories
                WHERE categories.name = {table}.category
            )
            WHERE category_id IS NULL
              AND (
                  SELECT COUNT(*)
                  FROM categories
                  WHERE categories.name = {table}.category
              ) = 1
            """
        )
    )


def _upgrade_items() -> None:
    columns = _columns("items")
    if "category" not in columns:
        return
    if "category_id" not in columns:
        op.add_column("items", sa.Column("category_id", sa.Integer(), nullable=True))

    _map_unique_category_names("items")
    op.execute(
        sa.text(
            """
            UPDATE items
            SET category_id = (SELECT MIN(id) FROM categories WHERE slug = 'uncategorized')
            WHERE category_id IS NULL
            """
        )
    )

    with op.batch_alter_table("items", naming_convention=_NAMING_CONVENTION) as batch:
        batch.alter_column("category_id", existing_type=sa.Integer(), nullable=False)
        if not _foreign_key_exists("items", "category_id"):
            batch.create_foreign_key(
                "fk_items_category_id_categories", "categories", ["category_id"], ["id"]
            )
        batch.drop_column("category")


def _upgrade_restock_items() -> None:
    columns = _columns("restock_items")
    if "category" not in columns:
        return
    if "category_id" not in columns:
        op.add_column("restock_items", sa.Column("category_id", sa.Integer(), nullable=True))

    _map_unique_category_names("restock_items")
    with op.batch_alter_table("restock_items", naming_convention=_NAMING_CONVENTION) as batch:
        if not _foreign_key_exists("restock_items", "category_id"):
            batch.create_foreign_key(
                "fk_restock_items_category_id_categories",
                "categories",
                ["category_id"],
                ["id"],
            )
        batch.drop_column("category")


def upgrade() -> None:
    """Repair legacy category columns while preserving every row."""
    # The baseline's offline SQL already creates the current category_id schema.
    # Reflection is unavailable in --sql mode, and no repair statements are needed.
    if context.is_offline_mode():
        return
    item_columns = _columns("items")
    restock_columns = _columns("restock_items")
    if "category" not in item_columns and "category" not in restock_columns:
        return

    _ensure_uncategorized()
    _upgrade_items()
    _upgrade_restock_items()


def _foreign_key_name(table: str, column: str) -> str:
    for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if column in foreign_key.get("constrained_columns", []):
            return foreign_key.get("name") or f"fk_{table}_{column}_categories"
    return f"fk_{table}_{column}_categories"


def _downgrade_table(table: str, nullable: bool) -> None:
    columns = _columns(table)
    if "category_id" not in columns or "category" in columns:
        return

    op.add_column(table, sa.Column("category", sa.String(length=100), nullable=True))
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET category = (
                SELECT categories.name
                FROM categories
                WHERE categories.id = {table}.category_id
            )
            """
        )
    )

    foreign_key_name = _foreign_key_name(table, "category_id")
    with op.batch_alter_table(table, naming_convention=_NAMING_CONVENTION) as batch:
        batch.drop_constraint(foreign_key_name, type_="foreignkey")
        if not nullable:
            batch.alter_column("category", existing_type=sa.String(length=100), nullable=False)
        batch.drop_column("category_id")


def downgrade() -> None:
    """Restore the legacy text category columns."""
    _downgrade_table("restock_items", nullable=True)
    _downgrade_table("items", nullable=False)

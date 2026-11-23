"""Store fixed-scale quantities and add stock, recipe, and favorite constraints.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-24
"""

from importlib import import_module

from alembic import context, op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

QUANTITY_TABLES = {"items": False, "restock_items": True}
INDEXES = {
    "items": ("ix_items_status", "status"),
    "restock_items": ("ix_restock_items_status", "status"),
    "recipes": ("ix_recipes_source_type", "source_type"),
}
FAVORITE_UNIQUE = "uq_recipe_favorites_recipe_id"


def _sqlite_quantity_table(table_name, *, upgraded, has_updated_at):
    prior = import_module("migrations.versions.0006_status_check_constraints")
    table = prior._sqlite_table(table_name, checked=True)
    if upgraded:
        table.c.quantity_value.type = sa.Numeric(12, 3)
    if table_name == "restock_items" and has_updated_at:
        table.append_column(sa.Column(
            "updated_at", sa.DateTime(), nullable=not upgraded,
            server_default=sa.func.now() if upgraded else None,
        ))
    return table


def _quantity_batch(table_name, *, upgraded=False, has_updated_at=False):
    if context.is_offline_mode() and op.get_context().dialect.name == "sqlite":
        return op.batch_alter_table(table_name, copy_from=_sqlite_quantity_table(
            table_name, upgraded=upgraded, has_updated_at=has_updated_at,
        ))
    return op.batch_alter_table(table_name)


def _favorites_batch(*, upgraded=False):
    if not context.is_offline_mode() or op.get_context().dialect.name != "sqlite":
        return op.batch_alter_table("recipe_favorites")
    metadata = sa.MetaData()
    recipes = sa.Table("recipes", metadata, sa.Column("id", sa.Integer, primary_key=True))
    table = sa.Table(
        "recipe_favorites",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recipe_id", sa.Integer, sa.ForeignKey(recipes.c.id), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("note", sa.String(500)),
    )
    if upgraded:
        table.append_constraint(sa.UniqueConstraint("recipe_id", name=FAVORITE_UNIQUE))
    return op.batch_alter_table("recipe_favorites", copy_from=table)


def upgrade() -> None:
    inspector = None if context.is_offline_mode() else sa.inspect(op.get_bind())
    dialect = op.get_context().dialect.name
    for table_name, quantity_nullable in QUANTITY_TABLES.items():
        columns = {} if inspector is None else {
            column["name"]: column["type"] for column in inspector.get_columns(table_name)
        }
        quantity_type = columns.get("quantity_value")
        alter_quantity = (
            getattr(quantity_type, "precision", None) != 12
            or getattr(quantity_type, "scale", None) != 3
        )
        add_updated_at = table_name == "restock_items" and "updated_at" not in columns

        if alter_quantity and dialect == "sqlite":
            # SQLite does not enforce a declared Numeric scale during the table copy.
            op.execute(sa.text(f"UPDATE {table_name} SET quantity_value = ROUND(quantity_value, 3)"))
        if add_updated_at:
            op.add_column(table_name, sa.Column("updated_at", sa.DateTime(), nullable=True))
            op.execute(sa.text("UPDATE restock_items SET updated_at = created_at"))

        if alter_quantity or add_updated_at:
            with _quantity_batch(table_name, has_updated_at=add_updated_at) as batch:
                if alter_quantity:
                    batch.alter_column(
                        "quantity_value", existing_type=sa.Float(),
                        type_=sa.Numeric(12, 3), existing_nullable=quantity_nullable,
                    )
                if add_updated_at:
                    batch.alter_column(
                        "updated_at", existing_type=sa.DateTime(), nullable=False,
                        server_default=sa.func.now(),
                    )

    existing_unique = set() if inspector is None else {
        constraint["name"] for constraint in inspector.get_unique_constraints("recipe_favorites")
    }
    if FAVORITE_UNIQUE not in existing_unique:
        op.execute(sa.text(
            "DELETE FROM recipe_favorites WHERE id NOT IN ("
            "SELECT keep_id FROM (SELECT MIN(id) AS keep_id FROM recipe_favorites "
            "GROUP BY recipe_id) AS keepers)"
        ))
        with _favorites_batch() as batch:
            batch.create_unique_constraint(FAVORITE_UNIQUE, ["recipe_id"])

    for table_name, (index, column) in INDEXES.items():
        existing = set() if inspector is None else {
            entry["name"] for entry in inspector.get_indexes(table_name)
        }
        if index not in existing:
            op.create_index(index, table_name, [column])


def downgrade() -> None:
    for table_name, (index, _) in INDEXES.items():
        op.drop_index(index, table_name=table_name)

    mysql_fk = None
    if op.get_context().dialect.name == "mysql":
        # InnoDB may use the unique key as the supporting index for the FK.
        # Recreating the FK lets InnoDB restore its own supporting index.
        mysql_fk = "recipe_favorites_ibfk_1"
        if not context.is_offline_mode():
            mysql_fk = next(
                fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys("recipe_favorites")
                if fk["constrained_columns"] == ["recipe_id"]
            )
    with _favorites_batch(upgraded=True) as batch:
        if mysql_fk is not None:
            batch.drop_constraint(mysql_fk, type_="foreignkey")
        batch.drop_constraint(FAVORITE_UNIQUE, type_="unique")
        if mysql_fk is not None:
            batch.create_foreign_key(mysql_fk, "recipes", ["recipe_id"], ["id"])

    for table_name, quantity_nullable in QUANTITY_TABLES.items():
        with _quantity_batch(table_name, upgraded=True, has_updated_at=True) as batch:
            batch.alter_column(
                "quantity_value", existing_type=sa.Numeric(12, 3), type_=sa.Float(),
                existing_nullable=quantity_nullable,
            )
            if table_name == "restock_items":
                batch.drop_column("updated_at")

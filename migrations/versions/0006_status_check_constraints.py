"""Enforce the stock and restock status vocabularies.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-24
"""

from alembic import context, op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# HEX keeps the check case- and whitespace-sensitive on MySQL and SQLite.
STATUS_CHECKS = {
    "items": "HEX(status) IN (HEX('active'), HEX('expiring soon'), HEX('expired'), HEX('consumed'))",
    "restock_items": "HEX(status) IN (HEX('pending'), HEX('done'))",
}


def _sqlite_table(name, *, checked=False):
    """Describe the source table for SQLite batch operations in SQL mode."""
    metadata = sa.MetaData()
    category = sa.Table("categories", metadata, sa.Column("id", sa.Integer, primary_key=True))
    items = sa.Table(
        "items",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey(category.c.id), nullable=False),
        sa.Column("owner", sa.String(100), nullable=False),
        sa.Column("purchase_date", sa.String(10), nullable=False),
        sa.Column("quantity_value", sa.Float, nullable=False),
        sa.Column("quantity_unit", sa.String(50), nullable=False),
        sa.Column("location", sa.String(100), nullable=False),
        sa.Column("unopened_expiration_date", sa.String(10), nullable=False),
        sa.Column("opened_expiration_date", sa.String(10)),
        sa.Column("opened_date", sa.String(10)),
        sa.Column("current_expiration_date", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    restock_items = sa.Table(
        "restock_items",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey(category.c.id)),
        sa.Column("quantity_value", sa.Float),
        sa.Column("quantity_unit", sa.String(50)),
        sa.Column("source_item_id", sa.Integer, sa.ForeignKey(items.c.id)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("done_at", sa.DateTime),
    )
    table = items if name == "items" else restock_items
    if checked:
        table.append_constraint(sa.CheckConstraint(STATUS_CHECKS[name], name=f"ck_{name}_status"))
    return table


def _batch(table_name, *, checked=False):
    if context.is_offline_mode() and op.get_context().dialect.name == "sqlite":
        return op.batch_alter_table(table_name, copy_from=_sqlite_table(table_name, checked=checked))
    return op.batch_alter_table(table_name)


def upgrade() -> None:
    existing_checks = {}
    if not context.is_offline_mode():
        connection = op.get_bind()
        invalid = {
            table: connection.execute(sa.text(
                f"SELECT COUNT(*) FROM {table} WHERE status IS NULL OR NOT ({check})"
            )).scalar_one()
            for table, check in STATUS_CHECKS.items()
        }
        if any(invalid.values()):
            counts = ", ".join(f"{table}: {count}" for table, count in invalid.items())
            raise RuntimeError(f"Cannot add status checks; invalid status rows ({counts})")

        inspector = sa.inspect(connection)
        existing_checks = {
            table: {check["name"] for check in inspector.get_check_constraints(table)}
            for table in STATUS_CHECKS
        }

    for table, check in STATUS_CHECKS.items():
        constraint = f"ck_{table}_status"
        # Schema adoption can start from tables created by current ORM metadata.
        if constraint not in existing_checks.get(table, ()):
            with _batch(table) as batch:
                batch.create_check_constraint(constraint, check)


def downgrade() -> None:
    for table in reversed(STATUS_CHECKS):
        with _batch(table, checked=True) as batch:
            batch.drop_constraint(f"ck_{table}_status", type_="check")

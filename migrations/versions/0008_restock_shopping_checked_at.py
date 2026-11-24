"""Add the restock shopping check time.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-25
"""

from alembic import context, op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TABLE = "restock_items"
COLUMN = "shopping_checked_at"


def _has_column() -> bool:
    if context.is_offline_mode():
        return False
    return COLUMN in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    # A nullable column without a default: existing rows stay unchecked.
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Plain DROP COLUMN (SQLite 3.35+, MySQL) keeps the table's CHECK constraints,
    # which a batch table copy would have to rebuild.
    op.drop_column(TABLE, COLUMN)

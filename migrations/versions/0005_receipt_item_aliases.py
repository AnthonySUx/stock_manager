"""Store confirmed receipt aliases and their per-name frequencies.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-20
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = set() if context.is_offline_mode() else set(sa.inspect(op.get_bind()).get_table_names())
    if "receipt_item_aliases" not in existing:
        op.create_table(
            "receipt_item_aliases",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("store_key", sa.String(255), nullable=False),
            sa.Column("store_name", sa.String(255), nullable=True),
            sa.Column("raw_name_normalized", sa.String(255), nullable=False),
            sa.Column("raw_name_original", sa.String(255), nullable=False),
            sa.Column("confirmed_item_name", sa.String(255), nullable=False),
            sa.Column(
                "confirmed_category_id", sa.Integer(),
                sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("confirmed_quantity_unit", sa.String(50), nullable=False),
            sa.Column("confirmed_location", sa.String(100), nullable=False),
            sa.Column("specificity", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("alias_mode", sa.String(8), nullable=False, server_default="suggest"),
            sa.Column("confirmed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("distinct_confirmed_names_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_confirmed_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("store_key", "raw_name_normalized", name="uq_receipt_alias_store_raw"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_bin",
        )
    if "receipt_alias_names" not in existing:
        op.create_table(
            "receipt_alias_names",
            sa.Column(
                "alias_id", sa.Integer(),
                sa.ForeignKey("receipt_item_aliases.id", ondelete="CASCADE"), primary_key=True,
            ),
            sa.Column("confirmed_item_name", sa.String(255), primary_key=True),
            sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_bin",
        )


def downgrade() -> None:
    op.drop_table("receipt_alias_names")
    op.drop_table("receipt_item_aliases")

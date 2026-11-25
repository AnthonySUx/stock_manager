"""Add household and recipe kitchen equipment.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import context, op


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set()
    if not context.is_offline_mode():
        existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "household_equipment" not in existing:
        op.create_table(
            "household_equipment",
            sa.Column("code", sa.String(32), primary_key=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )

    if "recipe_equipment" not in existing:
        op.create_table(
            "recipe_equipment",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("recipe_id", sa.Integer, sa.ForeignKey("recipes.id"), nullable=False),
            sa.Column("group_index", sa.Integer, nullable=False),
            sa.Column("equipment_code", sa.String(32), nullable=False),
            sa.UniqueConstraint(
                "recipe_id", "group_index", "equipment_code", name="uq_recipe_equipment_group_code",
            ),
        )
        op.create_index("ix_recipe_equipment_recipe_id", "recipe_equipment", ["recipe_id"])


def downgrade() -> None:
    op.drop_table("recipe_equipment")
    op.drop_table("household_equipment")

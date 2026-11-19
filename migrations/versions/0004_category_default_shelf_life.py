"""Add optional shelf-life defaults for inventory categories.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-19
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep the historical backfill independent of future seed changes.
_DEFAULT_DAYS = {
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
}


def upgrade() -> None:
    """Backfill only known system categories without a preset value."""
    column = "default_shelf_life_days"
    # Adopt an existing column, including after a retry following committed DDL.
    if context.is_offline_mode() or column not in {
        row["name"] for row in sa.inspect(op.get_bind()).get_columns("categories")
    }:
        op.add_column("categories", sa.Column(column, sa.Integer(), nullable=True))

    categories = sa.table(
        "categories",
        sa.column("slug", sa.String()),
        sa.column("is_system", sa.Boolean()),
        sa.column(column, sa.Integer()),
    )
    op.execute(
        categories.update()
        .where(
            categories.c.is_system.is_(True),
            categories.c.default_shelf_life_days.is_(None),
            categories.c.slug.in_(list(_DEFAULT_DAYS)),
        )
        .values(default_shelf_life_days=sa.case(_DEFAULT_DAYS, value=categories.c.slug))
    )


def downgrade() -> None:
    op.drop_column("categories", "default_shelf_life_days")

"""Drop the unused AI recommendation table; ai_saved recipes become user recipes (#66).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17

- `ai_recipe_recommendations` was never written to; the deprecated
  `/api/recipes/ai/today` endpoint that it belonged to is removed.
- `source_type = 'ai_saved'` is no longer a valid value. Nothing created such
  rows, but any that exist are converted to user recipes (a saved AI draft
  belongs to the user). The downgrade does not convert them back.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_recipes = sa.table(
    "recipes",
    sa.column("source_type", sa.String),
    sa.column("is_user_created", sa.Boolean),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        _recipes.update()
        .where(_recipes.c.source_type == "ai_saved")
        .values(source_type="user", is_user_created=True)
    )
    op.drop_table("ai_recipe_recommendations")


def downgrade() -> None:
    """Downgrade schema (recreates the table as in 0001, empty)."""
    op.create_table(
        "ai_recipe_recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_context_json", sa.Text(), nullable=True),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

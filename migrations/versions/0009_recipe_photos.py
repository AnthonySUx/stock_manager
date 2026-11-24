"""Add recipe photos.

Revision ID: 0009
Revises: 0008
"""

from alembic import context, op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TABLE = "recipe_photos"


def upgrade() -> None:
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table(TABLE):
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recipe_id", sa.Integer, sa.ForeignKey("recipes.id"), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("step_number", sa.Integer),
        sa.Column("usage_history_id", sa.Integer, sa.ForeignKey("recipe_usage_history.id")),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("is_cover", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("hidden", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("bytes", sa.Integer, nullable=False),
        sa.Column("caption", sa.String(255)),
        sa.Column("source_path", sa.String(500)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "HEX(origin) IN (HEX('howtocook'), HEX('user'))", name="ck_recipe_photos_origin",
        ),
        sa.CheckConstraint(
            "step_number IS NULL OR usage_history_id IS NULL", name="ck_recipe_photos_group",
        ),
        sa.CheckConstraint(
            "HEX(origin) != HEX('howtocook') OR usage_history_id IS NULL",
            name="ck_recipe_photos_source_group",
        ),
        sa.UniqueConstraint("recipe_id", "source_path", name="uq_recipe_photos_source_path"),
    )
    for column in ("recipe_id", "usage_history_id"):
        op.create_index(f"ix_{TABLE}_{column}", TABLE, [column])


def downgrade() -> None:
    op.drop_table(TABLE)

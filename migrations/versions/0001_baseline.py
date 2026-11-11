"""Baseline: the schema as it was when Alembic was added (#49).

Revision ID: 0001
Revises:
Create Date: 2026-11-12

Databases created before Alembic (by the old Base.metadata.create_all at
startup) already have these tables. Tables that exist are skipped, so
`alembic upgrade head` adopts such a database without touching its data,
then records revision 0001. Those databases must already have the current
schema (anything created after #33; older ones had to be rebuilt anyway).
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Offline (--sql) there is no database to look at: emit every table.
    existing = set() if context.is_offline_mode() else set(sa.inspect(op.get_bind()).get_table_names())

    def _create_table(name, *columns):
        """op.create_table, unless the table already exists (adoption)."""
        if name not in existing:
            op.create_table(name, *columns)

    _create_table('ai_recipe_recommendations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('request_context_json', sa.Text(), nullable=True),
    sa.Column('response_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('model_name', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('categories',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('recipe_usage', sa.String(length=20), server_default='never', nullable=False),
    sa.Column('is_system', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    _create_table('recipes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('source_type', sa.String(length=20), nullable=False),
    sa.Column('source_name', sa.String(length=100), nullable=False),
    sa.Column('source_url', sa.String(length=500), nullable=True),
    sa.Column('source_path', sa.String(length=500), nullable=True),
    sa.Column('license_name', sa.String(length=100), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('difficulty', sa.String(length=50), nullable=True),
    sa.Column('servings', sa.String(length=50), nullable=True),
    sa.Column('cook_time_minutes', sa.Integer(), nullable=True),
    sa.Column('raw_markdown', sa.Text(), nullable=True),
    sa.Column('is_user_created', sa.Boolean(), nullable=False),
    sa.Column('base_recipe_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['base_recipe_id'], ['recipes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('settings',
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('value', sa.String(length=255), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    _create_table('items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('owner', sa.String(length=100), nullable=False),
    sa.Column('purchase_date', sa.String(length=10), nullable=False),
    sa.Column('quantity_value', sa.Float(), nullable=False),
    sa.Column('quantity_unit', sa.String(length=50), nullable=False),
    sa.Column('location', sa.String(length=100), nullable=False),
    sa.Column('unopened_expiration_date', sa.String(length=10), nullable=False),
    sa.Column('opened_expiration_date', sa.String(length=10), nullable=True),
    sa.Column('opened_date', sa.String(length=10), nullable=True),
    sa.Column('current_expiration_date', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('recipe_favorites',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('recipe_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('note', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('recipe_ingredients',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('recipe_id', sa.Integer(), nullable=False),
    sa.Column('ingredient_name', sa.String(length=255), nullable=False),
    sa.Column('normalized_name', sa.String(length=255), nullable=True),
    sa.Column('quantity', sa.String(length=100), nullable=True),
    sa.Column('unit', sa.String(length=50), nullable=True),
    sa.Column('is_optional', sa.Boolean(), nullable=False),
    sa.Column('is_seasoning', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('recipe_steps',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('recipe_id', sa.Integer(), nullable=False),
    sa.Column('step_number', sa.Integer(), nullable=False),
    sa.Column('instruction', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('recipe_usage_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('recipe_id', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('metadata_json', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _create_table('restock_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('quantity_value', sa.Float(), nullable=True),
    sa.Column('quantity_unit', sa.String(length=50), nullable=True),
    sa.Column('source_item_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('done_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['source_item_id'], ['items.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('restock_items')
    op.drop_table('recipe_usage_history')
    op.drop_table('recipe_steps')
    op.drop_table('recipe_ingredients')
    op.drop_table('recipe_favorites')
    op.drop_table('items')
    op.drop_table('settings')
    op.drop_table('recipes')
    op.drop_table('categories')
    op.drop_table('ai_recipe_recommendations')

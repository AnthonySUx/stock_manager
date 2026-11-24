"""SQLAlchemy ORM models for Stock Manager."""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (#49).

    The DateTime columns are timezone-naive and every stored value is UTC, so
    the timezone is dropped after reading the clock in UTC. Replaces the
    deprecated datetime.utcnow().
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


# ─── Categories ──────────────────────────────────────────────────


class Category(Base):
    """Inventory category taxonomy. Max 2 levels: top-level and subcategory."""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    recipe_usage = Column(String(20), nullable=False, default="never", server_default="never")
    default_shelf_life_days = Column(Integer, nullable=True)
    is_system = Column(Boolean, nullable=False, default=False, server_default="0")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now(), onupdate=utcnow)

    parent = relationship("Category", remote_side="Category.id", back_populates="children")
    children = relationship("Category", back_populates="parent")



class ReceiptItemAlias(Base):
    """The latest confirmation for a normalized receipt line at one store."""

    __tablename__ = "receipt_item_aliases"
    __table_args__ = (
        UniqueConstraint("store_key", "raw_name_normalized", name="uq_receipt_alias_store_raw"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_key = Column(String(255), nullable=False)
    store_name = Column(String(255), nullable=True)
    raw_name_normalized = Column(String(255), nullable=False)
    raw_name_original = Column(String(255), nullable=False)
    confirmed_item_name = Column(String(255), nullable=False)
    confirmed_category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    confirmed_quantity_unit = Column(String(50), nullable=False)
    confirmed_location = Column(String(100), nullable=False)
    specificity = Column(String(32), nullable=False, server_default="unknown")
    alias_mode = Column(String(8), nullable=False, server_default="suggest")
    confirmed_count = Column(Integer, nullable=False, server_default="0")
    distinct_confirmed_names_count = Column(Integer, nullable=False, server_default="0")
    last_confirmed_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now(), onupdate=utcnow)

    names = relationship("ReceiptAliasName")


class ReceiptAliasName(Base):
    """Frequency of a confirmed name within one receipt alias."""

    __tablename__ = "receipt_alias_names"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}

    alias_id = Column(Integer, ForeignKey("receipt_item_aliases.id", ondelete="CASCADE"), primary_key=True)
    confirmed_item_name = Column(String(255), primary_key=True)
    count = Column(Integer, nullable=False, server_default="0")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        # Compare exact bytes even with a case-insensitive MySQL collation.
        CheckConstraint(
            "HEX(status) IN (HEX('active'), HEX('expiring soon'), HEX('expired'), HEX('consumed'))",
            name="ck_items_status",
        ),
        Index("ix_items_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    owner = Column(String(100), nullable=False)
    purchase_date = Column(String(10), nullable=False)
    quantity_value = Column(Numeric(12, 3), nullable=False)
    quantity_unit = Column(String(50), nullable=False)
    location = Column(String(100), nullable=False)
    unopened_expiration_date = Column(String(10), nullable=False)
    opened_expiration_date = Column(String(10), nullable=True)
    opened_date = Column(String(10), nullable=True)
    current_expiration_date = Column(String(10), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default="active",
    )
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=utcnow,
        server_default=func.now(),
        onupdate=utcnow,
    )

    # Relationship
    category = relationship("Category")

class RestockItem(Base):
    __tablename__ = "restock_items"
    __table_args__ = (
        CheckConstraint("HEX(status) IN (HEX('pending'), HEX('done'))", name="ck_restock_items_status"),
        Index("ix_restock_items_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    quantity_value = Column(Numeric(12, 3), nullable=True)
    quantity_unit = Column(String(50), nullable=True)
    source_item_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    status = Column(
        String(20),
        nullable=False,
        default="pending",
    )
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
    done_at = Column(DateTime, nullable=True)
    # Set while shopping when the item is in the cart; not stocked yet (#22).
    shopping_checked_at = Column(DateTime, nullable=True)
    updated_at = Column(
        DateTime, nullable=False, default=utcnow, server_default=func.now(), onupdate=utcnow,
    )

    # Relationships
    category = relationship("Category")
    source_item = relationship("Item", backref="restock_items")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(String(255), nullable=False)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=utcnow,
        server_default=func.now(),
        onupdate=utcnow,
    )


# ─── Recipe Models ────────────────────────────────────────────────


class Recipe(Base):
    """Recipe from HowToCook, user-created, or saved AI recommendations."""
    __tablename__ = "recipes"
    __table_args__ = (Index("ix_recipes_source_type", "source_type"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String(20), nullable=False, default="howtocook")
    source_name = Column(String(100), nullable=False, default="HowToCook")
    source_url = Column(String(500), nullable=True)
    source_path = Column(String(500), nullable=True)
    license_name = Column(String(100), nullable=True, default="The Unlicense")
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    difficulty = Column(String(50), nullable=True)
    servings = Column(String(50), nullable=True)
    cook_time_minutes = Column(Integer, nullable=True)
    raw_markdown = Column(Text, nullable=True)
    is_user_created = Column(Boolean, nullable=False, default=False)
    base_recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now(), onupdate=utcnow)

    ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")
    steps = relationship("RecipeStep", back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeStep.step_number")
    base_recipe = relationship("Recipe", remote_side="Recipe.id", backref="forks")


class RecipeIngredient(Base):
    """Ingredient entry for a recipe."""
    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    ingredient_name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=True)
    quantity = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=True)
    is_optional = Column(Boolean, nullable=False, default=False)
    is_seasoning = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=0)

    recipe = relationship("Recipe", back_populates="ingredients")


class RecipeStep(Base):
    """Step in a recipe."""
    __tablename__ = "recipe_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    instruction = Column(Text, nullable=False)

    recipe = relationship("Recipe", back_populates="steps")


class RecipeFavorite(Base):
    """User's favorite recipes."""
    __tablename__ = "recipe_favorites"
    __table_args__ = (UniqueConstraint("recipe_id", name="uq_recipe_favorites_recipe_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())
    note = Column(String(500), nullable=True)

    recipe = relationship("Recipe")


class RecipeUsageHistory(Base):
    """History of recommendations or cooking events."""
    __tablename__ = "recipe_usage_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    event_type = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())
    metadata_json = Column(Text, nullable=True)

    recipe = relationship("Recipe")

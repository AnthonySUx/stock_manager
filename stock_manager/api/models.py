"""SQLAlchemy ORM models for Stock Manager."""

from datetime import datetime

from sqlalchemy import (
    Column,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    owner = Column(String(100), nullable=False)
    purchase_date = Column(String(10), nullable=False)
    quantity_value = Column(Float, nullable=False)
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
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RestockItem(Base):
    __tablename__ = "restock_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)
    quantity_value = Column(Float, nullable=True)
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
        default=datetime.utcnow,
        server_default=func.now(),
    )
    done_at = Column(DateTime, nullable=True)

    # Relationship
    source_item = relationship("Item", backref="restock_items")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(String(255), nullable=False)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ─── Recipe Models ────────────────────────────────────────────────


class Recipe(Base):
    """Recipe from HowToCook, user-created, or saved AI recommendations."""
    __tablename__ = "recipes"

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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now(), onupdate=func.now())

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

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    note = Column(String(500), nullable=True)

    recipe = relationship("Recipe")


class RecipeUsageHistory(Base):
    """History of recommendations or cooking events."""
    __tablename__ = "recipe_usage_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    event_type = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    metadata_json = Column(Text, nullable=True)

    recipe = relationship("Recipe")


class AIRecipeRecommendation(Base):
    """Saved AI-generated daily recommendation results."""
    __tablename__ = "ai_recipe_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_context_json = Column(Text, nullable=True)
    response_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    model_name = Column(String(255), nullable=True)
"""Pydantic schemas for recipe features."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class IngredientSchema(BaseModel):
    ingredient_name: str
    normalized_name: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = None
    is_optional: bool = False
    is_seasoning: bool = False
    sort_order: int = 0


class StepSchema(BaseModel):
    step_number: int
    instruction: str


class RecipeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    difficulty: Optional[str] = Field(None, max_length=50)
    servings: Optional[str] = Field(None, max_length=50)
    cook_time_minutes: Optional[int] = None
    raw_markdown: Optional[str] = None
    ingredients: list[IngredientSchema] = []
    steps: list[StepSchema] = []


class RecipeUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    difficulty: Optional[str] = Field(None, max_length=50)
    servings: Optional[str] = Field(None, max_length=50)
    cook_time_minutes: Optional[int] = None
    raw_markdown: Optional[str] = None
    ingredients: Optional[list[IngredientSchema]] = None
    steps: Optional[list[StepSchema]] = None


class RecipeResponse(BaseModel):
    id: int
    source_type: str
    source_name: str
    source_url: Optional[str] = None
    source_path: Optional[str] = None
    license_name: Optional[str] = None
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[str] = None
    servings: Optional[str] = None
    cook_time_minutes: Optional[int] = None
    raw_markdown: Optional[str] = None
    is_user_created: bool = False
    base_recipe_id: Optional[int] = None
    is_favorite: bool = False
    ingredients: list[IngredientSchema] = []
    steps: list[StepSchema] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RecipeSummary(BaseModel):
    id: int
    source_type: str
    source_name: str
    title: str
    category: Optional[str] = None
    difficulty: Optional[str] = None
    cook_time_minutes: Optional[int] = None
    is_user_created: bool = False
    base_recipe_id: Optional[int] = None
    is_favorite: bool = False
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RecipeRecommendation(BaseModel):
    recipe_id: int
    title: str
    score: float = 0.0
    reason: Optional[str] = None
    matched_inventory_items: list[str] = []
    expiring_inventory_items: list[str] = []
    missing_ingredients: list[str] = []
    is_favorite: bool = False
    is_new_suggestion: bool = False
    source_type: str = "howtocook"


class RecipeRecommendationResponse(BaseModel):
    source_notice: str = ""
    recommendations: list[RecipeRecommendation] = []


class AIRecipeRecommendationResponse(BaseModel):
    mode: str  # "ai" or "rule_based_fallback"
    summary: Optional[str] = None
    source_notice: str = ""
    recommendations: list[RecipeRecommendation] = []


class SourceResponse(BaseModel):
    name: str
    url: str
    license: str
    notice: str

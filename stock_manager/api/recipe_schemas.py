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
    has_been_cooked: bool = False
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
    has_been_cooked: bool = False
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


class ConsumePreviewItem(BaseModel):
    """A single inventory item suggested for consumption."""
    ingredient_name: str
    item_id: int
    item_name: str
    available_quantity: float
    available_unit: str
    suggested_quantity: float = 1.0
    unit: str = ""
    status: str = "active"
    current_expiration_date: Optional[str] = None
    confidence: str = "high"


class ConsumePreviewResponse(BaseModel):
    """Preview of inventory items that would be consumed for a recipe."""
    recipe_id: int
    title: str
    suggestions: list[ConsumePreviewItem] = []
    unmatched_ingredients: list[str] = []


class CookConsumeItem(BaseModel):
    """User-confirmed inventory consumption for a cooked recipe."""
    item_id: int
    quantity: float = Field(..., gt=0)
    ingredient_name: str = ""


class CookRecipeRequest(BaseModel):
    """Request body for marking a recipe as cooked and consuming inventory."""
    consume_items: list[CookConsumeItem] = []
    notes: Optional[str] = None


class CookConsumedItem(BaseModel):
    """Result of a single inventory consumption."""
    item_id: int
    item_name: str
    consumed_quantity: float
    remaining_quantity: float
    status: str


class CookRecipeResponse(BaseModel):
    """Response after cooking a recipe and consuming inventory."""
    message: str
    recipe_id: int
    title: str
    consumed_items: list[CookConsumedItem] = []
    notes: Optional[str] = None

# ─── Explore Recipes ─────────────────────────────────────────────


class ExploreStructuredPreferences(BaseModel):
    """Structured preference fields for recipe exploration."""
    inventory_item_ids: list[int] = []
    extra_ingredients: list[str] = []
    flavors: list[str] = []
    textures: list[str] = []
    cuisine_group: Optional[str] = None
    cuisine: Optional[str] = None
    cooking_methods: list[str] = []
    max_time_minutes: Optional[int] = None
    difficulty: Optional[str] = None
    prioritize_expiring: bool = True
    allow_missing_ingredients: bool = True


class ExploreRequest(BaseModel):
    """Request body for Explore Recipes."""
    mode: str = Field(..., pattern="^(structured|natural_language)$")
    structured: Optional[ExploreStructuredPreferences] = None
    natural_language: Optional[str] = None


class ExploreIdea(BaseModel):
    """A single cooking idea returned from Explore Recipes."""
    idea_id: str = ""
    title: str
    description: Optional[str] = None
    source_type: str = "ai_idea"  # ai_idea | existing_recipe
    recipe_id: Optional[int] = None
    matched_ingredients: list[str] = []
    expiring_ingredients: list[str] = []
    missing_ingredients: list[str] = []
    flavors: list[str] = []
    textures: list[str] = []
    cuisine_group: Optional[str] = None
    cuisine: Optional[str] = None
    cooking_method: Optional[str] = None
    estimated_time_minutes: Optional[int] = None
    reason: Optional[str] = None
    can_expand_to_recipe: bool = True


class ExploreResponse(BaseModel):
    """Response from Explore Recipes."""
    mode: str  # ai
    input_mode: str  # structured | natural_language
    ideas: list[ExploreIdea] = []
    warnings: list[str] = []


class ExpandRequest(BaseModel):
    """Request body for expanding an idea into a recipe draft."""
    idea: ExploreIdea


class ExpandIngredient(BaseModel):
    ingredient_name: str
    quantity: Optional[str] = None
    unit: Optional[str] = None
    is_optional: bool = False
    is_seasoning: bool = False


class ExpandStep(BaseModel):
    step_number: int
    instruction: str


class ExpandResponse(BaseModel):
    """Response from expanding an idea into a recipe draft."""
    recipe_draft: dict  # RecipeCreate-compatible dict, not saved


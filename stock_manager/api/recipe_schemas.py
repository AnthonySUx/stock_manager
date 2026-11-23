"""Pydantic schemas for recipe features."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from stock_manager.api.schemas import ItemStatus, PositiveStockQuantity, RestockItemResponse

# Dish categories = HowToCook `dishes/<dir>` names (template excluded), so user
# recipes and imported ones share one vocabulary (#46).
RecipeCategory = Literal[
    "breakfast", "meat_dish", "vegetable_dish", "aquatic", "soup", "staple",
    "semi-finished", "dessert", "drink", "condiment",
]


# Machine fields in AI output are fixed English values; the app translates
# them for display (#65).
CookingMethod = Literal[
    "stir_fry", "steam", "boil", "braise", "stew", "pan_fry", "deep_fry",
    "roast", "bake", "grill", "cold_mix", "raw", "other",
]
CuisineGroup = Literal["chinese", "japanese", "korean", "western", "southeast_asian", "other"]
Difficulty = Literal["easy", "medium", "hard"]


class AIWarning(BaseModel):
    """A warning from an AI endpoint: a stable code plus parameters (#65).

    Codes and params: locale_fallback {requested}, draft_ai_generated,
    idea_dropped_malformed, idea_dropped_wrong_language {title},
    field_value_dropped {field, value}, quantity_dropped {ingredient},
    ingredient_dropped_malformed {index}, step_dropped_malformed {index}
    (index = 1-based position in the AI reply).
    """
    code: str
    params: dict[str, str] = {}


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
    # Required for new recipes so Today Recommendations can place them in a scene.
    category: RecipeCategory
    description: Optional[str] = None
    difficulty: Optional[str] = Field(None, max_length=50)
    servings: Optional[str] = Field(None, max_length=50)
    cook_time_minutes: Optional[int] = None
    raw_markdown: Optional[str] = None
    ingredients: list[IngredientSchema] = []
    steps: list[StepSchema] = []

    ai_draft_hash: Optional[str] = Field(None, pattern="^[0-9a-f]{64}$")


class RecipeUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[RecipeCategory] = None
    description: Optional[str] = None
    difficulty: Optional[str] = Field(None, max_length=50)
    servings: Optional[str] = Field(None, max_length=50)
    cook_time_minutes: Optional[int] = None
    raw_markdown: Optional[str] = None
    ingredients: Optional[list[IngredientSchema]] = None
    steps: Optional[list[StepSchema]] = None

    @field_validator("title", "category", mode="before")
    @classmethod
    def reject_null(cls, value, info):
        """Omit a field to keep it; null would clear a required value."""
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return value


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


class SourceResponse(BaseModel):
    name: str
    url: str
    license: str
    notice: str


class ConsumeAllocation(BaseModel):
    item_id: int
    quantity: float


class ConsumePreviewItem(BaseModel):
    """Suggested stock allocations for one recipe ingredient."""
    ingredient_name: str
    item_id: int
    item_name: str
    available_quantity: float
    available_unit: str
    # The recipe amount as written ("500克"); shown to help the user decide.
    recipe_quantity: Optional[str] = None
    # Amount to deduct from the first matching batch, for existing clients.
    suggested_quantity: Optional[float] = None
    unit: str = ""  # stock unit, the unit the amount is deducted in
    allocations: list[ConsumeAllocation] = Field(default_factory=list)
    needs_user_input: bool = False
    status: ItemStatus = "active"
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
    quantity: PositiveStockQuantity
    ingredient_name: str = ""


class CookRecipeRequest(BaseModel):
    """Request body for marking a recipe as cooked and consuming inventory."""
    consume_items: list[CookConsumeItem] = []
    add_depleted_to_restock: bool = False
    notes: Optional[str] = None


class CookConsumedItem(BaseModel):
    """Result of a single inventory consumption."""
    item_id: int
    item_name: str
    consumed_quantity: float
    remaining_quantity: float
    status: ItemStatus


class CookLine(BaseModel):
    """Outcome for one requested stock deduction."""

    item_id: int
    ingredient_name: str
    result: Literal["consumed", "skipped", "insufficient"]
    consumed_quantity: float | None = None
    requested: float | None = None
    available: float | None = None
    reason: Literal["item_not_found", "not_recipe_usable"] | None = None


class CookRecipeResponse(BaseModel):
    """Response after cooking a recipe and consuming inventory."""
    message: str
    recipe_id: int
    title: str
    consumed_items: list[CookConsumedItem] = []
    lines: list[CookLine] = []
    notes: Optional[str] = None

class SkippedRestockIngredient(BaseModel):
    name: str
    reason: Literal["already_pending"]


class MissingToRestockResponse(BaseModel):
    created: list[RestockItemResponse]
    skipped: list[SkippedRestockIngredient]


# ─── Explore Recipes ─────────────────────────────────────────────


class ExploreStructuredPreferences(BaseModel):
    """Structured preference fields for recipe exploration."""
    # When non-empty, only these inventory items are sent to the AI (#45).
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
    # Output language (zh-CN, en, ja). Omitted: household setting, then
    # Accept-Language, then zh-CN (#65).
    locale: Optional[str] = Field(None, max_length=35)

    @model_validator(mode="after")
    def check_mode_matches_payload(self):
        """`mode` decides which input is used; the other one must be empty (#45)."""
        text = (self.natural_language or "").strip()
        if self.mode == "structured":
            if self.structured is None:
                raise ValueError("mode 'structured' requires 'structured'")
            if text:
                raise ValueError("mode 'structured' does not accept 'natural_language'")
        else:
            if not text:
                raise ValueError("mode 'natural_language' requires non-empty 'natural_language'")
            if self.structured is not None:
                raise ValueError("mode 'natural_language' does not accept 'structured'")
            self.natural_language = text
        return self


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
    cuisine_group: Optional[CuisineGroup] = None
    cuisine: Optional[str] = None
    cooking_method: Optional[CookingMethod] = None
    estimated_time_minutes: Optional[int] = None
    reason: Optional[str] = None
    can_expand_to_recipe: bool = True


class ExploreResponse(BaseModel):
    """Response from Explore Recipes."""
    mode: str  # ai
    input_mode: str  # structured | natural_language
    locale: str  # the language the AI text was generated in (#65)
    ideas: list[ExploreIdea] = []
    warnings: list[AIWarning] = []


class ExpandRequest(BaseModel):
    """Request body for expanding an idea into a recipe draft."""
    idea: ExploreIdea
    # Output language (zh-CN, en, ja). Omitted: household setting, then
    # Accept-Language, then zh-CN (#65).
    locale: Optional[str] = Field(None, max_length=35)


class RecipeDraft(BaseModel):
    """An AI recipe draft, not saved (#65, #66 part 4).

    Same fields as RecipeCreate except that `category` may be null: the user
    picks one before saving. Missing values stay null; there are no
    invented defaults.
    """
    title: str
    category: Optional[RecipeCategory] = None
    description: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    servings: Optional[str] = None
    cook_time_minutes: Optional[int] = None
    raw_markdown: Optional[str] = None
    ingredients: list[IngredientSchema] = []
    steps: list[StepSchema] = []


class ExpandResponse(BaseModel):
    """Response from expanding an idea into a recipe draft."""
    recipe_draft: RecipeDraft
    draft_hash: str
    locale: str
    warnings: list[AIWarning] = []


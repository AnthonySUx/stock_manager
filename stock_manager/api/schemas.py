"""Pydantic schemas for request/response validation."""

from datetime import date, datetime
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator


# ─── Date fields (issue #43) ──────────────────────────────────────

INFINITE = "infinite"


def _check_date(value: str) -> str:
    """Accept a real calendar date in YYYY-MM-DD form."""
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("must be a valid date in YYYY-MM-DD format")
    if len(value) != 10 or parsed.isoformat() != value:
        raise ValueError("must be a valid date in YYYY-MM-DD format")
    return value


def _check_date_or_infinite(value: str) -> str:
    """Accept YYYY-MM-DD or the literal 'infinite' (never expires)."""
    if value == INFINITE:
        return value
    try:
        return _check_date(value)
    except ValueError:
        raise ValueError("must be a valid date in YYYY-MM-DD format or 'infinite'")


DateStr = Annotated[str, AfterValidator(_check_date)]
ExpirationStr = Annotated[str, AfterValidator(_check_date_or_infinite)]


# ─── Categories ───────────────────────────────────────────────────

RecipeUsage = Literal["always", "conditional", "never"]


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    parent_id: Optional[int] = None
    recipe_usage: Optional[RecipeUsage] = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    parent_id: Optional[int] = None
    recipe_usage: Optional[RecipeUsage] = None
    sort_order: Optional[int] = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    parent_id: Optional[int] = None
    recipe_usage: RecipeUsage
    is_system: bool
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CategoryTreeResponse(CategoryResponse):
    children: list["CategoryTreeResponse"] = []


# ─── Stock Items ─────────────────────────────────────────────────


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category_id: int = Field(..., gt=0)
    owner: str = Field(..., min_length=1, max_length=100)
    purchase_date: DateStr = Field(default_factory=lambda: date.today().isoformat())
    quantity_value: float = Field(..., gt=0)
    quantity_unit: str = Field(..., min_length=1, max_length=50)
    location: str = Field(..., min_length=1, max_length=100)
    unopened_expiration_date: ExpirationStr = Field(..., min_length=1)
    opened_expiration_date: Optional[ExpirationStr] = None
    opened_date: Optional[DateStr] = None
    current_expiration_date: ExpirationStr = Field(...)
    status: str = Field(default="active")
    notes: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category_id: Optional[int] = Field(None, gt=0)
    owner: Optional[str] = Field(None, min_length=1, max_length=100)
    purchase_date: Optional[DateStr] = None
    quantity_value: Optional[float] = Field(None, gt=0)
    quantity_unit: Optional[str] = Field(None, min_length=1, max_length=50)
    location: Optional[str] = Field(None, min_length=1, max_length=100)
    unopened_expiration_date: Optional[ExpirationStr] = None
    opened_expiration_date: Optional[ExpirationStr] = None
    opened_date: Optional[DateStr] = None
    current_expiration_date: Optional[ExpirationStr] = None
    status: Optional[str] = None
    notes: Optional[str] = None

    # Omitting a field leaves it unchanged; sending null for a NOT NULL
    # column is rejected with 422 instead of failing in the database.
    @field_validator(
        "name", "category_id", "owner", "purchase_date", "quantity_value",
        "quantity_unit", "location", "unopened_expiration_date",
        "current_expiration_date", "status",
        mode="before",
    )
    @classmethod
    def reject_null_for_required(cls, value, info):
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return value


class ConsumeRequest(BaseModel):
    quantity: float = Field(..., gt=0)
    add_to_restock: bool = False


class ItemResponse(BaseModel):
    id: int
    name: str
    category_id: int
    category: CategoryResponse
    owner: str
    purchase_date: str
    quantity_value: float
    quantity_unit: str
    location: str
    unopened_expiration_date: str
    opened_expiration_date: Optional[str] = None
    opened_date: Optional[str] = None
    current_expiration_date: str
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Restock Items ───────────────────────────────────────────────


class RestockItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category_id: Optional[int] = Field(None, gt=0)
    quantity_value: Optional[float] = Field(None, gt=0)
    quantity_unit: Optional[str] = Field(None, max_length=50)
    source_item_id: Optional[int] = Field(None, gt=0)
    notes: Optional[str] = None


class RestockItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category_id: Optional[int] = Field(None, gt=0)
    quantity_value: Optional[float] = Field(None, gt=0)
    quantity_unit: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = None
    notes: Optional[str] = None


class RestockDoneRequest(BaseModel):
    purchased_quantity: float = Field(..., gt=0)
    # Fields for adding to stock
    category_id: Optional[int] = Field(None, gt=0)
    owner: Optional[str] = None
    purchase_date: Optional[DateStr] = None
    location: Optional[str] = None
    unopened_expiration_date: Optional[ExpirationStr] = None
    opened_expiration_date: Optional[ExpirationStr] = None
    opened_date: Optional[DateStr] = None


class RestockItemResponse(BaseModel):
    id: int
    name: str
    category_id: Optional[int] = None
    category: Optional[CategoryResponse] = None
    quantity_value: Optional[float] = None
    quantity_unit: Optional[str] = None
    source_item_id: Optional[int] = None
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    done_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Settings ────────────────────────────────────────────────────


class SettingResponse(BaseModel):
    default_database: str
    expiration_reminder_days: str


class SettingUpdate(BaseModel):
    default_database: Optional[str] = None
    expiration_reminder_days: Optional[str] = None


# ─── Generic ─────────────────────────────────────────────────────


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    version: str


CategoryTreeResponse.model_rebuild()

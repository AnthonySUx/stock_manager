"""Pydantic schemas for request/response validation."""

from datetime import date, datetime
from typing import Annotated, Literal, Optional

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    field_validator,
    model_validator,
)

from stock_manager.api.errors import APIError


ItemStatus = Literal["active", "expiring soon", "expired", "consumed"]
RestockStatus = Literal["pending", "done"]
PositiveQuantity = Annotated[float, Field(gt=0, allow_inf_nan=False)]


def _strip_text(value):
    return value.strip() if isinstance(value, str) else value


StrippedNonEmpty = Annotated[str, BeforeValidator(_strip_text), Field(min_length=1)]


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


ShelfLifeDays = Annotated[int, Field(ge=1, le=3650, strict=True)]


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    parent_id: Optional[int] = None
    recipe_usage: Optional[RecipeUsage] = None
    default_shelf_life_days: Optional[ShelfLifeDays] = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    parent_id: Optional[int] = None
    recipe_usage: Optional[RecipeUsage] = None
    default_shelf_life_days: Optional[ShelfLifeDays] = None
    sort_order: Optional[int] = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    parent_id: Optional[int] = None
    recipe_usage: RecipeUsage
    default_shelf_life_days: Optional[int] = None
    is_system: bool
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CategoryTreeResponse(CategoryResponse):
    children: list["CategoryTreeResponse"] = []


# ─── Stock Items ─────────────────────────────────────────────────


class ItemCreate(BaseModel):
    name: StrippedNonEmpty = Field(..., max_length=255)
    category_id: int = Field(..., gt=0)
    owner: StrippedNonEmpty = Field(..., max_length=100)
    # Defaults to today in the household timezone; filled in by the router
    # because a schema default cannot read settings (#65).
    purchase_date: Optional[DateStr] = None
    quantity_value: PositiveQuantity
    quantity_unit: str = Field(..., min_length=1, max_length=50)
    location: StrippedNonEmpty = Field(..., max_length=100)
    unopened_expiration_date: ExpirationStr = Field(..., min_length=1)
    opened_expiration_date: Optional[ExpirationStr] = None
    opened_date: Optional[DateStr] = None
    current_expiration_date: Optional[ExpirationStr] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[StrippedNonEmpty] = Field(None, max_length=255)
    category_id: Optional[int] = Field(None, gt=0)
    owner: Optional[StrippedNonEmpty] = Field(None, max_length=100)
    purchase_date: Optional[DateStr] = None
    quantity_value: Optional[PositiveQuantity] = None
    quantity_unit: Optional[str] = Field(None, min_length=1, max_length=50)
    location: Optional[StrippedNonEmpty] = Field(None, max_length=100)
    unopened_expiration_date: Optional[ExpirationStr] = None
    opened_expiration_date: Optional[ExpirationStr] = None
    opened_date: Optional[DateStr] = None
    current_expiration_date: Optional[ExpirationStr] = None
    notes: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def reject_status(cls, data):
        if isinstance(data, dict) and "status" in data:
            raise APIError(422, "item_status_readonly", "Item status is read-only")
        return data

    # Omitting a field leaves it unchanged; sending null for a NOT NULL
    # column is rejected with 422 instead of failing in the database.
    @field_validator(
        "name", "category_id", "owner", "purchase_date", "quantity_value",
        "quantity_unit", "location", "unopened_expiration_date",
        "current_expiration_date",
        mode="before",
    )
    @classmethod
    def reject_null_for_required(cls, value, info):
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return value


class ConsumeRequest(BaseModel):
    quantity: PositiveQuantity
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
    status: ItemStatus
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Restock Items ───────────────────────────────────────────────


class RestockItemCreate(BaseModel):
    name: StrippedNonEmpty = Field(..., max_length=255)
    category_id: Optional[int] = Field(None, gt=0)
    quantity_value: Optional[PositiveQuantity] = None
    quantity_unit: Optional[str] = Field(None, max_length=50)
    source_item_id: Optional[int] = Field(None, gt=0)
    notes: Optional[str] = None


class RestockItemUpdate(BaseModel):
    name: Optional[StrippedNonEmpty] = Field(None, max_length=255)
    category_id: Optional[int] = Field(None, gt=0)
    quantity_value: Optional[PositiveQuantity] = None
    quantity_unit: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def reject_status(cls, data):
        if isinstance(data, dict) and "status" in data:
            raise APIError(422, "restock_status_readonly", "Restock status is read-only")
        return data

    @field_validator("name", mode="before")
    @classmethod
    def reject_null_name(cls, value):
        if value is None:
            raise ValueError("name cannot be null")
        return value


class RestockDoneRequest(BaseModel):
    purchased_quantity: PositiveQuantity
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
    status: RestockStatus
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    done_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Settings ────────────────────────────────────────────────────


# `default_database` was removed in #49: the API always uses MySQL. Old
# clients that still send it are not rejected; the field is ignored.
MAX_REMINDER_DAYS = 365


class SettingResponse(BaseModel):
    expiration_reminder_days: str
    # null = not set: the locale follows the device (Accept-Language) and
    # "today" uses the server's local date (#65).
    default_locale: Optional[str] = None
    default_timezone: Optional[str] = None


class SettingUpdate(BaseModel):
    # Whole days, 0-365, as a number or a numeric string. Stored and returned
    # as a string. Invalid values are a 422 (they used to become 2 silently).
    expiration_reminder_days: Optional[str] = None

    @field_validator("expiration_reminder_days", mode="before")
    @classmethod
    def check_reminder_days(cls, value):
        if value is None:
            return None
        # str() first: True, 1.5 and lists all fail the digit check below.
        text = str(value).strip()
        if not text.isascii() or not text.isdigit():
            raise ValueError("expiration_reminder_days must be a whole number of days")
        days = int(text)
        if days > MAX_REMINDER_DAYS:
            raise ValueError(f"expiration_reminder_days must be between 0 and {MAX_REMINDER_DAYS}")
        return str(days)

    # A supported locale (zh-CN, en, ja; tags such as "zh-Hans" or "en-US" are
    # normalized) or an IANA timezone name. "" clears the setting.
    default_locale: Optional[str] = None
    default_timezone: Optional[str] = None

    @field_validator("default_locale", mode="before")
    @classmethod
    def check_locale(cls, value):
        from stock_manager.api.localization import SUPPORTED_LOCALES, normalize_locale

        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("default_locale must be a string")
        if not value.strip():
            return ""
        locale = normalize_locale(value)
        if locale is None:
            raise ValueError(f"default_locale must be one of {', '.join(SUPPORTED_LOCALES)}")
        return locale

    @field_validator("default_timezone", mode="before")
    @classmethod
    def check_timezone(cls, value):
        from stock_manager.api.localization import validate_timezone

        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("default_timezone must be a string")
        if not value.strip():
            return ""
        return validate_timezone(value)


# ─── Generic ─────────────────────────────────────────────────────


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    version: str


CategoryTreeResponse.model_rebuild()

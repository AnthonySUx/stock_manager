"""Pydantic schemas for request/response validation."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── Stock Items ─────────────────────────────────────────────────


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=100)
    owner: str = Field(..., min_length=1, max_length=100)
    purchase_date: str = Field(default_factory=lambda: date.today().isoformat())
    quantity_value: float = Field(..., gt=0)
    quantity_unit: str = Field(..., min_length=1, max_length=50)
    location: str = Field(..., min_length=1, max_length=100)
    unopened_expiration_date: str = Field(..., min_length=1)
    opened_expiration_date: Optional[str] = None
    opened_date: Optional[str] = None
    current_expiration_date: str = Field(...)
    status: str = Field(default="active")
    notes: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    owner: Optional[str] = Field(None, min_length=1, max_length=100)
    purchase_date: Optional[str] = None
    quantity_value: Optional[float] = Field(None, gt=0)
    quantity_unit: Optional[str] = Field(None, min_length=1, max_length=50)
    location: Optional[str] = Field(None, min_length=1, max_length=100)
    unopened_expiration_date: Optional[str] = None
    opened_expiration_date: Optional[str] = None
    opened_date: Optional[str] = None
    current_expiration_date: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ConsumeRequest(BaseModel):
    quantity: float = Field(..., gt=0)
    add_to_restock: bool = False


class ItemResponse(BaseModel):
    id: int
    name: str
    category: str
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
    category: Optional[str] = Field(None, max_length=100)
    quantity_value: Optional[float] = Field(None, gt=0)
    quantity_unit: Optional[str] = Field(None, max_length=50)
    source_item_id: Optional[int] = None
    notes: Optional[str] = None


class RestockItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    quantity_value: Optional[float] = Field(None, gt=0)
    quantity_unit: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = None
    notes: Optional[str] = None


class RestockDoneRequest(BaseModel):
    purchased_quantity: float = Field(..., gt=0)
    # Fields for adding to stock
    owner: Optional[str] = None
    purchase_date: Optional[str] = None
    location: Optional[str] = None
    unopened_expiration_date: Optional[str] = None
    opened_expiration_date: Optional[str] = None
    opened_date: Optional[str] = None


class RestockItemResponse(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    quantity_value: Optional[float] = None
    quantity_unit: Optional[str] = None
    source_item_id: Optional[int] = None
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    done_at: Optional[datetime] = None

    shopping_checked: bool = False
    shopping_checked_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Restock Duplicate Detection ──────────────────────────────────


class RestockDuplicateCandidate(BaseModel):
    """A single pending restock item that may be a duplicate."""
    id: int
    name: str
    category: Optional[str] = None
    quantity_value: Optional[float] = None
    quantity_unit: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    match_confidence: str = "high"
    match_reason: str = ""


class RestockDuplicateResponse(BaseModel):
    """Response for restock duplicate detection."""
    query: str
    normalized_name: str
    candidates: list[RestockDuplicateCandidate] = []



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

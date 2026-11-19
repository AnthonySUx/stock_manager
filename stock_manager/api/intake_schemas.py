"""Request and response contracts for AI-assisted stock intake."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from stock_manager.api.recipe_schemas import AIWarning
from stock_manager.api.schemas import DateStr, ExpirationStr

MAX_DRAFT_ITEMS = 100
MAX_TEXT_LENGTH = 4000

ExpirationSource = Literal["printed", "stated", "estimated", "none"]
InputKind = Literal["text", "receipt", "product_closeup", "product_overview"]
RestockAction = Literal["done", "partial", "none"]
DeleteReason = Literal["user_requested", "duplicate", "non_product_line"]
QuestionCode = Literal["ambiguous_target", "ambiguous_quantity", "ambiguous_date"]
EditableField = Literal[
    "name", "quantity_value", "quantity_unit", "category_id", "owner", "location",
    "purchase_date", "unopened_expiration_date", "suggested_unopened_expiration_date",
    "expiration_source", "notes", "matched_restock_id",
]
TemporaryId = Annotated[str, Field(pattern=r"^cand_[0-9a-f]{8}$")]
PositiveQuantity = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Confidence = Annotated[float, Field(ge=0, le=1)]


class CandidateSource(BaseModel):
    input_kind: InputKind
    image_index: int | None = Field(None, ge=0)
    span: str | None = Field(None, max_length=200)


class IntakeCandidate(BaseModel):
    temporary_id: TemporaryId
    name: str | None = Field(None, max_length=255)
    raw_name: str | None = Field(None, max_length=255)
    quantity_value: PositiveQuantity | None = None
    quantity_unit: str | None = Field(None, max_length=50)
    category_id: int | None = Field(None, gt=0)
    owner: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=100)
    purchase_date: DateStr | None = None
    unopened_expiration_date: ExpirationStr | None = None
    suggested_unopened_expiration_date: DateStr | None = None
    expiration_source: ExpirationSource = "none"
    confidence: Confidence
    field_confidence: dict[EditableField, Confidence] = Field(default_factory=dict)
    warnings: list[AIWarning] = Field(default_factory=list)
    source: CandidateSource
    matched_restock_id: int | None = Field(None, gt=0)
    restock_action: RestockAction | None = None
    notes: str | None = None


class TextInput(BaseModel):
    type: Literal["text"]
    text: str


class IntakeDraft(BaseModel):
    items: list[IntakeCandidate]


class IntakeContext(BaseModel):
    locale: str | None = None
    timezone: str | None = None
    purchase_date: DateStr | None = None


class ParseRequest(BaseModel):
    input: TextInput
    draft: IntakeDraft
    context: IntakeContext = Field(default_factory=IntakeContext)


class AddOperation(BaseModel):
    op: Literal["add"]
    candidate: IntakeCandidate


class UpdateOperation(BaseModel):
    op: Literal["update"]
    temporary_id: TemporaryId
    changes: dict[EditableField | Literal["restock_action"], str | float | int | None]


class DeleteOperation(BaseModel):
    op: Literal["delete"]
    temporary_id: TemporaryId
    reason_code: DeleteReason


class ClarifyOperation(BaseModel):
    op: Literal["clarify"]
    temporary_ids: list[TemporaryId]
    question_code: QuestionCode
    question: str


IntakeOperation = Annotated[
    AddOperation | UpdateOperation | DeleteOperation | ClarifyOperation,
    Field(discriminator="op"),
]


class ParseResponse(BaseModel):
    operations: list[IntakeOperation]
    unparsed_fragments: list[str]
    locale: str
    warnings: list[AIWarning]


class ConfirmDefaults(BaseModel):
    owner: str | None = None
    location: str | None = None


class ConfirmItem(BaseModel):
    temporary_id: TemporaryId
    name: str | None = None
    category_id: int | None = None
    quantity_value: float | None = None
    quantity_unit: str | None = None
    purchase_date: str | None = None
    unopened_expiration_date: str | None = None
    opened_expiration_date: str | None = None
    opened_date: str | None = None
    owner: str | None = None
    location: str | None = None
    notes: str | None = None
    raw_name: str | None = Field(None, max_length=255)
    matched_restock_id: int | None = None
    restock_action: RestockAction | None = None


class ConfirmRequest(BaseModel):
    defaults: ConfirmDefaults = Field(default_factory=ConfirmDefaults)
    items: list[ConfirmItem] = Field(min_length=1, max_length=MAX_DRAFT_ITEMS)


class ConfirmedItem(BaseModel):
    temporary_id: TemporaryId
    item_id: int


class ConfirmResponse(BaseModel):
    created: list[ConfirmedItem]
    restock_done: list[int]
    restock_partial: list[int]
    warnings: list[AIWarning]

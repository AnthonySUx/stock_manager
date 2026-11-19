"""Optional receipt metadata carried by intake candidates."""

from typing import Literal

from pydantic import BaseModel, Field


ReceiptSpecificity = Literal["specific_product", "specific_receipt_label", "generic_category", "unknown"]
AliasMode = Literal["auto", "suggest", "blocked"]
ReceiptReviewReason = Literal[
    "first_seen", "generic_receipt_label", "low_confidence", "multi_mapped_alias",
    "inferred_fields", "alias_suggestion",
]


class ReceiptSuggestion(BaseModel):
    name: str
    source: Literal["user_alias_history"] = "user_alias_history"
    confirmed_count: int = Field(gt=0)


class ReceiptCandidateFields(BaseModel):
    specificity: ReceiptSpecificity | None = None
    alias_mode: AliasMode | None = None
    auto_apply_allowed: bool | None = None
    requires_user_review: bool | None = None
    review_reason: ReceiptReviewReason | None = None
    suggestions: list[ReceiptSuggestion] | None = Field(None, max_length=5)
    price: float | None = Field(None, ge=0, allow_inf_nan=False)
    generic_name: str | None = Field(None, max_length=255)
    store_name: str | None = Field(None, max_length=255)
    match_method: Literal["alias", "ai_knowledge"] | None = None

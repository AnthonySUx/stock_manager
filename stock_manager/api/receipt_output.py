"""Receipt-line metadata and review decisions for the intake parser."""

from dataclasses import dataclass
from math import isfinite
from typing import get_args

from stock_manager.api.ai_output import clean_enum, text_or_none, warning
from stock_manager.api.receipt_aliases import (
    AliasHistory, AliasKey, alias_key, may_auto_apply, normalize_raw_name, receipt_specificity,
)
from stock_manager.api.receipt_schemas import ReceiptSpecificity

_SPECIFICITIES = get_args(ReceiptSpecificity)
# The model has never seen a first-seen label confirmed, so its guess is capped.
FIRST_SEEN_MAX_CONFIDENCE = 0.5
_INFERRED_FIELDS = {
    "quantity_unit": "quantity_unit_inferred",
    "location": "location_inferred",
    "unopened_expiration_date": "expiration_date_inferred",
}


def _bounded_text(value, limit: int = 255) -> str | None:
    text = text_or_none(value) if isinstance(value, str) else None
    return text[:limit] if text is not None else None


def _price(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if isfinite(number) and number >= 0 else None


@dataclass(frozen=True)
class ReceiptLine:
    raw_name: str | None
    store_name: str | None
    generic_name: str | None
    specificity: ReceiptSpecificity
    price: float | None
    group: str | int | None
    key: AliasKey | None
    inferred_fields: tuple[str, ...]


def receipt_line(raw: dict, source: dict) -> ReceiptLine:
    name = _bounded_text(raw.get("raw_name"))
    store = _bounded_text(raw.get("store_name"))
    group = _bounded_text(raw.get("receipt_group"), 64) or source.get("image_index")
    inferred = raw.get("inferred_fields")
    return ReceiptLine(
        raw_name=name,
        store_name=store,
        generic_name=_bounded_text(raw.get("generic_name")),
        specificity=receipt_specificity(
            normalize_raw_name(name or ""),
            clean_enum(raw.get("specificity"), _SPECIFICITIES, "specificity", []),
        ),
        price=_price(raw.get("price")),
        group=group,
        key=alias_key(store, name) if name else None,
        inferred_fields=tuple(
            field for field in _INFERRED_FIELDS if isinstance(inferred, list) and field in inferred
        ),
    )


def apply_receipt_line(
    line: ReceiptLine, history: AliasHistory | None, fields: dict, confidence: float,
    warnings: list[dict],
) -> dict:
    """Apply a confirmed alias or expose reviewable suggestions."""
    generic = line.specificity == "generic_category"
    auto = bool(
        history and history.mode == "auto" and history.category_id is not None
        and may_auto_apply(history.specificity, history.confirmed_count, history.distinct_names)
        and may_auto_apply(line.specificity, history.confirmed_count, history.distinct_names)
    )
    first_seen = history is None
    # A first-seen label the model could not identify gets no guessed name (#84).
    # Without raw_name there is nothing to review instead, so the name stays.
    unidentified = first_seen and line.specificity == "unknown" and line.raw_name is not None
    if generic or unidentified:
        fields["name"] = None
    if first_seen:
        confidence = min(confidence, FIRST_SEEN_MAX_CONFIDENCE)
    if auto:
        fields.update(
            name=history.confirmed_name,
            category_id=history.category_id,
            quantity_unit=history.quantity_unit,
        )
    for field in line.inferred_fields:
        if field != "quantity_unit" or not auto:
            warnings.append(warning(_INFERRED_FIELDS[field], field=field))

    return {
        "specificity": line.specificity,
        "alias_mode": "auto" if auto else ("blocked" if history and history.mode == "blocked" else "suggest"),
        "auto_apply_allowed": auto,
        "requires_user_review": not auto,
        "suggestions": [
            {"name": name, "source": "user_alias_history", "confirmed_count": count}
            for name, count in history.names
        ] if history and not auto else [],
        "price": line.price,
        "raw_name": line.raw_name,
        "generic_name": line.generic_name,
        "store_name": line.store_name,
        "match_method": "alias" if auto else "ai_knowledge",
        "confidence": max(0.9, confidence) if auto else confidence,
    }


def receipt_review_reason(
    line: ReceiptLine, history: AliasHistory | None, confidence: float, warnings: list[dict],
) -> str:
    if line.specificity == "generic_category":
        return "generic_receipt_label"
    if history is None:
        return "first_seen"
    if history.distinct_names > 1:
        return "multi_mapped_alias"
    if confidence < 0.6:
        return "low_confidence"
    if any(item["code"] in _INFERRED_FIELDS.values() for item in warnings):
        return "inferred_fields"
    return "alias_suggestion"

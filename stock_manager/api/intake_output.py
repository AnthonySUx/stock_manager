"""Validate the intake operations received from the model."""

from calendar import monthrange
from datetime import date, timedelta
from math import isfinite
from typing import TYPE_CHECKING, get_args
from uuid import uuid4

from stock_manager.api.ai_output import (
    Inventory,
    clean_enum,
    clean_quantity,
    dedupe_warnings,
    in_locale,
    positive_int_or_none,
    text_or_none,
    warning,
)
from stock_manager.api.intake_schemas import (
    DeleteReason,
    EditableField,
    ExpirationSource,
    ImageKind,
    IntakeCandidate,
    QuestionCode,
)
from stock_manager.api.quantity import same_unit
from stock_manager.api.receipt_aliases import AliasHistory
from stock_manager.api.receipt_output import ReceiptLine, apply_receipt_line, receipt_line, receipt_review_reason

if TYPE_CHECKING:
    from stock_manager.api.intake_services import PreparedParse

EDITABLE_FIELDS = frozenset(get_args(EditableField))
_EXPIRATION_SOURCES = get_args(ExpirationSource)
_DELETE_REASONS = get_args(DeleteReason)
_QUESTION_CODES = get_args(QuestionCode)
_IMAGE_KINDS = get_args(ImageKind)
_TEXT_LIMITS = {"name": 255, "quantity_unit": 50, "owner": 100, "location": 100, "notes": None}
_DATE_FIELDS = {"purchase_date", "unopened_expiration_date", "suggested_unopened_expiration_date"}
_EXPIRATION_VALUES = {"unopened_expiration_date", "suggested_unopened_expiration_date", "expiration_source"}
_EXPIRATION_FIELDS = _DATE_FIELDS | {"category_id", "expiration_source"}
_RESTOCK_FIELDS = {"matched_restock_id", "quantity_value", "quantity_unit"}


def _text(value, limit: int | None = None) -> str | None:
    text = text_or_none(value) if isinstance(value, str) else None
    return text[:limit] if text is not None else None


def _numeric(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _quantity(value, locale: str) -> float | None:
    if isinstance(value, str):
        # The shared grammar also understands recipe units, but intake takes
        # quantity and unit in separate fields and accepts custom unit names.
        value, unit, ok = clean_quantity(value, None, locale, None)
        if not ok or unit is not None:
            return None
    number = _numeric(value)
    return number if number is not None and number > 0 else None


def _confidence(value) -> float:
    number = _numeric(value)
    return max(0.0, min(1.0, number)) if number is not None else 0.0


def _parse_date(value, field: str, today: date) -> str | None:
    if value == "infinite" and field == "unopened_expiration_date":
        return value
    parsed = _iso_date(value)
    if parsed is not None and _date_in_window(parsed, today):
        return value
    return None


def _iso_date(value) -> date | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _date_in_window(parsed: date, today: date) -> bool:
    last_day = monthrange(today.year + 5, today.month)[1]
    limit = today.replace(year=today.year + 5, day=min(today.day, last_day))
    return today - timedelta(days=30) <= parsed <= limit


def _printed_value(printed: dict) -> date | None:
    start = _iso_date(printed.get("date"))
    kind = printed.get("kind")
    if start is None or kind not in ("best_before", "use_by", "production_plus_shelf_life"):
        return None
    if kind in ("best_before", "use_by"):
        return start

    shelf_life = printed.get("shelf_life")
    if not isinstance(shelf_life, dict):
        return None
    value, unit = shelf_life.get("value"), shelf_life.get("unit")
    if type(value) is not int or value <= 0 or unit not in ("day", "month", "year"):
        return None
    try:
        if unit == "day":
            return start + timedelta(days=value)
        months = value * 12 if unit == "year" else value
        year, month_index = divmod(start.year * 12 + start.month - 1 + months, 12)
        month = month_index + 1
        return date(year, month, min(start.day, monthrange(year, month)[1]))
    except (OverflowError, ValueError):
        return None


def printed_expiration(printed, today: date) -> tuple[date | None, list[dict]]:
    """Resolve structured label evidence. A date with warnings is only a suggestion."""
    if not isinstance(printed, dict):
        return None, [warning("printed_date_unclear")]
    expiration = _printed_value(printed)
    if (
        expiration is None or printed.get("readable") is not True
        or not _text(printed.get("raw")) or not _date_in_window(expiration, today)
    ):
        return expiration, [warning("printed_date_unclear")]
    return expiration, []


def _extract_printed(
    raw: dict, source: dict | None, today: date, warnings: list[dict], *, receipt_add_image_count: int = 0,
) -> tuple[dict, tuple[date | None, list[dict]] | None]:
    if "printed" not in raw:
        return raw, None
    printed = raw["printed"]
    kind = source.get("input_kind") if source else None
    allowed = kind == "product_closeup"
    if kind == "receipt" and receipt_add_image_count and isinstance(printed, dict):
        index = printed.get("image_index")
        allowed = type(index) is int and 0 <= index < receipt_add_image_count and index != source["image_index"]

    # Image evidence cannot fall back to a model-computed expiration accompanying the label.
    fields = {
        key: value for key, value in raw.items()
        if key != "printed" and (source is None or key not in _EXPIRATION_VALUES)
    }
    if not allowed:
        warnings.append(warning("printed_evidence_dropped"))
        return fields, None
    return fields, printed_expiration(printed, today)


def _known_id(value, entries: dict[int, dict]) -> int | None:
    # Bound digit strings before conversion to avoid Python's large-int limit.
    if isinstance(value, str) and len(value.strip()) > 20:
        return None
    key = positive_int_or_none(value)
    return key if key in entries else None


def _clean_fields(raw: dict, context: "PreparedParse", warnings: list[dict]) -> dict:
    """Clean values shared by add candidates and update changes."""
    fields = {}
    for field, value in raw.items():
        if field in _TEXT_LIMITS:
            fields[field] = _text(value, _TEXT_LIMITS[field])
            code = "field_value_dropped"
        elif field in _DATE_FIELDS:
            fields[field] = _parse_date(value, field, context.today)
            code = "date_dropped"
        elif field == "quantity_value":
            fields[field] = _quantity(value, context.locale)
            code = "quantity_dropped"
        elif field == "category_id":
            fields[field] = _known_id(value, context.categories)
            code = "category_dropped"
        elif field == "matched_restock_id":
            fields[field] = _known_id(value, context.restock)
            code = "restock_match_dropped"
        else:
            fields[field] = clean_enum(value, _EXPIRATION_SOURCES, field, [])
            code = "field_value_dropped"
        if value is not None and fields[field] is None:
            warnings.append(warning(code, field=field))
    return fields


def _add_candidate(
    raw: dict, context: "PreparedParse", used_ids: set[str], source: dict | None = None,
    *, receipt: tuple[ReceiptLine, AliasHistory | None] | None = None, image_count: int = 0,
) -> dict | None:
    warnings: list[dict] = []
    raw, printed = _extract_printed(raw, source, context.today, warnings, receipt_add_image_count=image_count)
    fields = _clean_fields(
        {key: value for key, value in raw.items() if key in EDITABLE_FIELDS},
        context, warnings,
    )
    confidence = _confidence(raw.get("confidence"))
    metadata = {}
    if receipt is not None:
        line, history = receipt
        if context.purchase_date_explicit:
            fields["purchase_date"] = context.purchase_date.isoformat()
        elif fields.get("purchase_date"):
            warnings.append(warning("purchase_date_from_receipt"))
        metadata = apply_receipt_line(line, history, fields, confidence, warnings)
    generic = metadata.get("specificity") == "generic_category" and metadata.get("raw_name")
    if not fields.get("name") and not generic:
        return None
    if fields.get("purchase_date") is None:
        fields["purchase_date"] = context.purchase_date.isoformat()
    fields.update(_expiration_changes(fields, {}, context, warnings, allow_stated=source is None, printed=printed))
    if receipt is not None:
        metadata["review_reason"] = (
            None if metadata["auto_apply_allowed"] else receipt_review_reason(line, history, confidence, warnings)
        )
    if source is None:
        raw_source = raw.get("source")
        source = {
            "input_kind": "receipt" if receipt is not None else "text",
            "span": _text(raw_source.get("span"), 200) if isinstance(raw_source, dict) else None,
        }
    raw_confidence = raw.get("field_confidence")
    field_confidence = {
        key: _confidence(value) for key, value in raw_confidence.items() if key in EDITABLE_FIELDS
    } if isinstance(raw_confidence, dict) else {}
    if source["input_kind"] == "product_overview":
        quantity_score = field_confidence.get("quantity_value", 0.5)
        inferred = raw.get("inferred_fields")
        if (
            fields.get("quantity_value") is None or quantity_score <= 0.5
            or raw.get("quantity_value_inferred") is True
            or (isinstance(inferred, list) and "quantity_value" in inferred)
        ):
            field_confidence["quantity_value"] = min(quantity_score, 0.5)
            warnings.append(warning("quantity_value_inferred"))
    return {
        **fields,
        "temporary_id": _new_id(used_ids),
        "raw_name": _text(raw.get("raw_name"), 255),
        "confidence": confidence,
        "field_confidence": field_confidence,
        "warnings": dedupe_warnings(warnings),
        "source": source,
        "restock_action": _restock_action(fields, context.restock),
        **metadata,
    }


def _update_changes(raw: dict, context: "PreparedParse", warnings: list[dict]) -> dict:
    editable = {}
    for key, value in raw.items():
        if key in EDITABLE_FIELDS:
            editable[key] = value
        else:
            warnings.append(warning("op_field_dropped", field=key))
    changes = _clean_fields(editable, context, warnings)
    # Only an explicit null can clear a field the model tried to update.
    return {
        key: value for key, value in changes.items()
        if value is not None or editable[key] is None
    }


def _expiration_changes(
    fields: dict, previous: dict, context: "PreparedParse", warnings: list[dict], *, allow_stated: bool,
    printed: tuple[date | None, list[dict]] | None = None,
) -> dict:
    actual_field = "unopened_expiration_date"
    suggestion_field = "suggested_unopened_expiration_date"
    effective = {**previous, **fields}
    purchase_date = effective.get("purchase_date")
    purchased = date.fromisoformat(purchase_date) if purchase_date else context.purchase_date
    new_date = fields.get(actual_field)
    prior_date = previous.get(actual_field)
    prior_source = previous.get("expiration_source")
    new_suggestion = fields.get(suggestion_field)
    printed_date, printed_warnings = printed if printed is not None else (None, [])
    warnings.extend(printed_warnings)
    if printed_date is not None:
        if not printed_warnings:
            actual, suggested, source = printed_date.isoformat(), None, "printed"
        else:
            suggested = printed_date.isoformat()
            if prior_date and prior_source in ("printed", "stated"):
                actual, source = prior_date, prior_source
            else:
                actual, source = None, "estimated"
    elif allow_stated and new_date is not None and fields.get("expiration_source") == "stated":
        actual, suggested, source = new_date, None, "stated"
    elif prior_date and prior_source in ("printed", "stated") and (
        actual_field not in fields or new_date is not None
    ):
        # A new model date without a stated source cannot replace a trusted draft date.
        actual, suggested, source = prior_date, previous.get(suggestion_field), prior_source
        if new_date and new_date != actual:
            warnings.append(warning("ai_expiration_ignored", date=new_date))
    else:
        actual = None
        inferred = _category_expiration(effective.get("category_id"), purchased, context, warnings)
        if inferred is not None:
            suggested = inferred
            warnings.append(warning("expiration_date_inferred", basis="category_default"))
            for model_date in (new_date, new_suggestion):
                if model_date is not None:
                    warnings.append(warning("ai_expiration_ignored", date=model_date))
        else:
            suggested = effective.get(suggestion_field)
            if new_date and new_date != "infinite":
                suggested = new_date
                warnings.append(warning("expiration_moved_to_suggested"))
            elif new_date == "infinite":
                warnings.append(warning("date_dropped", field=actual_field))
        source = "estimated" if suggested is not None else "none"

    expiration = actual or suggested
    if expiration and expiration != "infinite" and date.fromisoformat(expiration) < purchased:
        warnings.append(warning("expiration_before_purchase"))
    result = {actual_field: actual, suggestion_field: suggested, "expiration_source": source}
    if not previous:
        return result
    if printed_date is None:
        evidence_fields = set()
    else:
        evidence_fields = {suggestion_field} if printed_warnings else {actual_field, "expiration_source"}
    return {
        key: value for key, value in result.items()
        if key in fields or key in evidence_fields or value != previous.get(key)
    }


def _category_expiration(
    category_id: int | None, purchased: date, context: "PreparedParse", warnings: list[dict]
) -> str | None:
    days = context.categories.get(category_id, {}).get("default_shelf_life_days")
    if days is None:
        return None
    try:
        return (purchased + timedelta(days=days)).isoformat()
    except OverflowError:
        warnings.append(warning("date_dropped", field="suggested_unopened_expiration_date"))
        return None


def _restock_action(candidate: dict, restock: dict[int, dict]) -> str | None:
    item = restock.get(candidate.get("matched_restock_id"))
    if item is None:
        return None
    quantity = candidate.get("quantity_value")
    if (
        quantity is None
        or item["quantity_value"] is None
        or not same_unit(candidate.get("quantity_unit"), item["quantity_unit"])
    ):
        return "none"
    return "done" if quantity >= item["quantity_value"] else "partial"


def _new_id(used_ids: set[str]) -> str:
    while True:
        temporary_id = f"cand_{uuid4().hex[:8]}"
        if temporary_id not in used_ids:
            used_ids.add(temporary_id)
            return temporary_id


def _draft_operation(row: dict, draft: dict, locale: str, inventory: Inventory) -> tuple[dict | None, str | None]:
    """Check an operation's structure, targets and fixed enums."""
    op = row.get("op")
    if op == "add":
        candidate = row.get("candidate")
        if not isinstance(candidate, dict):
            return None, "op_invalid"
        if "printed" in row and "printed" not in candidate:
            row = {**row, "candidate": {**candidate, "printed": row["printed"]}}
        return row, None
    if op == "clarify":
        ids = row.get("temporary_ids")
        if not isinstance(ids, list) or not ids or not all(isinstance(key, str) for key in ids):
            return None, "op_invalid"
        if any(key not in draft for key in ids):
            return None, "op_target_unknown"
        code = clean_enum(row.get("question_code"), _QUESTION_CODES, "question_code", [])
        question = _text(row.get("question"))
        if not code or not question or len(question) > 200 or not in_locale(question, locale, inventory):
            return None, "op_invalid"
        return {"op": op, "temporary_ids": ids, "question_code": code, "question": question}, None
    if op in ("update", "delete"):
        target = row.get("temporary_id")
        if not isinstance(target, str) or target not in draft:
            return None, "op_target_unknown"
        if op == "delete":
            reason = clean_enum(row.get("reason_code"), _DELETE_REASONS, "reason_code", [])
            if reason is None:
                return None, "op_invalid"
            return {"op": op, "temporary_id": target, "reason_code": reason}, None
        changes = row.get("changes")
        if isinstance(changes, dict):
            if "printed" in row and "printed" not in changes:
                changes = {**changes, "printed": row["printed"]}
            return {"op": op, "temporary_id": target, "changes": changes}, None
    return None, "op_invalid"


def _prepare_operations(
    rows: list, draft: dict, locale: str, inventory: Inventory, warnings: list[dict],
    *, image_count: int = 0,
) -> list[tuple[int, dict]]:
    valid: list[tuple[int, dict]] = []
    deletes: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            warnings.append(warning("op_invalid", index=index))
            continue
        source = _image_source(row.get("source"), image_count) if image_count else None
        if image_count and source is None:
            warnings.append(warning("op_invalid", index=index))
            continue
        operation, error = _draft_operation(row, draft, locale, inventory)
        if operation is None:
            warnings.append(warning(error, index=index))
            continue
        if source is not None:
            operation = {**operation, "source": source}
        if operation["op"] == "delete":
            deletes.add(operation["temporary_id"])
        valid.append((index, operation))

    operations = []
    for index, operation in valid:
        if operation["op"] == "update" and operation["temporary_id"] in deletes:
            warnings.append(warning("op_conflict", index=index))
        else:
            operations.append((index, operation))
    return operations


def _image_source(raw, image_count: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    index = raw.get("image_index")
    kind = raw.get("input_kind")
    if type(index) is not int or not 0 <= index < image_count or kind not in _IMAGE_KINDS:
        return None
    return {"image_index": index, "input_kind": kind, "span": _text(raw.get("span"), 200)}


def find_receipt_lines(reply: dict, image_count: int) -> dict[int, ReceiptLine]:
    """Recognize receipt adds from the model's source classification."""
    lines = {}
    for index, operation in enumerate(reply["operations"]):
        if not isinstance(operation, dict) or operation.get("op") != "add":
            continue
        raw = operation.get("candidate")
        if not isinstance(raw, dict):
            continue
        source = _image_source(operation.get("source"), image_count) if image_count else raw.get("source")
        if isinstance(source, dict) and source.get("input_kind") == "receipt":
            lines[index] = receipt_line(raw, source)
    return lines


def _fragments(values) -> list[str]:
    if not isinstance(values, list):
        return []
    fragments = []
    for value in values:
        fragment = _text(value, 200)
        if fragment is not None:
            fragments.append(fragment)
            if len(fragments) == 20:
                break
    return fragments


def clean_parse_output(
    reply: dict, items: list[IntakeCandidate], context: "PreparedParse", *, image_count: int = 0,
    receipts: dict[int, tuple[ReceiptLine, AliasHistory | None]] | None = None,
) -> dict:
    """Return validated operations in the order the app applies them."""
    draft = {item.temporary_id: item.model_dump() for item in items}
    inventory = Inventory(list(draft.values()))
    used_ids = set(draft)
    warnings = list(context.warnings)
    seen_generic: set[tuple] = set()
    operations: list[dict] = []
    prepared = _prepare_operations(
        reply["operations"], draft, context.locale, inventory, warnings, image_count=image_count,
    )
    for index, operation in prepared:
        match operation["op"]:
            case "add":
                source = operation.get("source") if image_count else None
                receipt = (receipts or {}).get(index)
                candidate = _add_candidate(
                    operation["candidate"], context, used_ids, source, receipt=receipt, image_count=image_count,
                )
                if candidate is None:
                    warnings.append(warning("op_invalid", index=index))
                    continue
                if receipt and receipt[0].specificity == "generic_category" and receipt[0].key:
                    line = receipt[0]
                    duplicate_key = (line.group, line.key)
                    if duplicate_key in seen_generic:
                        candidate["warnings"].append(warning("duplicate_generic_line"))
                    seen_generic.add(duplicate_key)
                operation = {"op": "add", "candidate": candidate}
                if source is not None:
                    operation["source"] = source
            case "update":
                field_warnings: list[dict] = []
                raw_changes, printed = _extract_printed(
                    operation["changes"], operation.get("source"), context.today, field_warnings,
                )
                changes = _update_changes(raw_changes, context, field_warnings)
                warnings.extend(
                    warning(w["code"], index=index, **w["params"])
                    if w["code"] == "op_field_dropped" else w
                    for w in field_warnings
                )
                if not changes and (printed is None or printed[0] is None):
                    if printed is not None:
                        warnings.extend(printed[1])
                    warnings.append(warning("op_invalid", index=index))
                    continue
                field_warnings = []
                key = operation["temporary_id"]
                previous = draft[key]
                if _EXPIRATION_FIELDS.intersection(changes) or printed is not None:
                    changes.update(_expiration_changes(
                        changes, previous, context, field_warnings, allow_stated=image_count == 0, printed=printed,
                    ))
                match_id = changes.get("matched_restock_id", previous.get("matched_restock_id"))
                if _RESTOCK_FIELDS.intersection(changes) and (
                    match_id is not None or "matched_restock_id" in changes
                ):
                    merged = {**previous, **changes}
                    if match_id is not None and match_id not in context.restock:
                        changes["matched_restock_id"] = None
                        field_warnings.append(warning("restock_match_dropped", field="matched_restock_id"))
                    changes["restock_action"] = _restock_action(merged, context.restock)
                warnings.extend(field_warnings)
                operation["changes"] = changes
                draft[key] = {**previous, **changes}
        operations.append(operation)
    dropped = len(reply["operations"]) - len(operations)
    if dropped:
        warnings.append(warning("ops_dropped", count=dropped))
    return {
        "operations": operations,
        "unparsed_fragments": _fragments(reply.get("unparsed_fragments")),
        "locale": context.locale,
        "warnings": dedupe_warnings(warnings),
    }

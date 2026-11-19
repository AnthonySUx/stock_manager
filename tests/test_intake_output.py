"""Validation of untrusted text intake output before it reaches the client."""

from datetime import date
from types import SimpleNamespace

import pytest

from stock_manager.api import intake_output
from stock_manager.api.ai_output import Inventory
from stock_manager.api.intake_services import PreparedParse


@pytest.fixture
def context():
    return PreparedParse(
        locale="en",
        warnings=[],
        today=date(2028, 2, 29),
        purchase_date=date(2028, 2, 28),
        categories={7: {"default_shelf_life_days": 7}},
        restock={
            1: {"quantity_value": 6, "quantity_unit": "pcs"},
            2: {"quantity_value": None, "quantity_unit": "pcs"},
        },
    )


def test_add_sanitizes_model_fields_and_assigns_unused_id(context, monkeypatch):
    uuids = iter(["00000001", "00000002"])
    monkeypatch.setattr(intake_output, "uuid4", lambda: SimpleNamespace(hex=next(uuids)))
    candidate = intake_output._add_candidate({
        "temporary_id": "cand_88888888",
        "name": "  Eggs  ",
        "raw_name": "raw " * 100,
        "quantity_value": "3",
        "quantity_unit": "个",
        "category_id": "7",
        "purchase_date": None,
        "confidence": 2,
        "field_confidence": {"name": -1, "notes": 0.7, "temporary_id": 0.9},
        "matched_restock_id": 1,
        "restock_action": "done",
        "warnings": [{"code": "injected"}],
        "source": {"input_kind": "receipt", "image_index": 5, "span": "s" * 210},
    }, context, Inventory([]), {"cand_00000001"})
    assert candidate["temporary_id"] == "cand_00000002"
    assert candidate["name"] == "Eggs"
    assert len(candidate["raw_name"]) == 255
    assert candidate["quantity_value"] == 3
    assert candidate["quantity_unit"] == "个"
    assert candidate["category_id"] == 7
    assert candidate["purchase_date"] == "2028-02-28"
    assert candidate["confidence"] == 1
    assert candidate["field_confidence"] == {"name": 0, "notes": 0.7}
    assert candidate["matched_restock_id"] == 1
    assert candidate["restock_action"] == "partial"
    assert candidate["source"] == {"input_kind": "text", "span": "s" * 200}
    assert candidate["warnings"] == [
        {"code": "expiration_date_inferred", "params": {"basis": "category_default"}},
    ]


def test_add_clears_invalid_fields_and_rejects_wrong_language_name(context):
    candidate = intake_output._add_candidate({
        "name": "Milk",
        "quantity_value": -1,
        "quantity_unit": "bottle",
        "category_id": 99,
        "purchase_date": "2028-02-30",
        "matched_restock_id": "9" * 5000,
        "confidence": "NaN",
    }, context, Inventory([]), set())
    assert candidate["quantity_value"] is None
    assert candidate["quantity_unit"] == "bottle"
    assert candidate["category_id"] is None
    assert candidate["purchase_date"] is None
    assert candidate["matched_restock_id"] is None
    assert candidate["restock_action"] is None
    assert candidate["confidence"] == 0
    assert {w["code"] for w in candidate["warnings"]} == {
        "quantity_dropped", "category_dropped", "date_dropped", "restock_match_dropped",
    }
    assert intake_output._add_candidate({"name": "牛奶"}, context, Inventory([]), set()) is None
    assert intake_output._add_candidate({"name": []}, context, Inventory([]), set()) is None


@pytest.mark.parametrize(("date_value", "expected"), [
    ("2028-01-29", None),
    ("2028-01-30", "2028-01-30"),
    ("2033-02-28", "2033-02-28"),
    ("2033-03-01", None),
    ("20280229", None),
    ("infinite", "infinite"),
])
def test_date_validation_uses_calendar_bounds(context, date_value, expected):
    assert intake_output._parse_date(date_value, "unopened_expiration_date", context.today) == expected
    assert intake_output._parse_date("infinite", "suggested_unopened_expiration_date", context.today) is None


@pytest.mark.parametrize(("quantity", "unit", "match", "action"), [
    (6, "个", 1, "done"),
    (8, "piece", 1, "done"),
    (3, "pcs", 1, "partial"),
    (6, "kg", 1, "none"),
    (None, "pcs", 1, "none"),
    (6, "pcs", 2, "none"),
    (6, None, 1, "none"),
    (6, "pcs", 3, None),
])
def test_restock_action_is_based_on_quantity_and_same_unit(context, quantity, unit, match, action):
    assert intake_output._restock_action({
        "quantity_value": quantity, "quantity_unit": unit, "matched_restock_id": match,
    }, context.restock) == action


def test_changes_ignore_other_keys(context):
    warnings = []
    changes = intake_output._update_changes({
        "restock_action": "done",
        "temporary_id": "cand_00000001",
        "notes": "  Note  ",
        "quantity_value": True,
    }, context, Inventory([]), warnings)
    assert changes == {"notes": "Note", "quantity_value": None}
    assert [w["code"] for w in warnings] == [
        "op_field_dropped", "op_field_dropped", "quantity_dropped",
    ]


def test_operation_targets_language_and_update_delete_conflicts():
    key = "cand_00000001"
    missing_key = "cand_00008888"
    draft = {key: {"name": "牛奶"}}
    inventory = Inventory(list(draft.values()))
    question = {"op": "clarify", "temporary_ids": [key], "question_code": "ambiguous_date"}
    warnings = []
    operations = intake_output._prepare_operations([
        {"op": "update", "temporary_id": key, "changes": {"notes": "New"}},
        {"op": "delete", "temporary_id": key, "reason_code": "duplicate"},
        {"op": "delete", "temporary_id": key, "reason_code": "made_up"},
        {"op": "update", "temporary_id": missing_key, "changes": {"notes": "Missing"}},
        {**question, "question": "When does 牛奶 expire?"},
        {**question, "question": "哪瓶牛奶？"},
        {**question, "question": "?" * 201},
        {**question, "question": "Which one?", "temporary_ids": [key, missing_key]},
        {**question, "question": "Which one?", "temporary_ids": [6]},
        {"op": "add", "candidate": None},
        None,
    ], draft, "en", inventory, warnings)
    assert [(index, op["op"]) for index, op in operations] == [(1, "delete"), (4, "clarify")]
    assert {w["params"]["index"]: w["code"] for w in warnings} == {
        "0": "op_conflict", "2": "op_invalid", "3": "op_target_unknown", "5": "op_invalid",
        "6": "op_invalid", "7": "op_target_unknown", "8": "op_invalid",
        "9": "op_invalid", "10": "op_invalid",
    }


def test_unparsed_fragments_are_trimmed_and_bounded():
    assert intake_output._fragments(["  Text  ", None, " " * 5, "x" * 250] + ["part"] * 30) == [
        "Text", "x" * 200, *(["part"] * 18),
    ]
    assert intake_output._fragments("unparsed") == []

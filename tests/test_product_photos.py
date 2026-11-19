"""Structured printed-date and product-overview tests with mocked vision."""

import json
from datetime import date

import pytest

from stock_manager.api import ai_client, intake_services
from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.intake_output import printed_expiration

PARSE = "/api/intake/parse"
TODAY = date(2026, 11, 20)
DRAFT_ID = "cand_12345678"
UNCLEAR = {"code": "printed_date_unclear", "params": {}}
EVIDENCE_DROPPED = {"code": "printed_evidence_dropped", "params": {}}
QUANTITY_INFERRED = {"code": "quantity_value_inferred", "params": {}}


def _label(value, kind="best_before", **overrides):
    return {"kind": kind, "raw": "Label date " + value, "date": value, "readable": True, **overrides}


def _shelf(start, amount, unit, **overrides):
    return _label(start, "production_plus_shelf_life", shelf_life={"value": amount, "unit": unit}, **overrides)


@pytest.mark.parametrize(("printed", "expected"), [
    (_label("2026-10-21"), date(2026, 10, 21)),
    (_label("2031-11-20", "use_by"), date(2031, 11, 20)),
    (_label("2028-02-29", "use_by"), date(2028, 2, 29)),
    (_shelf("2026-11-01", 180, "day"), date(2027, 4, 30)),
    (_shelf("2026-12-31", 1, "day"), date(2027, 1, 1)),
    (_shelf("2028-02-28", 1, "day"), date(2028, 2, 29)),
    (_shelf("2027-01-31", 1, "month"), date(2027, 2, 28)),
    (_shelf("2028-01-31", 1, "month"), date(2028, 2, 29)),
    (_shelf("2026-12-31", 2, "month"), date(2027, 2, 28)),
    (_shelf("2027-05-31", 13, "month"), date(2028, 6, 30)),
    (_shelf("2028-02-29", 1, "year"), date(2029, 2, 28)),
    (_shelf("2023-11-20", 4, "year"), date(2027, 11, 20)),
])
def test_printed_expiration_calculates_calendar_dates(printed, expected):
    assert printed_expiration(printed, TODAY) == (expected, [])


@pytest.mark.parametrize(("printed", "suggestion"), [
    (None, None),
    ("Best before 2027-01-31", None),
    ({}, None),
    (_label("2027-02-29"), None),
    (_label("2027-01-31", "unknown"), None),
    (_label("2027-01-31", "production_plus_shelf_life"), None),
    (_label("2027-01-31", readable=False), date(2027, 1, 31)),
    (_label("2027-01-31", readable="true"), date(2027, 1, 31)),
    (_label("2027-01-31", raw=" "), date(2027, 1, 31)),
    (_label("2026-10-20"), date(2026, 10, 20)),
    (_label("2031-11-21", "use_by"), date(2031, 11, 21)),
    (_shelf("2029-01-31", 3, "year"), date(2032, 1, 31)),
    (_shelf("2027-01-31", True, "month"), None),
    (_shelf("2027-01-31", 0, "month"), None),
    (_shelf("2027-01-31", -1, "month"), None),
    (_shelf("2027-01-31", 1.5, "month"), None),
    (_shelf("2027-01-31", 1, "week"), None),
    (_shelf("2027-01-31", 10**500, "day"), None),
    (_shelf("9999-12-31", 1, "year"), None),
])
def test_printed_expiration_preserves_computable_unclear_dates_as_suggestions(printed, suggestion):
    assert printed_expiration(printed, TODAY) == (suggestion, [UNCLEAR])


@pytest.fixture
def photo_ai(fake_ai, monkeypatch):
    monkeypatch.setenv("AI_VISION_ENABLED", "true")
    ai_client.reload_config()
    monkeypatch.setattr(intake_services.localization, "today", lambda db: TODAY)
    return fake_ai


def _draft(**fields):
    return {
        "temporary_id": DRAFT_ID, "name": "Milk", "confidence": 0.9,
        "source": {"input_kind": "receipt"}, **fields,
    }


def _source(kind="product_closeup", index=0):
    return {"input_kind": kind, "image_index": index}


def _add(name="Milk", kind="product_closeup", **candidate):
    return {"op": "add", "source": _source(kind), "candidate": {"name": name, **candidate}}


def _update(kind="product_closeup", **changes):
    return {"op": "update", "source": _source(kind), "temporary_id": DRAFT_ID, "changes": changes}


def _photo_parse(client, photo_ai, *operations, draft=(), image_count=1):
    photo_ai.reply = json.dumps({"operations": operations})
    response = client.post(PARSE, files=[
        ("payload", (None, json.dumps({"draft": {"items": draft}, "context": {"locale": "en"}}))),
        *(("images", (f"image-{index}.jpg", b"\xff\xd8\xffmock image", "image/jpeg")) for index in range(image_count)),
    ])
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("kind", ["best_before", "use_by"])
def test_closeup_add_uses_readable_label_and_ignores_model_computed_date(client, db_session, photo_ai, kind):
    dairy = get_category_by_slug(db_session, "dairy")
    result = _photo_parse(client, photo_ai, _add(
        category_id=dairy.id, printed=_label("2026-12-12", kind),
        unopened_expiration_date="2026-12-01", expiration_source="stated",
    ))
    candidate = result["operations"][0]["candidate"]
    assert candidate["unopened_expiration_date"] == "2026-12-12"
    assert candidate["expiration_source"] == "printed"
    assert candidate["suggested_unopened_expiration_date"] is None
    assert "printed" not in candidate and candidate["warnings"] == []


def test_closeup_updates_existing_receipt_draft_with_calculated_expiry(client, photo_ai):
    result = _photo_parse(
        client, photo_ai, _update(printed=_shelf("2027-01-31", 1, "month")),
        draft=[_draft(suggested_unopened_expiration_date="2026-11-27", expiration_source="estimated")],
    )
    assert len(result["operations"]) == 1
    operation = result["operations"][0]
    assert operation["op"] == "update" and operation["temporary_id"] == DRAFT_ID
    assert operation["source"]["image_index"] == 0
    assert operation["changes"] == {
        "unopened_expiration_date": "2027-02-28", "expiration_source": "printed",
        "suggested_unopened_expiration_date": None,
    }
    prompt = photo_ai.system_prompts[0]
    assert "Use update with the existing temporary_id if the close-up" in prompt
    assert "already added from a receipt" in prompt
    assert "Do not compute or return the final unopened_expiration_date" in prompt
    assert "If the package shows only a year and month, use readable=false" in prompt
    assert DRAFT_ID in photo_ai.requests[0]["messages"][1]["content"][0]["text"]


def test_closeup_valid_printed_date_can_update_a_previously_reviewed_date(client, photo_ai):
    op = _update()
    op["printed"] = _label("2026-12-12")
    result = _photo_parse(
        client, photo_ai, op,
        draft=[_draft(unopened_expiration_date="2026-12-01", expiration_source="stated")],
    )
    assert result["operations"][0]["changes"] == {
        "unopened_expiration_date": "2026-12-12", "expiration_source": "printed",
    }


def test_closeup_date_before_purchase_is_kept_and_warned(client, photo_ai):
    result = _photo_parse(client, photo_ai, _add(printed=_label("2026-11-19")))
    candidate = result["operations"][0]["candidate"]
    assert candidate["unopened_expiration_date"] == "2026-11-19"
    assert candidate["expiration_source"] == "printed"
    assert candidate["warnings"] == [{"code": "expiration_before_purchase", "params": {}}]


def test_closeup_date_flows_from_draft_update_into_confirmed_stock(client, db_session, photo_ai):
    dairy = get_category_by_slug(db_session, "dairy")
    draft = _draft(category_id=dairy.id, quantity_value=1, quantity_unit="bottle")
    result = _photo_parse(
        client, photo_ai, _update(printed=_shelf("2027-01-31", 1, "month")), draft=[draft],
    )
    result = client.post("/api/intake/confirm", json={
        "defaults": {"owner": "me", "location": "Fridge"},
        "items": [{**draft, **result["operations"][0]["changes"]}],
    })
    assert result.status_code == 201, result.text
    item_id = result.json()["created"][0]["item_id"]
    stock = client.get(f"/api/items/{item_id}").json()
    assert stock["unopened_expiration_date"] == stock["current_expiration_date"] == "2027-02-28"


@pytest.mark.parametrize("printed", [
    _label("2026-11-28", readable=False), _label("2031-11-21", "use_by"),
])
def test_unclear_closeup_add_keeps_calculated_suggestion_over_category_default(client, db_session, photo_ai, printed):
    dairy = get_category_by_slug(db_session, "dairy")
    result = _photo_parse(client, photo_ai, _add(category_id=dairy.id, printed=printed))
    candidate = result["operations"][0]["candidate"]
    assert candidate["unopened_expiration_date"] is None
    assert candidate["suggested_unopened_expiration_date"] == printed["date"]
    assert candidate["expiration_source"] == "estimated"
    assert candidate["warnings"] == [UNCLEAR]


def test_unclear_closeup_update_keeps_trusted_draft_date(client, photo_ai):
    draft = _draft(unopened_expiration_date="2026-12-01", expiration_source="stated")
    result = _photo_parse(
        client, photo_ai, _update(printed=_label("2026-12-10", readable=False)), draft=[draft],
    )
    assert result["operations"][0]["changes"] == {"suggested_unopened_expiration_date": "2026-12-10"}
    assert result["warnings"] == [UNCLEAR]


def test_unclear_closeup_update_without_prior_date_is_only_a_suggestion(client, photo_ai):
    result = _photo_parse(
        client, photo_ai, _update(printed=_shelf("2027-01-31", 1, "month", readable=False)),
        draft=[_draft()],
    )
    assert result["operations"][0]["changes"] == {
        "suggested_unopened_expiration_date": "2027-02-28", "expiration_source": "estimated",
    }
    assert result["warnings"] == [UNCLEAR]


def test_invalid_printed_update_warns_without_clearing_existing_expiry(client, photo_ai):
    result = _photo_parse(
        client, photo_ai, _update(
            printed=_label("2027-02-29"), unopened_expiration_date="2026-12-01", expiration_source="stated",
        ), draft=[_draft(unopened_expiration_date="2026-11-30", expiration_source="stated")],
    )
    assert result["operations"] == []
    assert UNCLEAR in result["warnings"]
    assert {"code": "ops_dropped", "params": {"count": "1"}} in result["warnings"]


def test_invalid_printed_evidence_does_not_store_any_expiration(client, photo_ai):
    result = _photo_parse(client, photo_ai, _add(
        printed=_label("2026-02-30"), unopened_expiration_date="2026-12-01",
    ))
    candidate = result["operations"][0]["candidate"]
    assert candidate["unopened_expiration_date"] is None
    assert candidate["suggested_unopened_expiration_date"] is None
    assert candidate["expiration_source"] == "none"
    assert candidate["warnings"] == [UNCLEAR]


@pytest.mark.parametrize("operation_level", [False, True])
def test_same_batch_receipt_add_uses_dates_from_matching_closeup(client, photo_ai, operation_level):
    receipt = _add(
        kind="receipt", raw_name="MILK", specificity="specific_product",
        printed=_shelf("2027-01-31", 1, "month", image_index=1),
    )
    if operation_level:
        receipt["printed"] = receipt["candidate"].pop("printed")
    result = _photo_parse(client, photo_ai, receipt, image_count=2)

    assert len(result["operations"]) == 1
    operation = result["operations"][0]
    assert operation["op"] == "add" and operation["source"]["image_index"] == 0
    candidate = operation["candidate"]
    assert candidate["unopened_expiration_date"] == "2027-02-28"
    assert candidate["expiration_source"] == "printed"
    assert candidate["suggested_unopened_expiration_date"] is None
    assert candidate["source"]["input_kind"] == "receipt" and candidate["raw_name"] == "MILK"
    assert candidate["warnings"] == []
    prompt = photo_ai.system_prompts[0]
    assert "If a close-up matches a new receipt row in the same batch, use the receipt's single add." in prompt
    assert "set printed.image_index to the close-up's" in prompt
    assert "Do not emit a separate add or update for that close-up." in prompt


@pytest.mark.parametrize("index", [0, 2, -1, True, "1", None])
def test_receipt_add_drops_invalid_printed_image_reference(client, photo_ai, index):
    label = _label("2026-12-12")
    if index is not None:
        label["image_index"] = index
    result = _photo_parse(client, photo_ai, _add(
        kind="receipt", printed=label, unopened_expiration_date="2026-12-12", expiration_source="printed",
    ), image_count=2)
    candidate = result["operations"][0]["candidate"]
    assert candidate["unopened_expiration_date"] is None
    assert candidate["suggested_unopened_expiration_date"] is None
    assert candidate["expiration_source"] == "none"
    assert candidate["warnings"] == [EVIDENCE_DROPPED]


def test_unrecognized_printed_kind_cannot_use_valid_shelf_life_to_create_a_date(client, photo_ai):
    label = _label("2026-12-12", "production_date", shelf_life={"value": 5, "unit": "day"})
    result = _photo_parse(client, photo_ai, _add(printed=label))
    candidate = result["operations"][0]["candidate"]
    assert candidate["unopened_expiration_date"] is None
    assert candidate["suggested_unopened_expiration_date"] is None
    assert candidate["expiration_source"] == "none"
    assert candidate["warnings"] == [UNCLEAR]


def test_text_parse_cannot_promote_structured_or_raw_printed_dates(client, fake_ai, monkeypatch):
    monkeypatch.setattr(intake_services.localization, "today", lambda db: TODAY)
    operations = [
        _add(printed=_label("2026-12-12"), source=_source(), unopened_expiration_date="2026-12-01",
             expiration_source="printed"),
        _update(printed=_label("2026-12-12")),
    ]
    fake_ai.reply = json.dumps({"operations": operations})
    response = client.post(PARSE, json={
        "input": {"type": "text", "text": "Milk"},
        "context": {"locale": "en"},
        "draft": {"items": [_draft()]},
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["operations"]) == 1
    candidate = result["operations"][0]["candidate"]
    assert candidate["source"]["input_kind"] == "text"
    assert candidate["unopened_expiration_date"] is None
    assert candidate["suggested_unopened_expiration_date"] == "2026-12-01"
    assert candidate["expiration_source"] == "estimated"
    assert EVIDENCE_DROPPED in candidate["warnings"]
    assert EVIDENCE_DROPPED in result["warnings"]


def test_overview_cannot_supply_structured_printed_date(client, photo_ai):
    result = _photo_parse(client, photo_ai, _add(
        kind="product_overview", printed=_label("2026-12-12", image_index=1),
    ), image_count=2)
    candidate = result["operations"][0]["candidate"]
    assert candidate["unopened_expiration_date"] is None
    assert candidate["expiration_source"] == "none"
    assert EVIDENCE_DROPPED in candidate["warnings"]


def test_receipt_update_cannot_supply_cross_image_printed_evidence(client, photo_ai):
    result = _photo_parse(
        client, photo_ai, _update(kind="receipt", printed=_label("2026-12-12", image_index=1)),
        image_count=2, draft=[_draft()],
    )
    assert result["operations"] == []
    assert EVIDENCE_DROPPED in result["warnings"]


def test_overview_keeps_distinct_adds_and_caps_inferred_quantities(client, photo_ai):
    items = [
        ("Milk", {"quantity_value": 2, "field_confidence": {"quantity_value": 0.9},
                  "inferred_fields": ["quantity_value"]}, 0.5, True),
        ("Apples", {"quantity_value": 3, "field_confidence": {"quantity_value": 0.9},
                    "quantity_value_inferred": True}, 0.5, True),
        ("Eggs", {"quantity_value": 6, "field_confidence": {"quantity_value": 0.4}}, 0.4, True),
        ("Water", {"field_confidence": {"quantity_value": 0.9}}, 0.5, True),
        ("Rice", {"quantity_value": 2}, 0.5, True),
        ("Yogurt", {"quantity_value": 4, "field_confidence": {"quantity_value": 0.9}}, 0.9, False),
    ]
    result = _photo_parse(
        client, photo_ai, *[_add(name, kind="product_overview", **fields) for name, fields, _, _ in items],
    )
    candidates = [operation["candidate"] for operation in result["operations"]]
    assert len({candidate["temporary_id"] for candidate in candidates}) == len(items)
    assert [candidate["name"] for candidate in candidates] == [item[0] for item in items]
    for candidate, (_, _, score, inferred) in zip(candidates, items):
        assert candidate["field_confidence"]["quantity_value"] == score
        assert (QUANTITY_INFERRED in candidate["warnings"]) is inferred
    assert "one add per recognizable item" in photo_ai.system_prompts[0]

"""User-entered opening dates on parse requests (#100)."""

import json

import pytest


OPENED_DATES = {"opened_date": "2026-11-23", "opened_expiration_date": "2026-11-26"}


def _parse(client, **overrides):
    candidate = {
        "temporary_id": "cand_00000001", "name": "Milk", "confidence": 1,
        "source": {"input_kind": "text"}, **OPENED_DATES, **overrides,
    }
    return client.post("/api/intake/parse", json={
        "input": {"type": "text", "text": "Update my draft"},
        "draft": {"items": [candidate]}, "context": {"locale": "en"},
    })


def test_parse_accepts_user_opening_dates_without_a_draft_response(client, fake_ai):
    fake_ai.reply = json.dumps({"operations": []})

    response = _parse(client)

    assert response.status_code == 200, response.text
    assert set(response.json()) == {"operations", "unparsed_fragments", "locale", "warnings"}
    assert len(fake_ai.requests) == 1
    prompt = json.loads(fake_ai.requests[0]["messages"][-1]["content"])
    assert OPENED_DATES.keys().isdisjoint(prompt["draft"][0])


@pytest.mark.parametrize(("field", "value"), [
    ("opened_date", "infinite"),
    ("opened_date", "2026-02-30"),
    ("opened_expiration_date", "2026-02-30"),
])
def test_parse_rejects_invalid_user_opening_dates(client, fake_ai, field, value):
    response = _parse(client, **{field: value})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["detail"][0]["loc"] == ["body", "draft", "items", 0, field]
    assert fake_ai.requests == []


def test_ai_opening_dates_are_dropped_from_both_add_and_update(client, fake_ai):
    fake_ai.reply = json.dumps({"operations": [
        {"op": "update", "temporary_id": "cand_00000001", "changes": {
            "notes": "Keep chilled", **OPENED_DATES,
        }},
        {"op": "add", "candidate": {"name": "Cheese", "confidence": 1, **OPENED_DATES}},
    ]})

    response = _parse(client)

    assert response.status_code == 200, response.text
    body = response.json()
    update, add = body["operations"]
    assert update["changes"] == {"notes": "Keep chilled"}
    assert OPENED_DATES.keys().isdisjoint(add["candidate"])
    dropped = {
        (entry["params"]["index"], entry["params"]["field"])
        for entry in body["warnings"] if entry["code"] == "op_field_dropped"
    }
    assert dropped == {("0", field) for field in OPENED_DATES} | {
        ("1", field) for field in OPENED_DATES
    }

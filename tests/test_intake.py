"""Text intake API tests using the isolated database and mocked AI."""

import asyncio
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from stock_manager.api import ai_client, intake_services
from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.errors import APIError
from stock_manager.api.models import Category, Item, RestockItem
from tests.helpers import make_restock_create_payload

PARSE = "/api/intake/parse"
CONFIRM = "/api/intake/confirm"


def _id(number):
    return f"cand_{number:08x}"


def _category(db_session, slug="dairy"):
    return get_category_by_slug(db_session, slug).id


def _restock(client, **fields):
    response = client.post("/api/restock", json=make_restock_create_payload(**fields))
    assert response.status_code == 201
    return response.json()["id"]


def _confirmed(db_session, number=1, **fields):
    return {
        "temporary_id": _id(number),
        "name": "牛奶",
        "category_id": _category(db_session),
        "quantity_value": 2,
        "quantity_unit": "瓶",
        "unopened_expiration_date": "infinite",
        **fields,
    }


def _confirm(client, *items, **overrides):
    return client.post(CONFIRM, json={
        "items": items, "defaults": {"owner": "me", "location": "冰箱"}, **overrides,
    })


class TestConfirm:
    def test_batch_defaults_overrides_and_derived_fields(self, client, db_session, monkeypatch):
        assert client.patch("/api/settings", json={"default_timezone": "Pacific/Kiritimati"}).status_code == 200
        commit = db_session.commit
        commits = []

        def count_commit():
            commits.append(True)
            commit()

        monkeypatch.setattr(db_session, "commit", count_commit)
        first = _confirmed(
            db_session, owner=None, location=None,
            purchase_date="2026-01-01", opened_date="2026-01-03",
            opened_expiration_date="2026-01-04", current_expiration_date="infinite",
            status="consumed",
        )
        second = _confirmed(db_session, 2, name="酸奶", owner="Alice", location="冷冻室")
        response = _confirm(client, first, second)
        assert response.status_code == 201, response.text
        created = response.json()["created"]
        assert [row["temporary_id"] for row in created] == [_id(1), _id(2)]
        stock = [db_session.get(Item, row["item_id"]) for row in created]
        assert (stock[0].owner, stock[0].location, stock[0].purchase_date) == ("me", "冰箱", "2026-01-01")
        assert (stock[0].current_expiration_date, stock[0].status) == ("2026-01-04", "expired")
        assert (stock[1].owner, stock[1].location) == ("Alice", "冷冻室")
        assert stock[1].purchase_date == datetime.now(ZoneInfo("Pacific/Kiritimati")).date().isoformat()
        assert commits == [True]

    @pytest.mark.parametrize(("field", "value"), [
        ("category_id", 999999),
        ("category_id", 2**63),
        ("matched_restock_id", 999999),
        ("matched_restock_id", 2**63),
        ("unopened_expiration_date", None),
        ("purchase_date", "2026-02-30"),
        ("quantity_value", 0),
        ("owner", "  "),
        ("location", ""),
    ])
    def test_invalid_item_in_batch_leaves_stock_and_restock_unchanged(self, client, db_session, field, value):
        restock_id = _restock(client)
        first = _confirmed(db_session, matched_restock_id=restock_id, restock_action="done")
        second = _confirmed(db_session, 2, **{field: value})
        response = _confirm(client, first, second)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "intake_item_invalid"
        assert response.json()["params"] == {"index": 1, "temporary_id": _id(2), "field": field}
        assert db_session.query(Item).count() == 0
        restock = db_session.get(RestockItem, restock_id)
        assert (restock.status, restock.quantity_value) == ("pending", 12)

    def test_requires_defaults_or_item_values_and_unique_ids(self, client, db_session):
        item = _confirmed(db_session)
        response = _confirm(client, item, defaults={})
        assert response.status_code == 422
        assert response.json()["params"]["field"] == "owner"

        response = _confirm(client, item, item)
        assert response.status_code == 422
        assert response.json()["code"] == "intake_duplicate_temporary_id"
        assert response.json()["params"] == {"id": _id(1)}
        assert db_session.query(Item).count() == 0

    @pytest.mark.parametrize("size", [0, 101])
    def test_confirm_batch_size(self, client, db_session, size):
        response = _confirm(client, *[_confirmed(db_session, i) for i in range(size)])
        assert response.status_code == 422
        assert db_session.query(Item).count() == 0

    def test_restock_done_partial_none_and_omitted(self, client, db_session):
        actions = ("done", "partial", "none", None)
        ids = [_restock(client, name=f"Item {i}") for i in range(len(actions))]
        response = _confirm(client, *[
            _confirmed(db_session, i, matched_restock_id=restock_id, restock_action=action)
            for i, (restock_id, action) in enumerate(zip(ids, actions))
        ])
        assert response.status_code == 201, response.text
        assert response.json()["restock_done"] == [ids[0]]
        assert response.json()["restock_partial"] == [ids[1]]
        assert response.json()["warnings"] == []
        restock = [db_session.get(RestockItem, key) for key in ids]
        assert [row.status for row in restock] == ["done", "pending", "pending", "pending"]
        assert [row.quantity_value for row in restock[1:]] == [10, 12, 12]
        assert [row.quantity_value for row in db_session.query(Item).order_by(Item.id).all()] == [2] * 4

    @pytest.mark.parametrize("action", ["done", "partial"])
    def test_duplicate_restock_only_applies_once(self, client, db_session, action):
        restock_id = _restock(client)
        response = _confirm(client, *[
            _confirmed(db_session, i, matched_restock_id=restock_id, restock_action=action)
            for i in (1, 2)
        ])
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["warnings"] == [{"code": "restock_already_done", "params": {"restock_id": str(restock_id)}}]
        assert body["restock_done"] == ([restock_id] if action == "done" else [])
        assert body["restock_partial"] == ([restock_id] if action == "partial" else [])
        assert db_session.query(Item).count() == 2
        if action == "partial":
            assert db_session.get(RestockItem, restock_id).quantity_value == 10

    @pytest.mark.parametrize("concurrent", [False, True])
    def test_restock_already_done_or_changed_still_creates_stock(self, client, db_session, monkeypatch, concurrent):
        restock_id = _restock(client)
        if concurrent:
            def conflict(db, restock, quantity, data):
                raise intake_services.RestockAlreadyDoneError(restock.id)

            monkeypatch.setattr(intake_services, "apply_restock_purchase", conflict)
        else:
            restock = db_session.get(RestockItem, restock_id)
            restock.status = "done"
            db_session.commit()

        response = _confirm(client, _confirmed(db_session, matched_restock_id=restock_id, restock_action="done"))
        assert response.status_code == 201, response.text
        assert response.json()["restock_done"] == []
        assert response.json()["warnings"] == [{"code": "restock_already_done", "params": {"restock_id": str(restock_id)}}]
        assert db_session.query(Item).count() == 1

    def test_hook_has_flushed_rows_and_failure_rolls_back(self, client, db_session, monkeypatch):
        restock_id = _restock(client)
        commits = []
        commit = db_session.commit

        def track_commit():
            commits.append(True)
            commit()

        def fail_hook(db, created):
            assert commits == []
            assert [draft.temporary_id for draft, stock in created] == [_id(1), _id(2)]
            assert all(stock.id is not None for draft, stock in created)
            assert db.query(Item).count() == 2
            assert db.get(RestockItem, restock_id).status == "done"
            raise RuntimeError("hook failed")

        monkeypatch.setattr(db_session, "commit", track_commit)
        monkeypatch.setattr(intake_services, "after_confirm", fail_hook)
        with pytest.raises(RuntimeError, match="hook failed"):
            _confirm(
                client,
                _confirmed(db_session, matched_restock_id=restock_id, restock_action="done"),
                _confirmed(db_session, 2),
            )
        assert commits == []
        assert db_session.query(Item).count() == 0
        assert db_session.get(RestockItem, restock_id).status == "pending"


class TestPrepareParse:
    @staticmethod
    def _request(**overrides):
        from stock_manager.api.intake_schemas import ParseRequest

        return ParseRequest.model_validate({
            "input": {"type": "text", "text": "  Two bottles of milk.  "},
            "draft": {"items": []},
            **overrides,
        })

    @pytest.mark.parametrize(("locale", "header", "setting", "expected", "fallback"), [
        ("en-AU", "ja", "zh-CN", "en", False),
        (None, "en", "ja", "ja", False),
        (None, "ja-JP", None, "ja", False),
        ("fr", "en", None, "en", True),
    ])
    def test_uses_shared_locale_resolution(self, client, db_session, locale, header, setting, expected, fallback):
        if setting is not None:
            assert client.patch("/api/settings", json={"default_locale": setting}).status_code == 200
        request = self._request(context={"locale": locale})
        prepared = intake_services.prepare_parse(db_session, request, header)
        assert prepared.locale == expected
        assert bool(prepared.warnings) is fallback

    @pytest.mark.parametrize("timezone", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])
    def test_prompt_calendar_follows_request_timezone(self, client, db_session, timezone):
        opposite = "Pacific/Pago_Pago" if timezone == "Pacific/Kiritimati" else "Pacific/Kiritimati"
        assert client.patch("/api/settings", json={"default_timezone": opposite}).status_code == 200
        request = self._request(context={"locale": "en", "timezone": timezone, "purchase_date": "2026-11-01"})
        prepared = intake_services.prepare_parse(db_session, request, None)
        system, user = intake_services._build_text_prompt(request, prepared)
        prompt = json.loads(user)
        today = datetime.now(ZoneInfo(timezone)).date()
        assert "json" in system
        assert "English" in system
        assert prompt["input"] == "Two bottles of milk."
        assert prompt["today"] == today.isoformat()
        assert prompt["purchase_date"] == "2026-11-01"
        assert prompt["weekday"] == today.strftime("%A")
        assert prompt["calendar"] == [
            {"date": day.isoformat(), "weekday": day.strftime("%A")}
            for day in (today + timedelta(days=offset) for offset in range(21))
        ]
        assert all("default_shelf_life_days" not in category for category in prompt["categories"])

    def test_uses_household_timezone_when_request_omits_it(self, client, db_session):
        timezone = "Pacific/Kiritimati"
        assert client.patch("/api/settings", json={"default_timezone": timezone}).status_code == 200
        prepared = intake_services.prepare_parse(db_session, self._request(), None)
        assert prepared.today == prepared.purchase_date == datetime.now(ZoneInfo(timezone)).date()

    @pytest.mark.parametrize(("overrides", "code", "params"), [
        ({"input": {"type": "text", "text": " \n "}}, "intake_text_empty", {}),
        ({"input": {"type": "text", "text": "x" * 4001}}, "intake_text_too_long", {"max": 4000}),
        ({"context": {"timezone": "moon/base"}}, "intake_timezone_invalid", {}),
    ])
    def test_rejects_invalid_input_before_reference_queries(
        self, db_session, fake_ai, monkeypatch, overrides, code, params
    ):
        def unexpected_query(*args):
            pytest.fail("invalid intake request read the database")

        monkeypatch.setattr(db_session, "query", unexpected_query)
        with pytest.raises(APIError) as raised:
            intake_services.prepare_parse(db_session, self._request(**overrides), None)
        assert raised.value.status_code == 422
        assert raised.value.code == code
        assert raised.value.params == params
        assert fake_ai.requests == []

    def test_rejects_large_and_duplicate_drafts(self, db_session, fake_ai):
        candidate = {"temporary_id": _id(0), "confidence": 1, "source": {"input_kind": "text"}}
        large = [{**candidate, "temporary_id": _id(i)} for i in range(101)]
        for items, code, params in [
            (large, "intake_draft_too_large", {"max": 100}),
            ([candidate, candidate], "intake_duplicate_temporary_id", {"id": _id(0)}),
        ]:
            with pytest.raises(APIError) as raised:
                intake_services.prepare_parse(db_session, self._request(draft={"items": items}), None)
            assert raised.value.code == code
            assert raised.value.params == params
        assert fake_ai.requests == []

    def test_reference_snapshot_and_prompt_limits(self, db_session, monkeypatch):
        db_session.add(RestockItem(name="Done", status="done"))
        db_session.add_all([RestockItem(name=f"Pending {i}", status="pending") for i in range(101)])
        db_session.commit()
        tracked = (Item, RestockItem, Category)
        before = [db_session.query(model).count() for model in tracked]

        def unexpected_commit():
            pytest.fail("parse must not commit")

        monkeypatch.setattr(db_session, "commit", unexpected_commit)
        request = self._request(draft={"items": [{
            "temporary_id": _id(1), "name": "牛奶", "owner": "me", "notes": "private",
            "confidence": 1, "source": {"input_kind": "text", "span": "original"},
        }]})
        prepared = intake_services.prepare_parse(db_session, request, None)
        _, user = intake_services._build_text_prompt(request, prepared)
        prompt = json.loads(user)

        assert len(prompt["pending_restock"]) == 100
        assert all(item["name"].startswith("Pending ") for item in prompt["pending_restock"])
        assert next(c for c in prompt["categories"] if c["name"] == "乳制品")["parent"] == "食品"
        assert set(prompt["draft"][0]) == {
            "temporary_id", "name", "quantity_value", "quantity_unit", "category_id",
            "unopened_expiration_date", "expiration_source",
        }
        assert [db_session.query(model).count() for model in tracked] == before

    @pytest.mark.parametrize("reply", [None, ["bad"], {"operations": {}}, {}])
    def test_rejects_replies_without_operations(self, db_session, fake_ai, reply):
        request = self._request()
        prepared = intake_services.prepare_parse(db_session, request, None)
        fake_ai.reply = json.dumps(reply)
        with pytest.raises(ai_client.AIUpstreamError) as raised:
            asyncio.run(intake_services.request_parse_reply(request, prepared))
        assert raised.value.reason == "not_json"
        assert len(fake_ai.requests) == 1

    def test_requests_json_once(self, db_session, fake_ai):
        request = self._request()
        prepared = intake_services.prepare_parse(db_session, request, None)
        expected = {"operations": [], "unparsed_fragments": ["milk"]}
        fake_ai.reply = json.dumps(expected)
        assert asyncio.run(intake_services.request_parse_reply(request, prepared)) == expected
        assert len(fake_ai.requests) == 1
        assert fake_ai.requests[0]["response_format"] == {"type": "json_object"}


def _candidate(number=1, **fields):
    return {
        "temporary_id": _id(number),
        "name": "Milk",
        "confidence": 0.9,
        "source": {"input_kind": "text"},
        **fields,
    }


def _add(**fields):
    return {"op": "add", "candidate": {"name": "Milk", **fields}}


def _update(number=1, **changes):
    return {"op": "update", "temporary_id": _id(number), "changes": changes}


def _parse_body(*items, text="Two bottles of milk", context=None):
    return {
        "input": {"type": "text", "text": text},
        "draft": {"items": items},
        "context": {"locale": "en"} if context is None else context,
    }


def _parse(client, fake_ai, operations, *items, **kwargs):
    fake_ai.reply = json.dumps({"operations": operations, "unparsed_fragments": ["remaining text"]})
    response = client.post(PARSE, json=_parse_body(*items, **kwargs))
    assert response.status_code == 200, response.text
    return response.json()


def _warning(code, **params):
    return {"code": code, "params": params}


class TestParse:
    @pytest.fixture(autouse=True)
    def fixed_today(self, monkeypatch):
        monkeypatch.setattr(intake_services.localization, "today", lambda db: date(2026, 11, 20))

    def test_all_operations_apply_without_db_writes(self, client, db_session, fake_ai, monkeypatch):
        dairy = _category(db_session)
        restock_id = _restock(client, name="Eggs", quantity_value=6, quantity_unit="pcs")
        tracked = (Item, RestockItem, Category)
        before = [db_session.query(model).count() for model in tracked]
        def unexpected_commit():
            pytest.fail("parse must not commit")

        prepare = intake_services.prepare_parse

        def prepare_in_worker(*args):
            with pytest.raises(RuntimeError, match="no running event loop"):
                asyncio.get_running_loop()
            return prepare(*args)

        monkeypatch.setattr(db_session, "commit", unexpected_commit)
        monkeypatch.setattr("stock_manager.api.routers.intake.prepare_parse", prepare_in_worker)
        result = _parse(client, fake_ai, [
            _add(name="Eggs", quantity_unit="个", quantity_value=6, matched_restock_id=restock_id),
            _update(1, quantity_value=2),
            {"op": "delete", "temporary_id": _id(2), "reason_code": "duplicate"},
            {
                "op": "clarify", "temporary_ids": [_id(1), _id(3)], "question_code": "ambiguous_target",
                "question": "Which milk did you mean?",
            },
        ], _candidate(category_id=dairy), _candidate(2), _candidate(3))
        assert [row["op"] for row in result["operations"]] == ["add", "update", "delete", "clarify"]
        assert result["operations"][0]["candidate"]["restock_action"] == "done"
        assert result["operations"][1]["changes"] == {"quantity_value": 2.0}
        assert result["operations"][2]["reason_code"] == "duplicate"
        assert result["operations"][3]["temporary_ids"] == [_id(1), _id(3)]
        assert result["unparsed_fragments"] == ["remaining text"]
        assert result["locale"] == "en"
        assert result["warnings"] == []
        assert [db_session.query(model).count() for model in tracked] == before

    @pytest.mark.parametrize(("payload", "code", "params"), [
        (_parse_body(text="  "), "intake_text_empty", {}),
        (_parse_body(text="x" * 4001), "intake_text_too_long", {"max": 4000}),
        (_parse_body(*[_candidate(i) for i in range(101)]), "intake_draft_too_large", {"max": 100}),
        (_parse_body(_candidate(), _candidate()), "intake_duplicate_temporary_id", {"id": _id(1)}),
        (_parse_body(context={"timezone": "Moon/Base"}), "intake_timezone_invalid", {}),
    ])
    def test_request_limits_are_stable_errors_before_ai(self, client, fake_ai, payload, code, params):
        response = client.post(PARSE, json=payload)
        assert response.status_code == 422
        assert response.json()["code"] == code
        assert response.json()["params"] == params
        assert fake_ai.requests == []

    def test_disabled_ai(self, client):
        response = client.post(PARSE, json=_parse_body())
        assert response.status_code == 503
        assert response.json()["code"] == "ai_unavailable"
        assert {"params", "detail"} <= response.json().keys()

    def test_bad_ai_reply(self, client, fake_ai):
        fake_ai.reply = '{"unparsed_fragments": []}'
        response = client.post(PARSE, json=_parse_body())
        assert response.status_code == 502
        assert response.json()["code"] == "ai_upstream_error"
        assert {"params", "detail"} <= response.json().keys()

    def test_dropped_ops_and_fields_have_warnings(self, client, fake_ai):
        result = _parse(client, fake_ai, [
            _update(2, notes="drop conflicting update"),
            {"op": "delete", "temporary_id": _id(2), "reason_code": "user_requested"},
            _update(1, restock_action="done"),
            _update(99, name="Unknown"),
            _add(name="  "),
            {
                "op": "clarify", "temporary_ids": [_id(1)], "question_code": "ambiguous_quantity",
                "question": "何本ですか？",
            },
            _update(1, unopened_expiration_date="2099-05-01"),
        ], _candidate(), _candidate(2))
        assert result["operations"] == [
            {"op": "delete", "temporary_id": _id(2), "reason_code": "user_requested"},
        ]
        for code, params in [
            ("op_conflict", {"index": "0"}),
            ("op_field_dropped", {"index": "2", "field": "restock_action"}),
            ("op_invalid", {"index": "2"}),
            ("op_target_unknown", {"index": "3"}),
            ("op_invalid", {"index": "4"}),
            ("op_invalid", {"index": "5"}),
            ("date_dropped", {"field": "unopened_expiration_date"}),
            ("op_invalid", {"index": "6"}),
            ("ops_dropped", {"count": "6"}),
        ]:
            assert _warning(code, **params) in result["warnings"]

    def test_invalid_update_values_discard_the_entire_operation(self, client, db_session, fake_ai):
        result = _parse(client, fake_ai, [
            _update(1, quantity_value="abc", category_id=999999, name="  "),
        ], _candidate(name="Milk", quantity_value=2, category_id=_category(db_session)))
        assert result["operations"] == []
        assert result["warnings"] == [
            _warning("quantity_dropped", field="quantity_value"),
            _warning("category_dropped", field="category_id"),
            _warning("field_value_dropped", field="name"),
            _warning("op_invalid", index="0"),
            _warning("ops_dropped", count="1"),
        ]

    def test_update_keeps_explicit_null_and_drops_only_the_invalid_value(self, client, db_session, fake_ai):
        result = _parse(client, fake_ai, [
            _update(1, quantity_value=None, category_id=999999, notes="Reviewed"),
        ], _candidate(quantity_value=2, category_id=_category(db_session)))
        assert result["operations"][0]["changes"] == {"quantity_value": None, "notes": "Reviewed"}
        assert result["warnings"] == [_warning("category_dropped", field="category_id")]

    def test_add_keeps_mixed_language_product_names(self, client, fake_ai):
        names = ["Oreo饼干", "Coca-Cola", "iPhone充电线"]
        result = _parse(
            client, fake_ai, [_add(name=name) for name in names],
            text="买了 Oreo饼干、Coca-Cola、iPhone充电线", context={"locale": "zh-CN"},
        )
        assert [op["candidate"]["name"] for op in result["operations"]] == names
        assert result["warnings"] == []

    def test_invalid_purchase_date_on_add_uses_context_default(self, client, fake_ai):
        result = _parse(
            client, fake_ai, [_add(purchase_date="2026-13-40")],
            context={"locale": "en", "purchase_date": "2026-11-18"},
        )
        candidate = result["operations"][0]["candidate"]
        assert candidate["purchase_date"] == "2026-11-18"
        assert candidate["warnings"] == [_warning("date_dropped", field="purchase_date")]

    @pytest.mark.parametrize(("changes", "loc"), [
        ({"temporary_id": "cand_1A2b3c4d"}, ["temporary_id"]),
        ({"temporary_id": "cand_1a2b3c4"}, ["temporary_id"]),
        ({"temporary_id": "app_1a2b3c4d"}, ["temporary_id"]),
        ({"source": {}}, ["source", "input_kind"]),
    ])
    def test_app_candidate_shape_is_validated(self, client, fake_ai, changes, loc):
        response = client.post(PARSE, json=_parse_body(_candidate(**changes)))
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "draft", "items", 0, *loc]
        assert fake_ai.requests == []

    def test_app_candidate_requires_confidence(self, client, fake_ai):
        candidate = _candidate()
        del candidate["confidence"]
        response = client.post(PARSE, json=_parse_body(candidate))
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "draft", "items", 0, "confidence"]
        assert fake_ai.requests == []

    @pytest.mark.parametrize("source", [None, "printed", "estimated", "none"])
    def test_category_default_replaces_untrusted_date_even_when_user_said_it(self, client, db_session, fake_ai, source):
        fields = {"category_id": _category(db_session), "unopened_expiration_date": "2026-12-01"}
        if source is not None:
            fields["expiration_source"] = source
        result = _parse(client, fake_ai, [_add(**fields)], text="The milk expires December 1.")
        candidate = result["operations"][0]["candidate"]
        assert candidate["unopened_expiration_date"] is None
        assert candidate["suggested_unopened_expiration_date"] == "2026-11-27"
        assert candidate["expiration_source"] == "estimated"
        assert candidate["warnings"] == [
            _warning("expiration_date_inferred", basis="category_default"),
            _warning("ai_expiration_ignored", date="2026-12-01"),
        ]

    def test_model_dates_only_move_when_category_has_no_default(self, client, db_session, fake_ai):
        result = _parse(client, fake_ai, [
            _add(category_id=_category(db_session, "other_food"), expiration_source="printed",
                 unopened_expiration_date="2026-11-21"),
            _add(category_id=_category(db_session), suggested_unopened_expiration_date="2026-11-29"),
            _add(unopened_expiration_date="infinite"),
            _add(category_id=_category(db_session), unopened_expiration_date="2026-02-30"),
        ])
        moved, suggested, indefinite, invalid = [op["candidate"] for op in result["operations"]]
        assert moved["unopened_expiration_date"] is None
        assert moved["suggested_unopened_expiration_date"] == "2026-11-21"
        assert moved["warnings"] == [_warning("expiration_moved_to_suggested")]
        assert moved["expiration_source"] == "estimated"
        assert suggested["suggested_unopened_expiration_date"] == "2026-11-27"
        assert _warning("ai_expiration_ignored", date="2026-11-29") in suggested["warnings"]
        assert indefinite["unopened_expiration_date"] is None
        assert indefinite["expiration_source"] == "none"
        assert indefinite["warnings"] == [_warning("date_dropped", field="unopened_expiration_date")]
        assert invalid["suggested_unopened_expiration_date"] == "2026-11-27"
        assert _warning("date_dropped", field="unopened_expiration_date") in invalid["warnings"]

    @pytest.mark.parametrize(("expiration", "before_purchase"), [
        ("2026-11-19", True), ("2026-12-01", False), ("infinite", False),
    ])
    def test_stated_date_survives_without_suggestion(self, client, db_session, fake_ai, expiration, before_purchase):
        result = _parse(client, fake_ai, [
            _add(category_id=_category(db_session), unopened_expiration_date=expiration,
                 expiration_source="stated"),
        ])
        candidate = result["operations"][0]["candidate"]
        assert candidate["unopened_expiration_date"] == expiration
        assert candidate["suggested_unopened_expiration_date"] is None
        assert candidate["expiration_source"] == "stated"
        assert candidate["warnings"] == ([_warning("expiration_before_purchase")] if before_purchase else [])

    def test_update_uses_merged_category_and_purchase_date(self, client, db_session, fake_ai):
        dairy = _category(db_session)
        other = _category(db_session, "other_food")
        result = _parse(client, fake_ai, [
            _update(1, unopened_expiration_date="2026-12-01"),
            _update(2, category_id=dairy, purchase_date="2026-11-25", unopened_expiration_date="2026-12-02"),
            _update(3, category_id=other, unopened_expiration_date="2026-12-03", expiration_source="printed"),
        ], _candidate(category_id=dairy, purchase_date="2026-11-21"),
            _candidate(2, category_id=other), _candidate(3, category_id=dairy))
        changes = [op["changes"] for op in result["operations"]]
        assert [row["suggested_unopened_expiration_date"] for row in changes] == [
            "2026-11-28", "2026-12-02", "2026-12-03",
        ]
        assert changes[0]["unopened_expiration_date"] is None
        assert changes[1]["category_id"] == dairy
        assert changes[2]["expiration_source"] == "estimated"
        assert _warning("ai_expiration_ignored", date="2026-12-01") in result["warnings"]
        assert _warning("ai_expiration_ignored", date="2026-12-02") in result["warnings"]
        assert _warning("expiration_moved_to_suggested") in result["warnings"]

    @pytest.mark.parametrize("source", ["printed", "stated"])
    def test_update_preserves_trusted_draft_date_until_explicitly_changed(self, client, db_session, fake_ai, source):
        dairy = _category(db_session)
        item = _candidate(unopened_expiration_date="2026-12-10", expiration_source=source)
        result = _parse(client, fake_ai, [
            _update(1, category_id=dairy),
            _update(1, unopened_expiration_date="2026-12-04"),
            _update(1, unopened_expiration_date="2026-12-20", expiration_source="stated"),
        ], item)
        first, second, third = [op["changes"] for op in result["operations"]]
        assert first == {"category_id": dairy}
        assert second == {"unopened_expiration_date": "2026-12-10"}
        assert third == {"unopened_expiration_date": "2026-12-20", "expiration_source": "stated"}
        assert result["warnings"] == [_warning("ai_expiration_ignored", date="2026-12-04")]

    def test_update_restock_action_from_merged_fields_and_ignores_model_action(self, client, db_session, fake_ai):
        restock_id = _restock(client, name="Eggs", quantity_value=6, quantity_unit="pcs")
        complete_id = _restock(client, name="Done")
        db_session.get(RestockItem, complete_id).status = "done"
        db_session.commit()
        result = _parse(client, fake_ai, [
            _update(1, matched_restock_id=restock_id, restock_action="done"),
            _update(1, quantity_value=6),
            _update(1, quantity_unit="kg"),
            _update(1, notes="Keep the user's choice", restock_action="done"),
            _update(1, matched_restock_id=None),
            _update(2, matched_restock_id=complete_id),
            _update(3, quantity_value=4),
        ], _candidate(quantity_value=3, quantity_unit="个", restock_action="none"),
            _candidate(2, matched_restock_id=restock_id),
            _candidate(3, matched_restock_id=complete_id))
        assert [op["changes"] for op in result["operations"]] == [
            {"matched_restock_id": restock_id, "restock_action": "partial"},
            {"quantity_value": 6.0, "restock_action": "done"},
            {"quantity_unit": "kg", "restock_action": "none"},
            {"notes": "Keep the user's choice"},
            {"matched_restock_id": None, "restock_action": None},
            {"quantity_value": 4.0, "matched_restock_id": None, "restock_action": None},
        ]
        assert _warning("op_field_dropped", index="0", field="restock_action") in result["warnings"]
        assert _warning("op_field_dropped", index="3", field="restock_action") in result["warnings"]
        assert _warning("restock_match_dropped", field="matched_restock_id") in result["warnings"]
        assert _warning("op_invalid", index="5") in result["warnings"]
        assert _warning("ops_dropped", count="1") in result["warnings"]

    def test_update_omits_restock_action_for_unlinked_quantity_change(self, client, fake_ai):
        result = _parse(client, fake_ai, [_update(1, quantity_value=3)], _candidate(quantity_value=2))
        assert result["operations"][0]["changes"] == {"quantity_value": 3.0}
        assert result["warnings"] == []

    def test_zero_valid_ops_and_locale_fallback_are_successful(self, client, fake_ai):
        result = _parse(client, fake_ai, [{"op": ["invalid"]}], context={"locale": "fr"})
        assert result["operations"] == []
        assert result["locale"] == "zh-CN"
        assert result["warnings"] == [
            _warning("locale_fallback", requested="fr"),
            _warning("op_invalid", index="0"),
            _warning("ops_dropped", count="1"),
        ]

    def test_parse_confirm_and_list(self, client, db_session, fake_ai):
        dairy = _category(db_session)
        result = _parse(client, fake_ai, [
            _add(
                category_id=dairy, quantity_value=2, quantity_unit="bottles",
                unopened_expiration_date="2026-11-29", expiration_source="stated",
            ),
        ])
        candidate = result["operations"][0]["candidate"]
        response = _confirm(client, candidate, defaults={"owner": "me", "location": "Fridge"})
        assert response.status_code == 201, response.text
        item_id = response.json()["created"][0]["item_id"]
        result = client.get("/api/items")
        assert result.status_code == 200
        stock = next(row for row in result.json() if row["id"] == item_id)
        assert (stock["name"], stock["quantity_value"], stock["category_id"]) == ("Milk", 2, dairy)
        assert stock["unopened_expiration_date"] == "2026-11-29"

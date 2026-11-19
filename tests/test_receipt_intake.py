"""Receipt parsing and confirmation with local alias history and mocked AI."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from stock_manager.api import ai_client, intake_services, receipt_lookup
from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.intake_schemas import ConfirmRequest
from stock_manager.api.models import Base, Category, Item, ReceiptAliasName, ReceiptItemAlias, RestockItem
from stock_manager.api.receipt_aliases import _upsert, normalize_raw_name, normalize_store
from tests.helpers import make_restock_create_payload

PARSE = "/api/intake/parse"
CONFIRM = "/api/intake/confirm"
RAW_NAME = "ORG MLK 2%"
STORE = "Trader Joe's"
DAIRY_NAME = "Organic Milk"


def _id(number=1):
    return f"cand_{number:08x}"


def _confirmed(db, number=1, **fields):
    return {
        "temporary_id": _id(number), "name": DAIRY_NAME,
        "category_id": get_category_by_slug(db, "dairy").id,
        "quantity_value": 1, "quantity_unit": "carton", "unopened_expiration_date": "infinite",
        "raw_name": RAW_NAME, "store_name": STORE, "specificity": "specific_receipt_label",
        **fields,
    }


def _confirm(client, *items):
    return client.post(CONFIRM, json={"defaults": {"owner": "me", "location": "Fridge"}, "items": items})


def _line(**fields):
    return {
        "name": "Milk", "source": {"input_kind": "receipt"}, "raw_name": RAW_NAME,
        "generic_name": "Milk", "store_name": STORE, "confidence": 0.8,
        "quantity_value": 1, "quantity_unit": "bottle", "price": 4.99,
        "specificity": "specific_receipt_label", **fields,
    }


def _parse(client, fake_ai, *lines, context=None, fragments=None):
    fake_ai.reply = json.dumps({
        "operations": [{"op": "add", "candidate": line} for line in lines],
        "unparsed_fragments": fragments or [],
    })
    response = client.post(PARSE, json={
        "input": {"type": "text", "text": "STORE\nORG MLK 2% 4.99\nTAX 0.95"},
        "draft": {"items": []}, "context": {"locale": "en", **(context or {})},
    })
    assert response.status_code == 200, response.text
    return response.json()


def _candidate(client, fake_ai, **fields):
    return _parse(client, fake_ai, _line(**fields))["operations"][0]["candidate"]


def test_receipt_normalization_keeps_product_size_and_strips_price_and_count():
    assert normalize_store(" Ｔｒａｄｅｒ Joe’s. ") == "traderjoes"
    assert normalize_store(None) == ""
    assert normalize_raw_name(" ＯＲＧ   ＭＬＫ ２％ ×2  ¥４．９９ ") == "org mlk 2%"
    assert normalize_raw_name("Chocolate 4,99") == "chocolate"
    assert normalize_raw_name("Coke 500 ml") == "coke 500 ml"
    assert normalize_raw_name("Flavor 42") == "flavor 42"


def test_first_seen_receipt_is_reviewed_and_lookup_only_gets_store_and_raw_label(
    client, db_session, fake_ai, monkeypatch,
):
    calls = []

    def lookup(raw_names, store):
        calls.append((raw_names, store))
        return {}

    monkeypatch.setattr(receipt_lookup, "lookup_products", lookup)

    def forbid_commit():
        pytest.fail("receipt parsing must never commit")

    model_counts = (Item, RestockItem, Category, ReceiptItemAlias, ReceiptAliasName)
    before = [db_session.query(model).count() for model in model_counts]
    monkeypatch.setattr(db_session, "commit", forbid_commit)
    receipt_date = (date.today() - timedelta(days=1)).isoformat()
    result = _parse(
        client, fake_ai, _line(purchase_date=receipt_date),
        fragments=["STORE", "TAX 0.95", "SUBTOTAL", "PAYMENT", "COUPON"],
    )

    candidate = result["operations"][0]["candidate"]
    assert candidate["source"]["input_kind"] == "receipt"
    assert candidate["raw_name"] == RAW_NAME and candidate["generic_name"] == "Milk"
    assert candidate["store_name"] == STORE and candidate["specificity"] == "specific_receipt_label"
    assert candidate["price"] == 4.99 and candidate["suggestions"] == []
    assert candidate["purchase_date"] == receipt_date
    assert {"code": "purchase_date_from_receipt", "params": {}} in candidate["warnings"]
    assert candidate["alias_mode"] == "suggest" and candidate["match_method"] == "ai_knowledge"
    assert candidate["requires_user_review"] is True and candidate["review_reason"] == "first_seen"
    assert candidate["auto_apply_allowed"] is False
    assert result["unparsed_fragments"] == ["STORE", "TAX 0.95", "SUBTOTAL", "PAYMENT", "COUPON"]
    assert calls == [([RAW_NAME], STORE)]
    assert [db_session.query(model).count() for model in model_counts] == before
    prompt = fake_ai.system_prompts[0]
    assert "source.input_kind=receipt" in prompt and "Do not merge separate lines" in prompt


def test_explicit_context_purchase_date_beats_receipt_date(client, fake_ai):
    receipt_date = (date.today() - timedelta(days=1)).isoformat()
    supplied = (date.today() - timedelta(days=2)).isoformat()
    result = _parse(
        client, fake_ai, _line(purchase_date=receipt_date), context={"purchase_date": supplied},
    )
    candidate = result["operations"][0]["candidate"]
    assert candidate["purchase_date"] == supplied
    assert not any(w["code"] == "purchase_date_from_receipt" for w in candidate["warnings"])


def test_receipt_parse_confirm_round_trip_learns_reviewed_name(client, db_session, fake_ai):
    candidate = _candidate(client, fake_ai, category_id=get_category_by_slug(db_session, "dairy").id)
    reviewed = {**candidate, "name": DAIRY_NAME, "unopened_expiration_date": "infinite"}
    response = _confirm(client, reviewed)
    assert response.status_code == 201, response.text
    item = db_session.get(Item, response.json()["created"][0]["item_id"])
    assert item.name == DAIRY_NAME and item.category_id == candidate["category_id"]
    assert not hasattr(item, "price")
    assert _candidate(client, fake_ai)["suggestions"] == [
        {"name": DAIRY_NAME, "source": "user_alias_history", "confirmed_count": 1},
    ]


def test_normal_text_adds_keep_the_existing_candidate_shape(client, db_session, fake_ai):
    result = _parse(client, fake_ai, _line(source={"input_kind": "text"}, alias_mode="auto"))
    candidate = result["operations"][0]["candidate"]
    assert candidate["source"]["input_kind"] == "text"
    assert "specificity" not in candidate and "alias_mode" not in candidate and "suggestions" not in candidate
    assert db_session.query(ReceiptItemAlias).count() == 0


def test_receipt_alias_promotes_after_three_confirmations_and_reuses_values(
    client, db_session, fake_ai, monkeypatch,
):
    for _ in range(2):
        assert _confirm(client, _confirmed(db_session)).status_code == 201

    def no_repeat_search(*args):
        pytest.fail("already confirmed aliases must not look up the product again")

    monkeypatch.setattr(receipt_lookup, "lookup_products", no_repeat_search)
    found = _candidate(client, fake_ai, raw_name=" ＯＲＧ ＭＬＫ ２％   $4.99 ", store_name="Trader Joe’s")
    assert found["name"] == "Milk"
    assert found["suggestions"] == [{"name": DAIRY_NAME, "source": "user_alias_history", "confirmed_count": 2}]
    assert found["alias_mode"] == "suggest" and found["requires_user_review"]

    assert _confirm(client, _confirmed(db_session, store_name="TRADER JOES")).status_code == 201
    stock = db_session.query(Item).order_by(Item.id).all()
    alias = db_session.query(ReceiptItemAlias).one()
    assert len(stock) == 3 and all(item.name == DAIRY_NAME for item in stock)
    assert "price" not in Item.__table__.c
    assert (alias.store_key, alias.store_name, alias.raw_name_original) == ("traderjoes", "TRADER JOES", RAW_NAME)
    assert (alias.confirmed_count, alias.distinct_confirmed_names_count, alias.alias_mode) == (3, 1, "auto")
    assert alias.confirmed_location == "Fridge" and alias.last_confirmed_at is not None
    assert db_session.query(ReceiptAliasName).one().count == 3

    found = _candidate(client, fake_ai, confidence=0.2, category_id=get_category_by_slug(db_session, "fruit").id)
    assert found["name"] == DAIRY_NAME and found["category_id"] == stock[0].category_id
    assert found["quantity_unit"] == "carton" and found["confidence"] == 0.9
    assert found["alias_mode"] == "auto" and found["match_method"] == "alias"
    assert found["auto_apply_allowed"] and not found["requires_user_review"]
    assert found["review_reason"] is None


def test_generic_safety_list_blocks_promotion_and_preserves_duplicate_lines(client, db_session, fake_ai):
    for _ in range(10):
        response = _confirm(client, _confirmed(db_session, raw_name="蔬菜", specificity="specific_product"))
        assert response.status_code == 201, response.text
    alias = db_session.query(ReceiptItemAlias).one()
    assert (alias.confirmed_count, alias.specificity, alias.alias_mode) == (10, "generic_category", "suggest")

    result = _parse(client, fake_ai, *[
        _line(raw_name="蔬菜", name="Tomatoes", price=price, specificity="specific_product",
              alias_mode="auto", auto_apply_allowed=True) for price in (4.3, 6.8, 9.2)
    ])
    candidates = [op["candidate"] for op in result["operations"]]
    assert len(candidates) == len({c["temporary_id"] for c in candidates}) == 3
    assert [c["price"] for c in candidates] == [4.3, 6.8, 9.2]
    for index, candidate in enumerate(candidates):
        assert candidate["name"] is None and candidate["raw_name"] == "蔬菜"
        assert candidate["specificity"] == "generic_category" and not candidate["auto_apply_allowed"]
        assert candidate["requires_user_review"] and candidate["review_reason"] == "generic_receipt_label"
        assert candidate["suggestions"][0]["confirmed_count"] == 10
        assert ({"code": "duplicate_generic_line", "params": {}} in candidate["warnings"]) is bool(index)


@pytest.mark.parametrize("raw_name", [
    "水果", "蔬菜 2", " ＰＲＯＤＵＣＥ ¥3.40", "Vegetables", "fruits", "weighted item", "bulk item", "MISC",
])
def test_generic_labels_override_model_classification(client, fake_ai, raw_name):
    found = _candidate(client, fake_ai, raw_name=raw_name, specificity="specific_product")
    assert found["specificity"] == "generic_category"
    assert found["name"] is None and not found["auto_apply_allowed"]


def test_multiple_names_downgrade_permanently_and_rank_five_suggestions(client, db_session, fake_ai):
    names = [DAIRY_NAME] * 3 + ["Skim Milk"] * 2 + ["A", "B", "C", "D", "E"] + [DAIRY_NAME] * 4
    items = [_confirmed(db_session, i, name=name) for i, name in enumerate(names, 1)]
    response = _confirm(client, *items)
    assert response.status_code == 201, response.text
    alias = db_session.query(ReceiptItemAlias).one()
    assert alias.alias_mode == "suggest"
    assert (alias.confirmed_count, alias.distinct_confirmed_names_count) == (14, 7)
    found = _candidate(client, fake_ai)
    assert found["name"] == "Milk" and found["requires_user_review"]
    assert found["review_reason"] == "multi_mapped_alias"
    assert [(entry["name"], entry["confirmed_count"]) for entry in found["suggestions"]] == [
        (DAIRY_NAME, 7), ("Skim Milk", 2), ("A", 1), ("B", 1), ("C", 1),
    ]


def test_same_raw_name_has_distinct_aliases_per_store_including_unknown(client, db_session, fake_ai):
    items = [
        _confirmed(db_session, 1, store_name=STORE, name="A"),
        _confirmed(db_session, 2, store_name="Market B", name="B"),
        _confirmed(db_session, 3, store_name=None, name="Unknown Store Milk"),
    ]
    assert _confirm(client, *items).status_code == 201
    aliases = db_session.query(ReceiptItemAlias).all()
    assert {(alias.store_key, alias.confirmed_item_name) for alias in aliases} == {
        ("traderjoes", "A"), ("marketb", "B"), ("", "Unknown Store Milk"),
    }
    for store, name in [("Trader Joe’s", "A"), (" market b ", "B"), (None, "Unknown Store Milk")]:
        found = _candidate(client, fake_ai, store_name=store)
        assert [entry["name"] for entry in found["suggestions"]] == [name]
    assert _candidate(client, fake_ai, store_name="Store C")["review_reason"] == "first_seen"


def test_suggestions_flag_low_confidence_and_inferred_fields(client, db_session, fake_ai):
    assert _confirm(client, _confirmed(db_session)).status_code == 201
    assert _candidate(client, fake_ai, confidence=0.59)["review_reason"] == "low_confidence"
    inferred = _candidate(client, fake_ai, confidence=0.6, inferred_fields=["quantity_unit", "location", "bogus"])
    assert inferred["review_reason"] == "inferred_fields"
    assert inferred["warnings"] == [
        {"code": "quantity_unit_inferred", "params": {"field": "quantity_unit"}},
        {"code": "location_inferred", "params": {"field": "location"}},
    ]
    assert _candidate(client, fake_ai, confidence=0.6)["review_reason"] == "alias_suggestion"


def test_unknown_and_blocked_aliases_do_not_promote(client, db_session, fake_ai):
    assert _confirm(client, *[
        _confirmed(db_session, i, specificity="unknown") for i in (1, 2, 3)
    ]).status_code == 201
    alias = db_session.query(ReceiptItemAlias).one()
    assert alias.alias_mode == "suggest"
    alias.alias_mode = "blocked"
    db_session.commit()

    assert _confirm(client, _confirmed(db_session)).status_code == 201
    assert db_session.query(ReceiptItemAlias).one().alias_mode == "blocked"
    candidate = _candidate(client, fake_ai)
    assert candidate["alias_mode"] == "blocked" and not candidate["auto_apply_allowed"]


def test_auto_alias_with_removed_category_requires_review(client, db_session, fake_ai):
    category = Category(name="Custom dairy", slug="receipt-custom")
    db_session.add(category)
    db_session.commit()
    category_id = category.id
    assert _confirm(client, *[
        _confirmed(db_session, i, category_id=category_id) for i in (1, 2, 3)
    ]).status_code == 201
    db_session.query(Item).delete()
    db_session.commit()
    assert client.delete(f"/api/categories/{category_id}").status_code == 200
    alias = db_session.query(ReceiptItemAlias).one()
    assert alias.confirmed_category_id is None
    found = _candidate(client, fake_ai)
    assert found["requires_user_review"] and not found["auto_apply_allowed"]
    assert found["suggestions"][0]["name"] == DAIRY_NAME


def test_receipt_image_uses_same_rules_and_keeps_distinct_receipt_groups(client, fake_ai, monkeypatch):
    monkeypatch.setenv("AI_VISION_ENABLED", "true")
    ai_client.reload_config()
    fake_ai.reply = json.dumps({"operations": [
        {
            "op": "add", "source": {"input_kind": "receipt", "image_index": i},
            "candidate": _line(raw_name="produce", receipt_group=group, price=i + 1),
        }
        for i, group in enumerate(("one", "one", "two"))
    ]})
    response = client.post(PARSE, files=[
        ("payload", (None, '{"draft":{"items":[]},"context":{"locale":"en"}}')),
        *(("images", (f"{i}.jpg", b"\xff\xd8\xffimage")) for i in range(3)),
    ])
    assert response.status_code == 200, response.text
    operations = response.json()["operations"]
    assert [operation["source"]["image_index"] for operation in operations] == [0, 1, 2]
    assert all(op["candidate"]["name"] is None for op in operations)
    assert [
        any(w["code"] == "duplicate_generic_line" for w in op["candidate"]["warnings"]) for op in operations
    ] == [False, True, False]


def test_receipt_learning_rolls_back_stock_restock_and_both_alias_tables(client, db_session, monkeypatch):
    restock = client.post("/api/restock", json=make_restock_create_payload(quantity_value=1))
    restock_id = restock.json()["id"]
    learn = intake_services.learn_receipt_alias
    recorded = []

    def fail_after_learning(db, *args):
        learn(db, *args)
        recorded.append(True)
        if len(recorded) == 2:
            raise RuntimeError("alias write failed")

    monkeypatch.setattr(intake_services, "learn_receipt_alias", fail_after_learning)
    with pytest.raises(RuntimeError, match="alias write failed"):
        _confirm(
            client, _confirmed(db_session, matched_restock_id=restock_id, restock_action="done"),
            _confirmed(db_session, 2, raw_name="Oreo"),
        )
    assert len(recorded) == 2
    assert [db_session.query(model).count() for model in (Item, ReceiptItemAlias, ReceiptAliasName)] == [0] * 3
    assert db_session.get(RestockItem, restock_id).status == "pending"


def test_receipt_lookup_default_is_local_noop_and_unsupported_provider_falls_back():
    config = ai_client.load_config({"RECEIPT_PRODUCT_LOOKUP_PROVIDER": "unsupported"})
    assert config.receipt_lookup_provider == "none"
    assert receipt_lookup.lookup_products([RAW_NAME], STORE) == {}


@pytest.mark.parametrize("value", [False, -1, float("inf"), 10**500, "4.99"])
def test_invalid_receipt_price_is_omitted(client, fake_ai, value):
    assert _candidate(client, fake_ai, price=value)["price"] is None


def test_parallel_confirms_keep_every_alias_count(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'receipt-aliases.db'}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(Category(name="Dairy", slug="dairy"))
            db.commit()
            items = [_confirmed(db, name=name) for name in (DAIRY_NAME, "Skim Milk", DAIRY_NAME, DAIRY_NAME)]

        barrier = Barrier(len(items), timeout=10)

        def confirm(item):
            request = ConfirmRequest.model_validate({
                "defaults": {"owner": "me", "location": "Fridge"}, "items": [item],
            })
            with Session(engine) as db:
                barrier.wait()
                return intake_services.confirm_intake(db, request)

        with ThreadPoolExecutor(max_workers=len(items)) as pool:
            assert all(result["created"] for result in pool.map(confirm, items))

        with Session(engine) as db:
            alias = db.query(ReceiptItemAlias).one()
            assert (alias.confirmed_count, alias.distinct_confirmed_names_count, alias.alias_mode) == (4, 2, "suggest")
            assert {row.confirmed_item_name: row.count for row in alias.names} == {
                DAIRY_NAME: 3, "Skim Milk": 1,
            }
            assert db.query(Item).count() == 4
    finally:
        engine.dispose()


def test_mysql_alias_upsert_compiles_atomic_increment_without_a_connection():
    db = Mock()
    db.get_bind.return_value.dialect.name = "mysql"
    aliases = ReceiptItemAlias.__table__
    _upsert(
        db, aliases, ("store_key", "raw_name_normalized"),
        {"store_key": "market", "raw_name_normalized": "milk", "confirmed_count": 1},
        {"confirmed_count": aliases.c.confirmed_count + 1},
    )
    statement = db.execute.call_args.args[0].compile(dialect=mysql.dialect())
    assert "ON DUPLICATE KEY UPDATE confirmed_count = (receipt_item_aliases.confirmed_count + %s)" in str(statement)

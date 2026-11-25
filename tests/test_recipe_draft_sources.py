"""AI draft identity and saved recipe behavior (#100)."""

import json
from hashlib import sha256

import pytest

from stock_manager.api.models import Recipe


@pytest.fixture
def expanded_draft(client, fake_ai):
    fake_ai.reply = json.dumps({
        "title": "Tomato Soup", "category": "soup", "description": "A quick soup",
        "difficulty": "easy", "servings": "2", "cook_time_minutes": 15,
        "ingredients": [{"ingredient_name": "Tomato", "quantity": "2", "unit": "pcs"}],
        "steps": [{"step_number": 1, "instruction": "Simmer the tomatoes."}],
    })
    response = client.post("/api/recipes/explore/expand", json={
        "idea": {"title": "Tomato Soup"}, "locale": "en",
    })
    assert response.status_code == 200, response.text
    return response.json()


def _save(client, expanded, **changes):
    response = client.post("/api/recipes", json={
        **expanded["recipe_draft"], "ai_draft_hash": expanded["draft_hash"], **changes,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_expand_hashes_canonical_content_and_unchanged_save_is_ai_saved(client, expanded_draft):
    content = {
        key: value for key, value in expanded_draft["recipe_draft"].items()
        if key not in {"category", "equipment"}
    }
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert expanded_draft["draft_hash"] == sha256(canonical.encode("utf-8")).hexdigest()

    recipe = _save(client, expanded_draft)

    assert (recipe["source_type"], recipe["source_name"], recipe["is_user_created"]) == (
        "ai_saved", "AI", True,
    )
    listing = client.get("/api/recipes", params={"source_type": "ai_saved"})
    assert listing.status_code == 200
    assert [result["id"] for result in listing.json()] == [recipe["id"]]


def test_unfiltered_list_ranks_ai_saved_and_user_recipes_before_howtocook(
    client, db_session, expanded_draft,
):
    imported = Recipe(
        title="Imported soup", category="soup", source_type="howtocook", source_name="HowToCook",
    )
    db_session.add(imported)
    db_session.commit()
    imported_id = imported.id
    ai_saved = _save(client, expanded_draft)
    user = _save(client, expanded_draft, title="My soup")

    response = client.get("/api/recipes")

    assert response.status_code == 200, response.text
    assert [(recipe["id"], recipe["source_type"]) for recipe in response.json()] == [
        (ai_saved["id"], "ai_saved"),
        (user["id"], "user"),
        (imported_id, "howtocook"),
    ]


@pytest.mark.parametrize(("field", "value"), [
    ("title", "Different soup"),
    ("description", "Another description"),
    ("difficulty", "hard"),
    ("servings", "4"),
    ("cook_time_minutes", 20),
    ("raw_markdown", "# Soup"),
    ("ingredients", [{"ingredient_name": "Carrot"}]),
    ("steps", [{"step_number": 1, "instruction": "Roast the tomatoes."}]),
])
def test_changing_any_content_field_saves_as_user(client, expanded_draft, field, value):
    recipe = _save(client, expanded_draft, **{field: value})
    assert (recipe["source_type"], recipe["source_name"], recipe["is_user_created"]) == (
        "user", "User", True,
    )


def test_category_choice_keeps_ai_source(client, expanded_draft):
    recipe = _save(client, expanded_draft, category="vegetable_dish")
    assert (recipe["category"], recipe["source_type"]) == ("vegetable_dish", "ai_saved")


@pytest.mark.parametrize("draft_hash", [None, "0" * 64])
def test_missing_or_different_hash_saves_as_user(client, expanded_draft, draft_hash):
    recipe = _save(client, expanded_draft, ai_draft_hash=draft_hash)
    assert recipe["source_type"] == "user"


def test_editing_ai_saved_recipe_converts_to_user(client, expanded_draft):
    recipe = _save(client, expanded_draft)

    edited = client.patch(f"/api/recipes/{recipe['id']}", json={"title": "My Soup"})

    assert edited.status_code == 200, edited.text
    assert (edited.json()["source_type"], edited.json()["source_name"], edited.json()["is_user_created"]) == (
        "user", "User", True,
    )
    assert client.get("/api/recipes", params={"source_type": "ai_saved"}).json() == []


def test_ai_saved_can_be_favorited_forked_in_place_and_deleted(client, expanded_draft):
    recipe = _save(client, expanded_draft)
    path = f"/api/recipes/{recipe['id']}"

    assert client.post(f"{path}/favorite").status_code == 200
    assert client.get(path).json()["source_type"] == "ai_saved"
    assert client.get(path).json()["is_favorite"] is True
    fork = client.post(f"{path}/fork")
    assert fork.status_code == 200
    assert (fork.json()["id"], fork.json()["source_type"]) == (recipe["id"], "ai_saved")
    assert client.delete(path).status_code == 200
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(("equipment", "expected", "warning_values"), [
    (["steamer", "oven", "steamer"], [["oven"], ["steamer"]], []),
    (["oven", "x" * 80, 123], [["oven"]], ["x" * 50, "123"]),
    ("oven", [], []),
])
def test_expand_equipment_and_warnings(client, fake_ai, equipment, expected, warning_values):
    from stock_manager.api.equipment import EQUIPMENT_CODES

    fake_ai.reply = json.dumps({
        "title": "Soup", "category": "soup",
        "steps": [{"instruction": "Cook the soup."}], "equipment": equipment,
    })
    response = client.post("/api/recipes/explore/expand", json={
        "idea": {"title": "Soup"}, "locale": "en",
    })

    assert response.status_code == 200, response.text
    expanded = response.json()
    assert expanded["recipe_draft"]["equipment"] == expected
    assert [w for w in expanded["warnings"] if w["code"] == "field_value_dropped"] == [
        {"code": "field_value_dropped", "params": {"field": "equipment", "value": value}}
        for value in warning_values
    ]
    assert len(fake_ai.requests) == 1
    prompt = fake_ai.system_prompts[0]
    assert ", ".join(EQUIPMENT_CODES) in prompt
    example = prompt.split("```json", 1)[1].split("```", 1)[0]
    assert json.loads(example)["equipment"] == ["oven"]


def test_equipment_does_not_affect_draft_identity(client, expanded_draft):
    from stock_manager.api.recipe_schemas import RecipeDraft
    from stock_manager.api.recipe_services import recipe_draft_hash

    draft = RecipeDraft.model_validate(expanded_draft["recipe_draft"])
    equipped = draft.model_copy(update={"equipment": [["oven"]]})
    assert recipe_draft_hash(equipped) == recipe_draft_hash(draft) == expanded_draft["draft_hash"]
    assert _save(client, expanded_draft, equipment=equipped.equipment)["source_type"] == "ai_saved"
    payload = equipped.model_dump(exclude={"equipment"})
    response = client.post("/api/recipes", json={**payload, "ai_draft_hash": recipe_draft_hash(equipped)})
    assert response.status_code == 201, response.text
    assert response.json()["source_type"] == "ai_saved"


def test_dropped_equipment_does_not_create_draft_problem():
    from stock_manager.api.ai_output import Inventory, clean_draft

    result = clean_draft(
        {"title": "Soup", "steps": ["Cook the soup."], "equipment": ["unknown"]},
        {}, "en", Inventory([]),
    )
    assert result.draft["equipment"] == []
    assert result.problems == []

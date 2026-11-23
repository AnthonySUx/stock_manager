"""AI draft identity and saved recipe behavior (#100)."""

import json
from hashlib import sha256

import pytest


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
    content = {key: value for key, value in expanded_draft["recipe_draft"].items() if key != "category"}
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert expanded_draft["draft_hash"] == sha256(canonical.encode("utf-8")).hexdigest()

    recipe = _save(client, expanded_draft)

    assert (recipe["source_type"], recipe["source_name"], recipe["is_user_created"]) == (
        "ai_saved", "AI", False,
    )
    listing = client.get("/api/recipes", params={"source_type": "ai_saved"})
    assert listing.status_code == 200
    assert [result["id"] for result in listing.json()] == [recipe["id"]]


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

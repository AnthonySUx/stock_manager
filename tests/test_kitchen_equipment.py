"""API coverage for household settings, recipe requirements, and filtering."""

import pytest

from stock_manager.api.models import HouseholdEquipment, Recipe, RecipeEquipment, Setting

CODES = [
    "oven", "air_fryer", "microwave", "pressure_cooker", "rice_cooker", "steamer",
    "blender", "electric_mixer", "bread_machine", "clay_pot", "grill",
    "thermometer", "kitchen_scale",
]


def _settings(client):
    response = client.get("/api/settings")
    assert response.status_code == 200, response.text
    return response.json()


def _configure(client, codes):
    response = client.patch("/api/settings", json={"kitchen_equipment": codes})
    assert response.status_code == 200, response.text
    return response.json()


def _make_recipe(client, title, groups):
    response = client.post("/api/recipes", json={
        "title": title, "category": "soup", "equipment": groups,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_equipment_catalog_order_and_authentication(client):
    response = client.get("/api/equipment")
    assert response.status_code == 200
    assert response.json() == {"codes": CODES}
    assert client.get("/api/equipment", headers={"Authorization": ""}).status_code == 401


def test_settings_replace_preserve_and_clear_equipment(client):
    initial = _settings(client)
    assert initial["kitchen_equipment"] == []
    assert initial["kitchen_equipment_configured"] is False
    assert client.patch("/api/settings", json={"kitchen_equipment": None}).json() == initial

    saved = _configure(client, ["microwave", "oven", "microwave"])
    assert saved["kitchen_equipment"] == ["oven", "microwave"]
    assert saved["kitchen_equipment_configured"] is True

    saved = _configure(client, ["clay_pot"])
    assert saved["kitchen_equipment"] == ["clay_pot"]
    for extra in ({}, {"kitchen_equipment": None}):
        response = client.patch("/api/settings", json={"expiration_reminder_days": 3, **extra})
        assert response.status_code == 200, response.text
        assert response.json()["kitchen_equipment"] == ["clay_pot"]
        assert response.json()["kitchen_equipment_configured"] is True

    cleared = _configure(client, [])
    assert cleared["kitchen_equipment"] == []
    assert cleared["kitchen_equipment_configured"] is True
    assert _settings(client) == cleared


def test_first_empty_settings_save_configures_equipment(client):
    assert _configure(client, [])["kitchen_equipment_configured"] is True


@pytest.mark.parametrize("already_configured", [False, True])
def test_unknown_equipment_does_not_write_settings(client, db_session, already_configured, monkeypatch):
    if already_configured:
        _configure(client, ["oven"])
    before = _settings(client)
    commits = []
    monkeypatch.setattr(db_session, "commit", lambda: commits.append(1))
    response = client.patch("/api/settings", json={
        "kitchen_equipment": ["unknown", "bad", "unknown", "steamer"],
        "expiration_reminder_days": 42,
    })
    assert response.status_code == 422
    assert response.json()["code"] == "equipment_unknown"
    assert response.json()["params"] == {"codes": ["bad", "unknown"]}
    assert _settings(client) == before
    assert commits == []
    assert not db_session.new and not db_session.dirty and not db_session.deleted


def test_combined_settings_update_commits_once(client, db_session, monkeypatch):
    commits = []
    commit = db_session.commit

    def track_commit():
        commits.append(1)
        commit()

    monkeypatch.setattr(db_session, "commit", track_commit)
    response = client.patch("/api/settings", json={
        "kitchen_equipment": ["grill"], "expiration_reminder_days": 4,
    })
    assert response.status_code == 200, response.text
    assert response.json()["expiration_reminder_days"] == "4"
    assert response.json()["kitchen_equipment"] == ["grill"]
    assert db_session.get(Setting, "kitchen_equipment_configured").value == "1"
    assert db_session.get(HouseholdEquipment, "grill") is not None
    assert commits == [1]


def test_recipe_create_update_and_delete_equipment(client, db_session):
    recipe = _make_recipe(client, "Equipment soup", [
        ["clay_pot"], ["rice_cooker", "oven", "oven"], ["oven", "rice_cooker"],
    ])
    recipe_id = recipe["id"]
    path = f"/api/recipes/{recipe_id}"
    assert recipe["equipment"] == [["clay_pot"], ["oven", "rice_cooker"]]
    assert recipe["missing_equipment"] == []
    assert client.patch(path, json={"title": "Soup"}).json()["equipment"] == recipe["equipment"]

    response = client.patch(path, json={"equipment": [["oven"]]})
    assert response.status_code == 200, response.text
    assert response.json()["equipment"] == [["oven"]]
    assert client.patch(path, json={"equipment": []}).json()["equipment"] == []
    assert client.get(path).json()["equipment"] == []

    assert client.patch(path, json={"equipment": [["grill"]]}).status_code == 200
    assert db_session.query(RecipeEquipment).filter_by(recipe_id=recipe_id).count() == 1
    assert client.delete(path).status_code == 200
    assert db_session.query(RecipeEquipment).filter_by(recipe_id=recipe_id).count() == 0


@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize(("groups", "code"), [
    ([["unrecognized"]], "equipment_unknown"),
    ([[]], "validation_error"),
    ([["oven"]] * 11, "validation_error"),
    ([["oven"] * 6], "validation_error"),
    (None, "validation_error"),
])
def test_recipe_equipment_validation(client, method, groups, code):
    payload = {"equipment": groups}
    path = "/api/recipes"
    if method == "post":
        payload.update(title="Invalid recipe", category="soup")
    else:
        recipe = _make_recipe(client, "Unchanged recipe", [["oven"]])
        path += f"/{recipe['id']}"
    response = client.request(method, path, json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == code
    if method == "patch":
        assert client.get(path).json()["equipment"] == [["oven"]]


def test_fork_copies_imported_equipment(client, db_session):
    recipe = Recipe(title="Imported", category="soup", source_type="howtocook")
    db_session.add(recipe)
    db_session.flush()
    db_session.add_all([
        RecipeEquipment(recipe_id=recipe.id, group_index=0, equipment_code=code)
        for code in ["steamer", "rice_cooker"]
    ])
    db_session.commit()
    response = client.post(f"/api/recipes/{recipe.id}/fork")
    assert response.status_code == 200, response.text
    fork = response.json()
    assert fork["base_recipe_id"] == recipe.id
    assert fork["equipment"] == [["rice_cooker", "steamer"]]
    assert client.patch(f"/api/recipes/{fork['id']}", json={"equipment": []}).status_code == 200
    assert client.get(f"/api/recipes/{recipe.id}").json()["equipment"] == [["rice_cooker", "steamer"]]


def test_cookable_filter_and_missing_equipment(client):
    groups = [["oven", "rice_cooker"], ["blender"]]
    stew = _make_recipe(client, "Kitchen stew", groups)["id"]
    soup = _make_recipe(client, "Kitchen soup", [["steamer"]])["id"]
    salad = _make_recipe(client, "Kitchen salad", [])["id"]

    def listed(cookable_only):
        response = client.get("/api/recipes", params={"query": "Kitchen", "cookable_only": cookable_only})
        assert response.status_code == 200, response.text
        return {r["id"]: r["missing_equipment"] for r in response.json()}

    assert listed(True) == {stew: [], soup: [], salad: []}
    assert client.get(f"/api/recipes/{stew}").json()["missing_equipment"] == []

    _configure(client, [])
    assert listed(True) == {salad: []}
    assert listed(False) == {stew: groups, soup: [["steamer"]], salad: []}

    _configure(client, ["rice_cooker"])
    assert listed(False)[stew] == [["blender"]]
    assert client.get(f"/api/recipes/{stew}").json()["missing_equipment"] == [["blender"]]
    assert listed(True) == {salad: []}

    _configure(client, ["rice_cooker", "blender"])
    assert listed(True) == {stew: [], salad: []}
    assert listed(False) == {stew: [], soup: [["steamer"]], salad: []}
    first = client.get("/api/recipes?cookable_only=true&limit=1&offset=1").json()
    assert [r["id"] for r in first] == [salad]


def test_recommendations_require_each_configured_group(client):
    alternative = _make_recipe(client, "Alternative", [["oven", "rice_cooker"], ["blender"]])["id"]
    oven = _make_recipe(client, "Oven", [["oven"]])["id"]
    none = _make_recipe(client, "No equipment", [])["id"]

    def recommended():
        response = client.get("/api/recipes/recommendations")
        assert response.status_code == 200, response.text
        return {r["recipe_id"] for r in response.json()["recommendations"]}

    assert recommended() == {alternative, oven, none}
    _configure(client, [])
    assert recommended() == {none}
    _configure(client, ["rice_cooker", "blender"])
    assert recommended() == {alternative, none}
    _configure(client, ["oven", "blender"])
    assert recommended() == {alternative, oven, none}

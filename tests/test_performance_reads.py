"""Issue #48: fewer queries and no writes on reads, with identical results."""

from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from sqlalchemy import event, func

from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.models import (
    Item,
    Recipe,
    RecipeFavorite,
    RecipeIngredient,
    RecipeUsageHistory,
)
from stock_manager.api.recipe_services import get_recipes
from tests.conftest import test_engine
from tests.helpers import make_item_create_payload


@contextmanager
def count_sql():
    """Collect the SQL statements run inside the block."""
    statements: list[str] = []

    def before(conn, cursor, statement, *args):
        statements.append(" ".join(statement.split()).lower())

    event.listen(test_engine, "before_cursor_execute", before)
    try:
        yield statements
    finally:
        event.remove(test_engine, "before_cursor_execute", before)


def _selects_from(statements, table):
    return [s for s in statements if s.startswith("select") and f"from {table}" in s]


def _item(client, db_session, name, expires_in_days, quantity=2):
    when = (date.today() + timedelta(days=expires_in_days)).isoformat()
    payload = make_item_create_payload(
        name=name,
        category_id=get_category_by_slug(db_session, "vegetables").id,
        quantity_value=quantity,
        unopened_expiration_date=when,
        current_expiration_date=when,
    )
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ─── Items: status refresh and reminders ──────────────────────────


class TestReminders:
    def test_order_and_content(self, client, db_session):
        expired_a = _item(client, db_session, "过期A", -3)
        soon_a = _item(client, db_session, "临期A", 1)
        _item(client, db_session, "正常", 30)
        expired_b = _item(client, db_session, "过期B", -1)
        soon_b = _item(client, db_session, "临期B", 0)
        used = _item(client, db_session, "用完", -5)
        assert client.post(f"/api/items/{used}/consume", json={"quantity": 2}).status_code == 200

        response = client.get("/api/items/reminders")

        assert response.status_code == 200
        # Expiring soon first, then expired; each in id order (same as before #48).
        assert [i["id"] for i in response.json()] == [soon_a, soon_b, expired_a, expired_b]

    def test_one_refresh_and_one_query(self, client, db_session):
        _item(client, db_session, "临期", 1)
        _item(client, db_session, "过期", -1)

        with count_sql() as statements:
            assert client.get("/api/items/reminders").status_code == 200

        # One full-table read for the refresh, one for the reminder list.
        assert len(_selects_from(statements, "items")) == 2

    def test_reminders_see_status_that_went_stale(self, client, db_session):
        item_id = _item(client, db_session, "牛奶", 30)
        # Simulate time passing: the stored status is now out of date.
        item = db_session.get(Item, item_id)
        item.current_expiration_date = (date.today() - timedelta(days=1)).isoformat()
        db_session.commit()

        assert [i["id"] for i in client.get("/api/items/reminders").json()] == [item_id]


class TestRefreshWritesOnlyWhenNeeded:
    def _count_commits(self, db_session, monkeypatch):
        calls = []
        real = db_session.commit
        monkeypatch.setattr(db_session, "commit", lambda: (calls.append(1), real())[1])
        return calls

    def test_read_without_changes_does_not_commit(self, client, db_session, monkeypatch):
        _item(client, db_session, "番茄", 30)
        commits = self._count_commits(db_session, monkeypatch)

        for url in ("/api/items", "/api/items/search?keyword=番", "/api/items/reminders"):
            assert client.get(url).status_code == 200

        assert commits == []

    def test_stale_status_is_fixed_and_committed(self, client, db_session, monkeypatch):
        item_id = _item(client, db_session, "番茄", 30)
        item = db_session.get(Item, item_id)
        item.current_expiration_date = (date.today() + timedelta(days=1)).isoformat()
        db_session.commit()
        commits = self._count_commits(db_session, monkeypatch)

        listed = client.get("/api/items").json()

        assert [i["status"] for i in listed] == ["expiring soon"]
        assert commits == [1]


# ─── Recipes list: same order as the old in-memory version ────────


def _old_get_recipes(db, *, source_type=None, category=None, query=None,
                     favorite_only=False, limit=20, offset=0):
    """get_recipes as it was before #48 (load all, sort in Python, slice)."""
    q = db.query(Recipe)
    if source_type:
        q = q.filter(Recipe.source_type == source_type)
    if category:
        q = q.filter(func.lower(Recipe.category) == category.lower())
    if query:
        pattern = f"%{query}%"
        q = q.filter(
            func.lower(Recipe.title).like(pattern.lower())
            | func.lower(func.coalesce(Recipe.description, "")).like(pattern.lower())
        )
    if favorite_only:
        q = q.filter(Recipe.id.in_(db.query(RecipeFavorite.recipe_id)))
    results = q.order_by(Recipe.id).all()
    fav_ids = {r[0] for r in db.query(RecipeFavorite.recipe_id).all()}
    cooked_ids = {r[0] for r in db.query(RecipeUsageHistory.recipe_id).filter(
        RecipeUsageHistory.event_type == "cooked").all()}
    if not query:
        results.sort(key=lambda r: (
            r.id not in fav_ids, r.id not in (fav_ids | cooked_ids), not r.is_user_created, r.id,
        ))
    else:
        q_lower = query.lower().strip()

        def search_score(recipe):
            score = 0
            title_lower = recipe.title.lower()
            if recipe.is_user_created:
                score += 100
            if recipe.id in fav_ids:
                score += 80
            if recipe.id in cooked_ids:
                score += 60
            if title_lower == q_lower:
                score += 50
            elif q_lower in title_lower:
                score += 40
            for ing in recipe.ingredients or []:
                if q_lower in ing.ingredient_name.lower() or (
                    ing.normalized_name and q_lower in ing.normalized_name.lower()
                ):
                    score += 25
                    break
            if recipe.description and q_lower in recipe.description.lower():
                score += 10
            return score

        results.sort(key=search_score, reverse=True)
    return results[offset:offset + limit]


TITLES = ["番茄炒蛋", "番茄", "番茄牛腩", "土豆丝", "红烧肉", "Tomato Soup", "tomato", "蛋炒饭",
          "凉拌黄瓜", "番茄鸡蛋面", "鸡蛋羹", "50%糖奶茶", "a_b 饼"]


@pytest.fixture()
def recipe_library(db_session):
    """Recipes covering every scoring rule, with ties on purpose."""
    for i, title in enumerate(TITLES * 2):
        recipe = Recipe(
            title=title,
            source_type=["howtocook", "user", "ai_saved"][i % 3],
            is_user_created=(i % 3 == 1),
            category=["meat_dish", "vegetable_dish", "soup"][i % 4 % 3],
            description=[None, "", "家常 番茄 味道", "TOMATO rich", "含 50% 糖"][i % 5],
        )
        db_session.add(recipe)
        db_session.flush()
        names = [("番茄", None), ("鸡蛋", "蛋"), ("盐", None)][: i % 4]
        if i % 6 == 5:
            # Matches "番茄" only through its normalized name.
            names = [("西红柿", "番茄")]
        for j, (name, norm) in enumerate(names):
            db_session.add(RecipeIngredient(recipe_id=recipe.id, ingredient_name=name,
                                            normalized_name=norm, sort_order=j))
        if i % 4 == 0:
            db_session.add(RecipeFavorite(recipe_id=recipe.id))
        if i % 5 in (0, 2):
            db_session.add(RecipeUsageHistory(recipe_id=recipe.id, event_type="cooked"))
            db_session.add(RecipeUsageHistory(recipe_id=recipe.id, event_type="cooked"))
        if i % 7 == 0:
            db_session.add(RecipeUsageHistory(recipe_id=recipe.id, event_type="recommended"))
    # Matched by the "  " query through the title; descriptions missing, empty, set.
    for description in (None, "", "家常"):
        db_session.add(Recipe(title="家常  小炒", source_type="howtocook", description=description))
    db_session.commit()


# "  " is empty after strip(): every substring test is true, except that an
# empty or missing description must still score 0.
QUERIES = [None, "番茄", "番茄炒蛋", "tomato", "TOMATO", "蛋", "鸡蛋", "50%", "_", "a_b", " 番茄 ",
           "  ", "不存在"]
FILTERS = [
    {},
    {"favorite_only": True},
    {"source_type": "user"},
    {"category": "SOUP"},
    {"source_type": "howtocook", "favorite_only": True},
]
PAGES = [(20, 0), (5, 0), (5, 5), (7, 3), (100, 0), (3, 40)]


@pytest.mark.parametrize("query", QUERIES)
@pytest.mark.parametrize("filters", FILTERS)
def test_get_recipes_order_matches_old_version(db_session, recipe_library, query, filters):
    for limit, offset in PAGES:
        kwargs = dict(filters, query=query, limit=limit, offset=offset)
        expected = [r.id for r in _old_get_recipes(db_session, **kwargs)]
        assert [r.id for r in get_recipes(db_session, **kwargs)] == expected, kwargs


def test_recipe_list_queries_do_not_grow_with_page_size(client, db_session, recipe_library):
    counts = []
    for limit in (2, 20):
        with count_sql() as statements:
            response = client.get(f"/api/recipes?limit={limit}")
        assert len(response.json()) == limit
        counts.append(len(statements))
    assert counts[0] == counts[1]


def test_recipe_list_flags_match_detail(client, db_session, recipe_library):
    for query in ("", "&query=番茄"):
        listed = client.get(f"/api/recipes?limit=100{query}").json()
        assert listed
        for summary in listed:
            detail = client.get(f"/api/recipes/{summary['id']}").json()
            assert (summary["is_favorite"], summary["has_been_cooked"]) == (
                detail["is_favorite"], detail["has_been_cooked"]
            )


# ─── Recommendations: ingredients in one query ────────────────────


def test_recommendations_load_ingredients_once(client, db_session, recipe_library):
    _item(client, db_session, "番茄", 1)
    for recipe in db_session.query(Recipe):
        recipe.source_type = "howtocook"
        recipe.source_path = f"dishes/{recipe.category}/{recipe.id}.md"
    db_session.commit()

    with count_sql() as statements:
        response = client.get("/api/recipes/recommendations?limit=50")

    assert response.status_code == 200
    assert response.json()["recommendations"]
    assert len(_selects_from(statements, "recipe_ingredients")) == 1


def test_recommendations_with_no_recipes(client, db_session):
    _item(client, db_session, "番茄", 1)
    response = client.get("/api/recipes/recommendations")
    assert response.status_code == 200
    assert response.json()["recommendations"] == []


def test_flags_helper_handles_empty_page(db_session):
    from stock_manager.api.recipe_services import get_recipe_flags
    assert get_recipe_flags(db_session, []) == (set(), set())

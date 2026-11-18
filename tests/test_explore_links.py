"""Explore ideas linked to local recipes (#66 part 6).

The thresholds were tuned on the 373 HowToCook titles; the pairs below come
from that list and from real Explore replies.
"""
import json

import pytest

from stock_manager.api.models import Recipe
from stock_manager.api.recipe_services import DEFAULT_SYNONYM_MAP
from stock_manager.api.text_search import TitleMatcher, dice

LIBRARY = [
    "西红柿炒鸡蛋的做法", "西红柿豆腐汤羹的做法", "徽派红烧肉的做法", "简易红烧肉的做法",
    "黄焖鸡的做法", "辣椒炒肉的做法", "黄瓜炒肉的做法", "鸡蛋花的做法", "紫菜蛋花汤的做法",
    "蛋炒饭的做法", "麻婆豆腐的做法", "酸梅汤（半成品加工）的做法", "手撕包菜的做法",
    "西红柿土豆炖牛肉的做法", "湖南农家家常红烧肉的做法", "烤鸡翅的做法", "西红柿鸡蛋挂面的做法",
    "Tomato Egg Fried Rice",
]


@pytest.fixture()
def matcher():
    return TitleMatcher(list(enumerate(LIBRARY, 1)), DEFAULT_SYNONYM_MAP)


def _linked(matcher, title):
    match = matcher.match(title)
    return LIBRARY[match.recipe_id - 1].removesuffix("的做法") if match else None


class TestTitleMatcher:
    @pytest.mark.parametrize("idea,recipe", [
        ("麻婆豆腐", "麻婆豆腐"),
        ("番茄炒蛋", "西红柿炒鸡蛋"),  # synonyms: 西红柿 → 番茄, 鸡蛋 → 蛋
        ("番茄炒鸡蛋", "西红柿炒鸡蛋"),
        (" 番茄 · 炒蛋！", "西红柿炒鸡蛋"),  # spaces and punctuation
        ("酸梅汤", "酸梅汤（半成品加工）"),  # bracketed notes
        ("手撕圆白菜", "手撕包菜"),  # both sides map to 卷心菜
        ("番茄豆腐汤", "西红柿豆腐汤羹"),  # contained after synonyms
        ("番茄鸡蛋面", "西红柿鸡蛋挂面"),  # similar, not contained: Dice 0.86
        ("tomato egg fried-rice", "Tomato Egg Fried Rice"),  # case and punctuation
        ("红烧肉", "徽派红烧肉"),  # contained; same length, older recipe wins
        ("黄焖鸡米饭", "黄焖鸡"),  # contains the recipe title
        ("土豆炖牛肉", "西红柿土豆炖牛肉"),
        ("蛋花汤", "紫菜蛋花汤"),  # not 鸡蛋花
        ("奥尔良烤鸡翅", "烤鸡翅"),
    ])
    def test_links(self, matcher, idea, recipe):
        assert _linked(matcher, idea) == recipe

    @pytest.mark.parametrize("idea", [
        "青椒炒肉",  # vs 辣椒炒肉: Dice 0.67, a different dish
        "黄瓜炒蛋",  # vs 黄瓜炒肉
        "炒饭",  # contained in 蛋炒饭, but only 2 characters
        "香菇豆腐煲",
        "Tomato egg",
        "",
        None,
        "（）",
    ])
    def test_no_link(self, matcher, idea):
        assert matcher.match(idea) is None

    def test_exact_beats_contained(self):
        m = TitleMatcher([(1, "简易红烧肉"), (2, "红烧肉")], {})
        match = m.match("红烧肉")
        assert (match.recipe_id, match.score) == (2, 1.0)

    def test_best_score_then_older_recipe(self):
        m = TitleMatcher([(1, "湖南家常红烧肉"), (3, "南派红烧肉"), (2, "简易红烧肉")], {})
        assert m.match("红烧肉").recipe_id == 2  # 0.67 beats 0.5; then id 2 before 3

    def test_containment_needs_enough_overlap(self, matcher):
        # 红烧肉 is inside 湖南农家家常红烧肉, but Dice is only 0.4.
        m = TitleMatcher([(1, "湖南农家家常红烧肉")], {})
        assert dice("红烧肉", "湖南农家家常红烧肉") < 0.5
        assert m.match("红烧肉") is None

    def test_one_character_aliases_are_not_replaced(self, matcher):
        # 蒜 → 大蒜 or 米 → 大米 would turn 蒜蓉虾 into 大蒜蓉虾.
        assert matcher.normalize("蒜蓉虾") == "蒜蓉虾"
        assert matcher.normalize("小米粥") == "小米粥"

    def test_synonyms_come_from_the_given_map(self):
        m = TitleMatcher([(1, "洋芋丝")], {"土豆": ["洋芋"]})
        assert m.match("土豆丝").recipe_id == 1
        assert TitleMatcher([(1, "洋芋丝")], {}).match("土豆丝") is None

    def test_recipes_without_a_usable_title_are_skipped(self):
        m = TitleMatcher([(1, ""), (2, None), (3, "！！"), (4, "蛋炒饭")], {})
        assert m.match("蛋炒饭").recipe_id == 4

    def test_every_library_title_finds_itself(self, matcher):
        for recipe_id, title in enumerate(LIBRARY, 1):
            assert matcher.match(title).recipe_id == recipe_id


# ─── Explore ─────────────────────────────────────────────────────


def _idea(title):
    return {"title": title, "description": f"{title}的做法很简单", "matched_ingredients": []}


@pytest.fixture()
def library(db_session):
    recipes = {}
    for title in ("西红柿炒鸡蛋的做法", "麻婆豆腐的做法", "简易红烧肉的做法"):
        recipe = Recipe(title=title, source_type="howtocook", source_name="HowToCook")
        db_session.add(recipe)
        db_session.flush()
        recipes[title.removesuffix("的做法")] = recipe.id
    db_session.commit()
    return recipes


def _explore(client, path="/api/recipes/explore"):
    return client.post(path, json={"mode": "natural_language", "natural_language": "晚饭"})


class TestExploreLinks:
    def test_ideas_are_linked(self, client, fake_ai, library):
        fake_ai.reply = json.dumps({"ideas": [_idea("番茄炒蛋"), _idea("虾仁蒸蛋"), _idea("麻婆豆腐")]},
                                   ensure_ascii=False)
        ideas = _explore(client).json()["ideas"]
        assert [(i["title"], i["source_type"], i["recipe_id"], i["can_expand_to_recipe"]) for i in ideas] == [
            ("番茄炒蛋", "existing_recipe", library["西红柿炒鸡蛋"], False),
            ("虾仁蒸蛋", "ai_idea", None, True),
            ("麻婆豆腐", "existing_recipe", library["麻婆豆腐"], False),
        ]

    def test_second_idea_for_the_same_recipe_is_not_sent(self, client, fake_ai, library):
        fake_ai.reply = json.dumps({"ideas": [_idea("番茄炒蛋"), _idea("西红柿炒鸡蛋"), _idea("红烧肉"),
                                              _idea("清蒸鲈鱼")]}, ensure_ascii=False)
        ideas = _explore(client).json()["ideas"]
        assert [i["title"] for i in ideas] == ["番茄炒蛋", "红烧肉", "清蒸鲈鱼"]
        assert ideas[1]["recipe_id"] == library["简易红烧肉"]

    def test_streamed_ideas_are_linked(self, client, fake_ai, library):
        fake_ai.reply = json.dumps({"ideas": [_idea("麻婆豆腐"), _idea("鱼香茄子"), _idea("番茄炒蛋")]},
                                   ensure_ascii=False)
        text = _explore(client, "/api/recipes/explore/stream").text
        ideas = [json.loads(line[6:]) for line in text.split("\n") if line.startswith("data: {\"idea_id")]
        assert [(i["title"], i["recipe_id"]) for i in ideas] == [
            ("麻婆豆腐", library["麻婆豆腐"]), ("鱼香茄子", None), ("番茄炒蛋", library["西红柿炒鸡蛋"]),
        ]
        assert ideas[0]["source_type"] == "existing_recipe" and ideas[1]["source_type"] == "ai_idea"

    def test_user_recipes_count_too(self, client, fake_ai, db_session):
        recipe = Recipe(title="外婆红烧肉", source_type="user", source_name="User", is_user_created=True)
        db_session.add(recipe)
        db_session.commit()
        fake_ai.reply = json.dumps({"ideas": [_idea("外婆 红烧肉")]}, ensure_ascii=False)
        idea = _explore(client).json()["ideas"][0]
        assert idea["recipe_id"] == recipe.id

    def test_without_local_recipes_nothing_is_linked(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [_idea("麻婆豆腐")]}, ensure_ascii=False)
        idea = _explore(client).json()["ideas"][0]
        assert (idea["source_type"], idea["recipe_id"], idea["can_expand_to_recipe"]) == ("ai_idea", None, True)

    def test_model_cannot_claim_a_link(self, client, fake_ai, library):
        fake_ai.reply = json.dumps({"ideas": [{**_idea("虾仁蒸蛋"), "source_type": "existing_recipe",
                                               "recipe_id": library["麻婆豆腐"]}]}, ensure_ascii=False)
        idea = _explore(client).json()["ideas"][0]
        assert (idea["source_type"], idea["recipe_id"]) == ("ai_idea", None)

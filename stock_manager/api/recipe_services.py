"""Business logic for recipe features."""
import json
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from math import isfinite
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_manager.api import media
from stock_manager.api.photo_services import delete_recipe_photos, move_orphaned_step_photos
from stock_manager.api.category_services import RECIPE_USAGE_NEVER
from stock_manager.api.equipment_services import (
    delete_recipe_equipment,
    load_recipe_equipment,
    meets_equipment_requirements,
    replace_recipe_equipment,
)
from stock_manager.api.errors import APIError
from stock_manager.api.models import (
    Recipe,
    RecipeFavorite,
    RecipeIngredient,
    RecipePhoto,
    RecipeStep,
    RecipeUsageHistory,
    RestockItem,
    utcnow,
)
from stock_manager.api.recipe_schemas import RecipeCreate, RecipeDraft, RecipeUpdate
from stock_manager.api.quantity import (
    parse_quantity,
    quantize_stock_quantity,
    round_stock_quantity,
    same_unit,
)
from stock_manager.api.services import _add_stock_to_restock, deduct_item_quantity
from stock_manager.api.text_search import contains_ci


DEFAULT_SYNONYM_MAP: dict[str, list[str]] = {
    # ── 蔬菜 / Vegetables ──
    "番茄": ["西红柿", "tomato", "tomatoes", "トマト"],
    "土豆": ["马铃薯", "洋芋", "potato", "potatoes", "じゃがいも", "ジャガイモ"],
    "胡萝卜": ["红萝卜", "carrot", "carrots", "にんじん", "ニンジン"],  # not 人参 (ginseng)
    "西兰花": ["青花菜", "broccoli", "ブロッコリー"],
    "菠菜": ["spinach", "ほうれん草", "ホウレンソウ"],
    "白菜": ["大白菜", "Chinese cabbage", "napa cabbage", "ハクサイ"],
    "卷心菜": ["圆白菜", "包菜", "甘蓝", "cabbage", "キャベツ"],
    "生菜": ["lettuce", "レタス"],
    "洋葱": ["onion", "玉ねぎ", "タマネギ"],
    "大蒜": ["蒜", "garlic", "ニンニク"],
    "生姜": ["姜", "ginger", "しょうが", "ショウガ"],
    "葱": ["小葱", "green onion", "scallion", "spring onion", "ねぎ", "ネギ"],
    "黄瓜": ["青瓜", "cucumber", "きゅうり", "キュウリ"],
    "茄子": ["eggplant", "aubergine", "なす", "ナス"],
    "玉米": ["corn", "sweet corn", "とうもろこし", "トウモロコシ"],
    "青椒": ["甜椒", "bell pepper", "ピーマン"],
    "辣椒": ["尖椒", "chili", "chilli", "唐辛子", "とうがらし"],
    "豆芽": ["绿豆芽", "黄豆芽", "bean sprout", "bean sprouts", "もやし"],
    "芹菜": ["celery", "セロリ"],
    "韭菜": ["leek", "garlic chives", "にら", "ニラ"],
    "南瓜": ["pumpkin", "かぼちゃ", "カボチャ"],
    "山药": ["山藥", "淮山", "Chinese yam", "长芋", "ながいも", "ナガイモ"],
    "莲藕": ["lotus root", "れんこん", "レンコン"],
    "豆腐": ["tofu", "とうふ"],
    "豆角": ["四季豆", "green bean", "green beans", "さやいんげん"],
    "秋葵": ["okra", "オクラ"],
    "芦笋": ["asparagus", "アスパラガス"],
    # ── 肉类 / Meats ──
    "猪肉": ["pork", "豚肉", "ぶたにく"],
    "牛肉": ["beef", "ぎゅうにく", "牛肉"],
    "鸡肉": ["chicken", "鶏肉", "とりにく"],
    "羊肉": ["lamb", "mutton", "ラム"],
    "排骨": ["ribs", "spareribs", "rib"],
    "鸡翅": ["chicken wing", "chicken wings", "手羽先", "てばさき"],
    "鸡胸肉": ["chicken breast", "鶏むね肉"],
    "鸡腿": ["chicken leg", "chicken drumstick", "鶏もも肉"],
    "培根": ["bacon", "ベーコン"],
    "火腿": ["ham", "ハム"],
    "香肠": ["sausage", "sausages", "ソーセージ"],
    "五花肉": ["pork belly"],
    "里脊肉": ["tenderloin", "loin"],
    "肉末": ["绞肉", "ground pork", "minced pork", "ひき肉"],
    # ── 蛋奶 / Eggs & Dairy ──
    "鸡蛋": ["鸡子", "egg", "eggs", "鶏卵", "たまご", "卵"],
    "牛奶": ["鲜奶", "milk", "牛乳"],
    "黄油": ["奶油", "butter", "バター"],
    "奶酪": ["芝士", "cheese", "起司", "チーズ"],
    "酸奶": ["yogurt", "ヨーグルト"],
    "淡奶油": ["鲜奶油", "heavy cream", "whipping cream", "生クリーム"],
    # ── 水产 / Seafood ──
    "虾": ["虾仁", "shrimp", "prawn", "prawns", "えび", "エビ"],
    "鱼": ["鱼片", "fish", "さかな", "サカナ"],
    "三文鱼": ["salmon", "サーモン"],
    "金枪鱼": ["tuna", "ツナ", "マグロ"],
    "带鱼": ["ribbonfish", "太刀魚"],
    "鱿鱼": ["squid", "いか", "イカ"],
    "蛤蜊": ["clams", "clam", "あさり"],
    # ── 主食 / Staples ──
    "大米": ["白米", "rice", "米", "ライス"],
    "糯米": ["glutinous rice", "もち米"],
    "面粉": ["中筋面粉", "低筋面粉", "高筋面粉", "flour", "小麦粉"],
    "面条": ["面", "挂面", "noodle", "noodles", "麺"],
    "意面": ["意大利面", "pasta", "spaghetti", "パスタ"],
    "面包": ["bread", "パン"],
    "馒头": ["steamed bun", "steamed bread", "饅頭"],
    "饺子": ["dumpling", "dumplings", "gyoza", "餃子"],
    "鸡蛋面": ["egg noodle", "egg noodles"],
    # ── 豆类 / Legumes ──
    "红豆": ["赤小豆", "red bean", "red beans", "あずき"],
    "绿豆": ["mung bean", "mung beans", "green gram"],
    "黄豆": ["大豆", "soybean", "soybeans", "大豆"],
    "花生": ["peanut", "peanuts", "落花生", "らっかせい"],
    # ── 干货 / Dry goods ──
    "木耳": ["黑木耳", "wood ear", "black fungus", "きくらげ"],
    "香菇": ["干香菇", "shiitake", "椎茸", "しいたけ"],
    "紫菜": ["海苔", "nori", "seaweed", "のり"],
    "海带": ["kelp", "昆布"],
    "银耳": ["白木耳", "snow fungus", "しろきくらげ"],
    # ── 水果 / Fruits ──
    "柠檬": ["lemon", "レモン"],
    "苹果": ["apple", "りんご", "リンゴ"],
    "香蕉": ["banana", "バナナ"],
    "草莓": ["strawberry", "strawberries", "いちご"],
    "葡萄": ["grapes", "grape", "ぶどう"],
    "橙子": ["orange", "橙", "オレンジ"],
    # ── 调味品 / Seasonings (basic) ──
    "盐": ["食盐", "salt", "食塩"],
    "糖": ["白糖", "sugar", "グラニュー糖"],
    "酱油": ["生抽", "老抽", "soy sauce", "醤油", "しょうゆ"],
    "醋": ["vinegar", "酢"],
    "料酒": ["cooking wine", "料理酒"],
    "淀粉": ["生粉", "cornstarch", "potato starch", "片栗粉"],
    "食用油": ["植物油", "菜籽油", "玉米油", "cooking oil", "oil", "サラダ油"],
    "芝麻油": ["麻油", "香油", "sesame oil", "ごま油"],
    "蚝油": ["oyster sauce", "オイスターソース"],
    "豆瓣酱": ["doubanjiang", "toban djan"],
    "番茄酱": ["ketchup", "tomato sauce", "ケチャップ"],
    "蜂蜜": ["honey", "はちみつ"],
    # ── 香料 / Spices ──
    "胡椒": ["白胡椒", "黑胡椒", "pepper", "black pepper", "white pepper", "こしょう"],
    "花椒": ["Sichuan pepper", "Szechuan pepper", "山椒"],
    "八角": ["star anise", "スターアニス"],
    "桂皮": ["肉桂", "cinnamon", "シナモン"],
    "香叶": ["bay leaf", "bay leaves", "ローリエ"],
}


SYNONYM_MAP: dict[str, list[str]] = dict(DEFAULT_SYNONYM_MAP)

def load_synonym_map(map_data: dict[str, list[str]]):
    """Load a synonym map for ingredient name normalization."""
    global SYNONYM_MAP
    SYNONYM_MAP = map_data


def _normalize_name(name: str) -> str:
    """Return normalized ingredient name using synonym map."""
    lower = name.strip().lower()
    for canonical, aliases in SYNONYM_MAP.items():
        if lower == canonical.lower():
            return canonical
        for alias in aliases:
            if lower == alias.lower():
                return canonical
    return name.strip()


def _build_normalized_set(names: list[str]) -> set[str]:
    """Build a set of normalized names."""
    return {_normalize_name(n) for n in names}


# ─── CRUD ────────────────────────────────────────────────────────


def get_recipes(
    db: Session,
    *,
    source_type: Optional[str] = None,
    category: Optional[str] = None,
    query: Optional[str] = None,
    favorite_only: bool = False,
    cookable_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[Recipe]:
    """Return recipes matching filters. Sorted by user relevance when query is provided.

    Filtering, sorting and paging all run in SQL, so only one page of
    recipes is loaded (#48). Sorting:
    - no query: favorites, then favorited-or-cooked, then user-created, then id;
    - query: highest search score first, then id. Score = user-created 100,
      favorite 80, cooked 60, title equal 50 / contains 40, an ingredient
      contains it 25, description contains it 10.
    """
    fav_ids = select(RecipeFavorite.recipe_id)
    cooked_ids = select(RecipeUsageHistory.recipe_id).where(
        RecipeUsageHistory.event_type == "cooked"
    )
    is_fav = Recipe.id.in_(fav_ids)
    is_cooked = Recipe.id.in_(cooked_ids)

    q = db.query(Recipe)

    if source_type:
        q = q.filter(Recipe.source_type == source_type)
    if category:
        q = q.filter(func.lower(Recipe.category) == category.lower())
    if query:
        q = q.filter(
            contains_ci(Recipe.title, query)
            | contains_ci(func.coalesce(Recipe.description, ""), query)
        )
    if favorite_only:
        q = q.filter(is_fav)
    if cookable_only:
        q = q.filter(meets_equipment_requirements())

    if not query:
        q = q.order_by(
            case((is_fav, 0), else_=1),
            case((is_fav | is_cooked, 0), else_=1),
            case((Recipe.is_user_created, 0), else_=1),
            Recipe.id,
        )
    else:
        q_lower = query.lower().strip()

        def contains(column):
            # Plain substring test (not LIKE), so % and _ are literal.
            return func.instr(func.lower(column), q_lower) > 0

        title = func.lower(Recipe.title)
        ingredient_hit = (
            select(RecipeIngredient.id)
            .where(
                RecipeIngredient.recipe_id == Recipe.id,
                contains(RecipeIngredient.ingredient_name)
                | contains(func.coalesce(RecipeIngredient.normalized_name, "")),
            )
            .exists()
        )
        # instr(x, '') is 1, so an empty description must be excluded explicitly.
        has_description = func.coalesce(Recipe.description, "") != ""
        score = (
            case((Recipe.is_user_created, 100), else_=0)
            + case((is_fav, 80), else_=0)
            + case((is_cooked, 60), else_=0)
            + case((title == q_lower, 50), (contains(Recipe.title), 40), else_=0)
            + case((ingredient_hit, 25), else_=0)
            + case((has_description & contains(Recipe.description), 10), else_=0)
        )
        q = q.order_by(score.desc(), Recipe.id)

    return q.offset(offset).limit(limit).all()


def get_recipe_flags(db: Session, recipe_ids: list[int]) -> tuple[set[int], set[int]]:
    """(favorite ids, cooked ids) among `recipe_ids`, in two queries (#48)."""
    if not recipe_ids:
        return set(), set()
    favorites = {
        row[0] for row in db.query(RecipeFavorite.recipe_id)
        .filter(RecipeFavorite.recipe_id.in_(recipe_ids))
    }
    cooked = {
        row[0] for row in db.query(RecipeUsageHistory.recipe_id)
        .filter(
            RecipeUsageHistory.recipe_id.in_(recipe_ids),
            RecipeUsageHistory.event_type == "cooked",
        )
        .distinct()
    }
    return favorites, cooked


def get_recipe(db: Session, recipe_id: int) -> Optional[Recipe]:
    """Return one recipe by id."""
    return db.query(Recipe).filter(Recipe.id == recipe_id).first()


def recipe_draft_hash(data: RecipeDraft | RecipeCreate) -> str:
    """Hash the full draft content apart from the user-selected category."""
    fields = RecipeDraft.model_fields.keys() - {"category"}
    content = data.model_dump(mode="json", include=fields)
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def is_user_editable(recipe: Recipe) -> bool:
    return recipe.source_type in ("user", "ai_saved")


def create_recipe(db: Session, data: RecipeCreate, source_type: str = "user") -> Recipe:
    """Create a new recipe (user-created or AI-saved)."""
    recipe = Recipe(
        source_type=source_type,
        source_name="User" if source_type == "user" else "AI",
        title=data.title,
        category=data.category,
        description=data.description,
        difficulty=data.difficulty,
        servings=data.servings,
        cook_time_minutes=data.cook_time_minutes,
        raw_markdown=data.raw_markdown,
        is_user_created=source_type in ("user", "ai_saved"),
    )
    db.add(recipe)
    db.flush()

    for ing in data.ingredients:
        normalized = _normalize_name(ing.ingredient_name)
        db.add(RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_name=ing.ingredient_name,
            normalized_name=normalized or ing.ingredient_name,
            quantity=ing.quantity,
            unit=ing.unit,
            is_optional=ing.is_optional,
            is_seasoning=ing.is_seasoning,
            sort_order=ing.sort_order,
        ))

    for step in data.steps:
        db.add(RecipeStep(
            recipe_id=recipe.id,
            step_number=step.step_number,
            instruction=step.instruction,
        ))

    if data.equipment:
        replace_recipe_equipment(db, recipe.id, data.equipment)
    db.commit()
    db.refresh(recipe)
    return recipe


@media.file_transaction()
def update_recipe(db: Session, recipe_id: int, data: RecipeUpdate) -> Optional[Recipe]:
    """Update an editable recipe and mark edited AI drafts as user recipes."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).with_for_update().first()
    if recipe is None:
        return None
    if not is_user_editable(recipe):
        return None  # cannot edit HowToCook recipes directly

    update_data = data.model_dump(exclude_unset=True, exclude={"ingredients", "steps", "equipment"})
    for key, value in update_data.items():
        setattr(recipe, key, value)

    if data.ingredients is not None:
        db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe_id).delete()
        for ing in data.ingredients:
            normalized = _normalize_name(ing.ingredient_name)
            db.add(RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_name=ing.ingredient_name,
                normalized_name=normalized or ing.ingredient_name,
                quantity=ing.quantity,
                unit=ing.unit,
                is_optional=ing.is_optional,
                is_seasoning=ing.is_seasoning,
                sort_order=ing.sort_order,
            ))

    if data.steps is not None:
        move_orphaned_step_photos(db, recipe_id, {step.step_number for step in data.steps})
        db.query(RecipeStep).filter(RecipeStep.recipe_id == recipe_id).delete()
        for step in data.steps:
            db.add(RecipeStep(
                recipe_id=recipe.id,
                step_number=step.step_number,
                instruction=step.instruction,
            ))

    if data.equipment is not None:
        replace_recipe_equipment(db, recipe_id, data.equipment)

    if recipe.source_type == "ai_saved" and (
        update_data or data.ingredients is not None or data.steps is not None or data.equipment is not None
    ):
        recipe.source_type = "user"
        recipe.source_name = "User"
        recipe.is_user_created = True

    db.commit()
    db.refresh(recipe)
    return recipe


@media.file_transaction()
def delete_recipe(db: Session, recipe_id: int) -> bool:
    """Delete a user-created recipe."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).with_for_update().first()
    if recipe is None:
        return False
    if not is_user_editable(recipe):
        return False
    # Remove rows that reference this recipe so the delete does not violate
    # foreign keys (issue #43). Forks are kept: the `forks` backref sets their
    # base_recipe_id to NULL when the recipe is deleted.
    delete_recipe_equipment(db, [recipe_id])
    hashes = delete_recipe_photos(db, [recipe_id])
    db.query(RecipeFavorite).filter(RecipeFavorite.recipe_id == recipe_id).delete(
        synchronize_session=False
    )
    db.query(RecipeUsageHistory).filter(
        RecipeUsageHistory.recipe_id == recipe_id
    ).delete(synchronize_session=False)
    db.delete(recipe)
    db.commit()
    for photo_hash in hashes:
        media.delete_files_if_unused(db, photo_hash)
    return True


@media.file_transaction()
def fork_recipe(db: Session, recipe_id: int) -> Optional[Recipe]:
    """Fork a recipe into a user-editable copy."""
    original = db.query(Recipe).filter(Recipe.id == recipe_id).with_for_update().first()
    if original is None:
        return None
    if is_user_editable(original):
        return original  # already user-owned

    recipe = Recipe(
        source_type="user",
        source_name="User",
        source_url=original.source_url,
        title=original.title,
        # Forks drop source_path, so store the dish category resolved from it.
        category=recipe_dish_category(original),
        description=original.description,
        difficulty=original.difficulty,
        servings=original.servings,
        cook_time_minutes=original.cook_time_minutes,
        raw_markdown=original.raw_markdown,
        is_user_created=True,
        base_recipe_id=original.id,
    )
    db.add(recipe)
    db.flush()

    for ing in original.ingredients:
        db.add(RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_name=ing.ingredient_name,
            normalized_name=ing.normalized_name,
            quantity=ing.quantity,
            unit=ing.unit,
            is_optional=ing.is_optional,
            is_seasoning=ing.is_seasoning,
            sort_order=ing.sort_order,
        ))

    for step in original.steps:
        db.add(RecipeStep(
            recipe_id=recipe.id,
            step_number=step.step_number,
            instruction=step.instruction,
        ))

    equipment = load_recipe_equipment(db, [original.id]).get(original.id, [])
    if equipment:
        replace_recipe_equipment(db, recipe.id, equipment)

    photos = db.query(RecipePhoto).filter(
        RecipePhoto.recipe_id == original.id, RecipePhoto.hidden.is_(False),
        RecipePhoto.usage_history_id.is_(None),
    ).all()
    for photo in photos:
        db.add(RecipePhoto(
            recipe_id=recipe.id, origin=photo.origin, step_number=photo.step_number,
            position=photo.position, caption=photo.caption, is_cover=photo.is_cover,
            sha256=photo.sha256, width=photo.width, height=photo.height, bytes=photo.bytes,
            created_at=photo.created_at,
        ))

    db.commit()
    db.refresh(recipe)
    return recipe


# ─── Favorites ────────────────────────────────────────────────────


def add_favorite(db: Session, recipe_id: int) -> RecipeFavorite | None:
    """Return the favorite, creating it and its history entry when needed."""
    if db.get(Recipe, recipe_id) is None:
        return None
    favorites = db.query(RecipeFavorite).filter(RecipeFavorite.recipe_id == recipe_id)
    existing = favorites.first()
    if existing is not None:
        return existing

    favorite = RecipeFavorite(recipe_id=recipe_id)
    db.add(favorite)
    db.add(RecipeUsageHistory(recipe_id=recipe_id, event_type="favorited"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = favorites.first()
        if existing is None:
            raise
        return existing
    return favorite


def remove_favorite(db: Session, recipe_id: int) -> bool:
    """Remove a recipe from favorites."""
    fav = db.query(RecipeFavorite).filter(
        RecipeFavorite.recipe_id == recipe_id
    ).first()
    if fav is None:
        return False
    db.delete(fav)
    db.commit()
    return True


def is_favorite(db: Session, recipe_id: int) -> bool:
    """Check if a recipe is favorited."""
    return db.query(RecipeFavorite).filter(
        RecipeFavorite.recipe_id == recipe_id
    ).first() is not None


def has_been_cooked(db: Session, recipe_id: int) -> bool:
    """Check if a recipe has been cooked before."""
    return db.query(RecipeUsageHistory).filter(
        RecipeUsageHistory.recipe_id == recipe_id,
        RecipeUsageHistory.event_type == "cooked",
    ).first() is not None


# ─── Usage history ──────────────────────────────────────────────


def record_recommendation(db: Session, recipe_id: int):
    """Record that a recipe was recommended."""
    db.add(RecipeUsageHistory(recipe_id=recipe_id, event_type="recommended"))
    db.commit()


def record_recommendations(db: Session, recipe_ids: list[int]):
    """Record that multiple recipes were recommended (batch)."""
    for recipe_id in recipe_ids:
        db.add(RecipeUsageHistory(recipe_id=recipe_id, event_type="recommended"))
    db.commit()


# ─── Rule-based recommendations ─────────────────────────────────

# Recipes cooked within this many days are down-weighted (#46).
RECENT_COOKED_DAYS = 7

# Today Recommendations scenes -> HowToCook `dishes/<dir>` names (#46).
# Verified against Anduin2017/HowToCook `dishes/` on 2026-11-09:
# aquatic, breakfast, condiment, dessert, drink, meat_dish, semi-finished,
# soup, staple, template, vegetable_dish.
RECOMMENDATION_SCENES = ("all", "breakfast", "meal", "dessert_drink")
SCENE_DISH_CATEGORIES = {
    "breakfast": {"breakfast"},
    "meal": {"meat_dish", "vegetable_dish", "aquatic", "soup", "staple", "semi-finished"},
    "dessert_drink": {"dessert", "drink"},
}
# Directories that exist but belong to no scene (shown only under "all").
_UNSCENED_DISH_CATEGORIES = {"condiment"}
# dishes/ directories that do not hold recipes.
_NON_RECIPE_DISH_DIRS = {"template"}
_KNOWN_DISH_CATEGORIES = set().union(*SCENE_DISH_CATEGORIES.values()) | _UNSCENED_DISH_CATEGORIES
# Free-text categories users may type for their own recipes.
_CATEGORY_ALIASES = {
    "早餐": "breakfast", "早饭": "breakfast",
    "荤菜": "meat_dish", "素菜": "vegetable_dish", "水产": "aquatic",
    "汤": "soup", "汤羹": "soup", "主食": "staple", "半成品": "semi-finished",
    "甜品": "dessert", "甜点": "dessert", "饮品": "drink", "饮料": "drink",
    "调料": "condiment", "酱料": "condiment",
}


def recipe_dish_category(recipe: Recipe) -> Optional[str]:
    """Return the HowToCook-style dish category of a recipe, if known.

    HowToCook recipes use the first directory under `dishes/` in
    `source_path` (some recipes are nested one level deeper, e.g.
    `dishes/meat_dish/口水鸡/口水鸡.md`, so the folder right above the file is
    not reliable). Other recipes use `category`, with Chinese aliases.
    """
    parts = (recipe.source_path or "").replace("\\", "/").split("/")
    if len(parts) >= 3 and parts[0] == "dishes":
        return parts[1]
    raw = (recipe.category or "").strip()
    if not raw:
        return None
    return _CATEGORY_ALIASES.get(raw, raw.lower())


def is_recommendable(recipe: Recipe) -> bool:
    """False for HowToCook rows that are not dishes (tips/, .github/, template),
    which older importers stored as recipes."""
    if recipe.source_type != "howtocook":
        return True
    parts = (recipe.source_path or "").replace("\\", "/").split("/")
    return len(parts) >= 3 and parts[0] == "dishes" and parts[1] not in _NON_RECIPE_DISH_DIRS


def recipe_matches_scene(recipe: Recipe, scene: str) -> bool:
    """True if the recipe belongs in the given Today Recommendations scene.

    Nothing is excluded for good: every recipe appears under "all". The
    user's own recipes (user-created / AI-saved) with no or an unknown
    category count as a meal.
    """
    if scene == "all":
        return True
    category = recipe_dish_category(recipe)
    if category in SCENE_DISH_CATEGORIES[scene]:
        return True
    return (
        scene == "meal"
        and recipe.source_type != "howtocook"
        and category not in _KNOWN_DISH_CATEGORIES
    )



def _match_recipe_ingredients(
    ingredients: list[RecipeIngredient], names: set[str], normalized_names: set[str],
) -> tuple[list[RecipeIngredient], list[RecipeIngredient]]:
    """Separate matched ingredients from required ingredients missing from stock."""
    matched, missing = [], []
    for ingredient in ingredients:
        name = ingredient.ingredient_name
        if name.strip().lower() in names or _normalize_name(name).lower() in normalized_names:
            matched.append(ingredient)
        elif not (ingredient.is_seasoning or ingredient.is_optional):
            missing.append(ingredient)
    return matched, missing


def _recommendation_candidates(db: Session, inventory_names: set[str], normalized_names: set[str]):
    required = (
        select(RecipeIngredient.recipe_id, func.count().label("total"))
        .where(RecipeIngredient.is_seasoning.is_(False), RecipeIngredient.is_optional.is_(False))
        .group_by(RecipeIngredient.recipe_id)
        .subquery()
    )
    short_recipes = (
        select(Recipe.id)
        .outerjoin(required, required.c.recipe_id == Recipe.id)
        .where(required.c.total.is_(None) | (required.c.total <= 1))
    )
    sources = [select(RecipeFavorite.recipe_id)]
    if inventory_names:
        # Expand current aliases back to raw names. Imported rows may lack a
        # stored normalized name, and older rows may use a previous synonym map.
        names = set(inventory_names)
        seen = set()
        for canonical, aliases in SYNONYM_MAP.items():
            raw_names = {name.lower() for name in (canonical, *aliases)}
            if canonical.lower() in normalized_names:
                names.update(raw_names - seen)
            # Like _normalize_name, take the first mapping for a shared alias.
            seen.update(raw_names)

        ingredient_name = RecipeIngredient.ingredient_name
        if db.get_bind().dialect.name == "sqlite":
            # SQLite's built-in lower() handles ASCII only.
            db.connection().connection.driver_connection.create_function(
                "recipe_name_key", 1, lambda name: name.strip().lower(), deterministic=True,
            )
            name_key = func.recipe_name_key(ingredient_name)
        else:
            # Trim surrounding whitespace before applying the database's Unicode lower().
            name_key = func.lower(func.regexp_replace(ingredient_name, r"^[[:space:]]+|[[:space:]]+$", ""))
        sources.append(select(RecipeIngredient.recipe_id).where(name_key.in_(sorted(names))))

    return short_recipes.union(*sources).cte("recommendation_candidates")


def get_recommendations(
    db: Session,
    limit: int = 10,
    scene: str = "all",
) -> list[dict]:
    """Generate rule-based recipe recommendations from inventory.

    Refresh stored inventory statuses before scoring with the current
    inventory and cooking history. The SQL candidates are the union of recipes
    with a matching stock ingredient (including optional items or seasoning),
    favorites, and recipes with at most one required ingredient. Favorites can
    overcome missing ingredients with their bonus. Other unmatched recipes
    with two or more required ingredients always score below zero. Revisit
    these candidate rules when changing the scoring rules. Once household
    equipment is configured, SQL also excludes any recipe with an equipment
    group for which no option is owned.

    Scoring:
    - Matched ingredient: +10 (conditional category: +6)
    - Expiring ingredient: +40 (conditional category: +20)
    - Missing ingredient: -5
    - Favorite recipe: +15
    - Cooked in the last RECENT_COOKED_DAYS days: -10
    - Not cooked in the last RECENT_COOKED_DAYS days: +5
    """
    if scene not in RECOMMENDATION_SCENES:
        raise ValueError(f"Unknown scene '{scene}'")

    # Gather active inventory - only recipe eligible
    from stock_manager.api.category_services import RECIPE_USAGE_ALWAYS, query_recipe_candidate_items
    items = query_recipe_candidate_items(db).all()

    inventory_names = set()
    expiring_names = set()
    always_names = set()
    for item in items:
        item_lower = item.name.strip().lower()
        inventory_names.add(item_lower)
        if item.status == "expiring soon":
            expiring_names.add(item_lower)
        if item.category.recipe_usage == RECIPE_USAGE_ALWAYS:
            always_names.add(item_lower)

    # Also add normalized (synonym-resolved) names, lower-cased for comparison
    inv_norm = {n.lower() for n in _build_normalized_set(list(inventory_names))}
    exp_norm = {n.lower() for n in _build_normalized_set(list(expiring_names))}
    always_norm = {n.lower() for n in _build_normalized_set(list(always_names))}

    def _is_always(ingredient_name: str) -> bool:
        """True if the matched ingredient comes from an always-usage item.

        Checks both the raw name and its synonym-resolved form, so an
        always item named e.g. 西红柿 is not down-weighted when matched to
        a recipe ingredient named 番茄.
        """
        raw = ingredient_name.strip().lower()
        return raw in always_names or _normalize_name(ingredient_name).lower() in always_norm

    candidates = _recommendation_candidates(db, inventory_names, inv_norm)
    recipes = [
        recipe for recipe in db.query(Recipe)
        .join(candidates, candidates.c.id == Recipe.id)
        .filter(meets_equipment_requirements())
        .order_by(Recipe.id)
        if is_recommendable(recipe) and recipe_matches_scene(recipe, scene)
    ]

    # Recipes actually cooked recently (written by POST /recipes/{id}/cook)
    cooked_since = utcnow() - timedelta(days=RECENT_COOKED_DAYS)
    recent_cooked_ids = set(
        row[0] for row in db.query(RecipeUsageHistory.recipe_id).filter(
            RecipeUsageHistory.event_type == "cooked",
            RecipeUsageHistory.created_at >= cooked_since,
        ).all()
    )

    # Get favorite IDs
    fav_ids = set(
        row[0] for row in db.query(RecipeFavorite.recipe_id).all()
    )

    # All candidate ingredients in one query instead of one per recipe (#48).
    ingredients_by_recipe: dict[int, list[RecipeIngredient]] = {r.id: [] for r in recipes}
    if recipes:
        for ing in (
            db.query(RecipeIngredient)
            .filter(RecipeIngredient.recipe_id.in_(list(ingredients_by_recipe)))
            .order_by(RecipeIngredient.id)
        ):
            ingredients_by_recipe[ing.recipe_id].append(ing)

    scored: list[dict] = []

    for recipe in recipes:
        ingredients = ingredients_by_recipe[recipe.id]

        matched_rows, missing_rows = _match_recipe_ingredients(
            ingredients, inventory_names, inv_norm,
        )
        matched = [ingredient.ingredient_name for ingredient in matched_rows]
        missing = [ingredient.ingredient_name for ingredient in missing_rows]
        expiring_used = [
            name for name in matched
            if name.strip().lower() in expiring_names or _normalize_name(name).lower() in exp_norm
        ]

        score = len(matched) * 10 + len(expiring_used) * 40
        # Reduce score for conditional (non-always) matched items
        for m in matched:
            if not _is_always(m):
                score -= 4  # +10 becomes +6 for conditional
        for e in expiring_used:
            if not _is_always(e):
                score -= 20  # +40 becomes +20 for conditional
        score -= len(missing) * 5
        if recipe.id in fav_ids:
            score += 15
        if recipe.id in recent_cooked_ids:
            score -= 10  # cooked recently: give other dishes a turn
        else:
            score += 5  # not cooked recently

        if score < 0:
            continue

        scored.append({
            "recipe_id": recipe.id,
            "title": recipe.title,
            "score": round(score, 1),
            "matched_inventory_items": matched,
            "expiring_inventory_items": expiring_used,
            "missing_ingredients": missing,
            "is_favorite": recipe.id in fav_ids,
            "is_new_suggestion": recipe.id not in recent_cooked_ids,
            "source_type": recipe.source_type,
        })


    # Highest score first; ties keep recipe id order, so results are stable.
    scored.sort(key=lambda x: (-x["score"], x["recipe_id"]))
    return scored[:limit]


def _restock_recipe_ingredient(db: Session, ingredient: RecipeIngredient) -> RestockItem:
    quantity, parsed_unit = parse_quantity(ingredient.quantity, ingredient.unit)
    stock_quantity = None
    if quantity is not None and isfinite(quantity) and quantity > 0:
        try:
            stock_quantity = quantize_stock_quantity(quantity) or None
        except ValueError:
            pass  # Keep the gap and let the user choose a quantity that fits in stock.
    entry = RestockItem(
        name=ingredient.ingredient_name,
        quantity_value=stock_quantity,
        quantity_unit=ingredient.unit or parsed_unit,
        category_id=None,
        source_item_id=None,
        status="pending",
        notes=None,
    )
    db.add(entry)
    return entry


def add_recipe_gaps_to_restock(db: Session, recipe_id: int) -> dict | None:
    """Queue missing required ingredients using the recommendation match rules."""
    from stock_manager.api.category_services import query_recipe_candidate_items

    recipe = get_recipe(db, recipe_id)
    if recipe is None:
        return None

    # This query may commit a status refresh. Finish it before staging any restock rows.
    inventory = query_recipe_candidate_items(db).all()
    names = {item.name.strip().lower() for item in inventory}
    normalized_names = {name.lower() for name in _build_normalized_set(list(names))}
    _, missing = _match_recipe_ingredients(recipe.ingredients, names, normalized_names)

    created, skipped = [], []
    if not missing:
        return {"created": created, "skipped": skipped}

    try:
        pending = (
            db.query(RestockItem.name).filter(RestockItem.status == "pending").with_for_update()
        )
        pending_names = {_normalize_name(name).lower() for (name,) in pending}
        for ingredient in missing:
            name = _normalize_name(ingredient.ingredient_name).lower()
            if name in pending_names:
                skipped.append({"name": ingredient.ingredient_name, "reason": "already_pending"})
                continue
            created.append(_restock_recipe_ingredient(db, ingredient))
            pending_names.add(name)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"created": created, "skipped": skipped}


# ─── Consume Preview and Cook ─────────────────────────────────────


def _recipe_quantity_text(quantity: Optional[str], unit: Optional[str]) -> Optional[str]:
    """The recipe amount as written, e.g. "500克" or "2 个"; None if absent."""
    q = (quantity or "").strip()
    u = (unit or "").strip()
    if not q:
        return None
    if u and not q.endswith(u):
        return f"{q} {u}"
    return q


def _name_keys(name: Optional[str]) -> set[str]:
    """Lower-cased forms a name matches by: as written and its synonym-map
    canonical name. Empty for a missing name."""
    text = (name or "").strip()
    if not text:
        return set()
    return {text.lower(), _normalize_name(text).lower()}


def get_consume_preview(db: Session, recipe_id: int) -> Optional[dict]:
    """Preview which inventory items would be consumed for a recipe.
    Refreshes stored statuses without consuming inventory.
    """
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        return None

    ingredients = db.query(RecipeIngredient).filter(
        RecipeIngredient.recipe_id == recipe_id,
    ).order_by(RecipeIngredient.id)

    from stock_manager.api.category_services import query_recipe_candidate_items

    batches = sorted(query_recipe_candidate_items(db).all(), key=lambda item: (
        item.status != "expiring soon", item.current_expiration_date, item.id,
    ))
    available = {item.id: _name_keys(item.name) for item in batches}
    suggestions, unmatched = [], []

    for ingredient in ingredients:
        if ingredient.is_seasoning or ingredient.is_optional:
            continue
        names = _name_keys(ingredient.ingredient_name)
        matches = [item for item in batches if item.id in available and names & available[item.id]]
        if not matches:
            unmatched.append(ingredient.ingredient_name)
            continue

        number, recipe_unit = parse_quantity(ingredient.quantity, ingredient.unit)
        compatible = [item for item in matches if same_unit(recipe_unit, item.quantity_unit)]
        allocations = []
        first = matches[0]
        needs_user_input = True
        remaining = round_stock_quantity(Decimal(str(number))) if (
            number is not None and isfinite(number) and number > 0
        ) else Decimal(0)
        if remaining and compatible:
            first = compatible[0]
            for item in compatible:
                quantity = min(remaining, item.quantity_value)
                allocations.append({"item_id": item.id, "quantity": float(quantity)})
                del available[item.id]
                remaining -= quantity
                if not remaining:
                    break
            needs_user_input = remaining > 0
        else:
            del available[first.id]

        suggestions.append({
            "ingredient_name": ingredient.ingredient_name,
            "item_id": first.id,
            "item_name": first.name,
            "available_quantity": first.quantity_value,
            "available_unit": first.quantity_unit,
            "recipe_quantity": _recipe_quantity_text(ingredient.quantity, ingredient.unit),
            "suggested_quantity": allocations[0]["quantity"] if allocations else None,
            "unit": first.quantity_unit,
            "allocations": allocations,
            "needs_user_input": needs_user_input,
            "status": first.status,
            "current_expiration_date": first.current_expiration_date,
            "confidence": "high" if allocations else "low",
        })

    return {
        "recipe_id": recipe.id,
        "title": recipe.title,
        "suggestions": suggestions,
        "unmatched_ingredients": unmatched,
    }


def _cook_line(db: Session, entry: dict, *, add_depleted_to_restock: bool) -> tuple[dict, dict | None]:
    item_id = entry["item_id"]
    quantity = quantize_stock_quantity(entry["quantity"])
    item, deducted = deduct_item_quantity(db, item_id, quantity, recipe_only=True)
    line = {"item_id": item_id, "ingredient_name": entry.get("ingredient_name", "")}
    if deducted:
        if add_depleted_to_restock and item.quantity_value == 0:
            _add_stock_to_restock(db, item, quantity, source_item_id=item.id)
        return (
            {**line, "result": "consumed", "consumed_quantity": float(quantity)},
            {
                "item_id": item_id,
                "item_name": item.name,
                "consumed_quantity": float(quantity),
                "remaining_quantity": float(item.quantity_value),
                "status": item.status,
            },
        )
    if item is None:
        return {**line, "result": "skipped", "reason": "item_not_found"}, None
    if item.category.recipe_usage == RECIPE_USAGE_NEVER:
        return {**line, "result": "skipped", "reason": "not_recipe_usable"}, None

    return {
        **line, "result": "insufficient", "requested": float(quantity),
        "available": float(item.quantity_value),
    }, None


def cook_recipe_and_consume(
    db: Session,
    recipe_id: int,
    consume_items: list[dict],
    notes: Optional[str] = None,
    *,
    add_depleted_to_restock: bool = False,
) -> Optional[dict]:
    """Record a cook and its successful deductions in a single transaction."""
    entries = {}
    for entry in consume_items:
        item_id = entry["item_id"]
        if item_id in entries:
            raise APIError(422, "duplicate_item", "Duplicate stock item", item_id=item_id)
        entries[item_id] = entry

    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        return None

    try:
        # Acquire stock locks in the same order across requests.
        outcomes = {
            item_id: _cook_line(db, entries[item_id], add_depleted_to_restock=add_depleted_to_restock)
            for item_id in sorted(entries)
        }
        lines = []
        consumed = []
        for item_id in entries:
            line, deduction = outcomes[item_id]
            lines.append(line)
            if deduction is not None:
                consumed.append(deduction)
        if lines and not consumed:
            raise APIError(
                409, "cook_nothing_consumed", "No stock was consumed", lines=lines,
            )

        history = RecipeUsageHistory(
            recipe_id=recipe_id,
            event_type="cooked",
            metadata_json=json.dumps({"consumed_items": consumed, "notes": notes}, ensure_ascii=False),
        )
        db.add(history)
        db.flush()
        result = {
            "recipe_id": recipe_id,
            "usage_history_id": history.id,
            "title": recipe.title,
            "consumed_items": consumed,
            "notes": notes,
            "lines": lines,
        }
        db.commit()
    except Exception:
        db.rollback()
        raise

    return result

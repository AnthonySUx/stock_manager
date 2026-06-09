"""Business logic for recipe features."""
import json
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from stock_manager.api.models import (
    Recipe,
    RecipeFavorite,
    RecipeIngredient,
    RecipeStep,
    RecipeUsageHistory,
    AIRecipeRecommendation,
    Item,
)
from stock_manager.api.recipe_schemas import RecipeCreate, RecipeUpdate


DEFAULT_SYNONYM_MAP: dict[str, list[str]] = {
    # ── 蔬菜 / Vegetables ──
    "番茄": ["西红柿", "tomato", "tomatoes", "トマト"],
    "土豆": ["马铃薯", "洋芋", "potato", "potatoes", "じゃがいも", "ジャガイモ"],
    "胡萝卜": ["红萝卜", "carrot", "carrots", "人参", "にんじん", "ニンジン"],
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
    limit: int = 20,
    offset: int = 0,
) -> list[Recipe]:
    """Return recipes matching filters. Sorted by user relevance when query is provided."""
    from stock_manager.api.models import RecipeUsageHistory, RecipeFavorite

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
        q = q.filter(Recipe.id.in_(
            db.query(RecipeFavorite.recipe_id)
        ))

    results = q.all()

    if not query:
        # Default sorting: favorites and user-created first
        fav_ids = set(r[0] for r in db.query(RecipeFavorite.recipe_id).all())
        cooked_ids = set(r[0] for r in db.query(RecipeUsageHistory.recipe_id).filter(
            RecipeUsageHistory.event_type == "cooked"
        ).all())
        results.sort(key=lambda r: (
            r.id not in fav_ids,
            r.id not in (fav_ids | cooked_ids),
            not r.is_user_created,
            r.id,
        ))
    else:
        # Smart search scoring for queries
        q_lower = query.lower().strip()
        fav_ids = set(r[0] for r in db.query(RecipeFavorite.recipe_id).all())
        cooked_ids = set(r[0] for r in db.query(RecipeUsageHistory.recipe_id).filter(
            RecipeUsageHistory.event_type == "cooked"
        ).all())

        def search_score(recipe: Recipe) -> int:
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
            if recipe.ingredients:
                for ing in recipe.ingredients:
                    if q_lower in ing.ingredient_name.lower() or (ing.normalized_name and q_lower in ing.normalized_name.lower()):
                        score += 25
                        break
            if recipe.description and q_lower in recipe.description.lower():
                score += 10
            return score

        results.sort(key=search_score, reverse=True)

    return results[offset:offset+limit]


def get_recipe(db: Session, recipe_id: int) -> Optional[Recipe]:
    """Return one recipe by id."""
    return db.query(Recipe).filter(Recipe.id == recipe_id).first()


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
        is_user_created=(source_type == "user"),
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

    db.commit()
    db.refresh(recipe)
    return recipe


def update_recipe(db: Session, recipe_id: int, data: RecipeUpdate) -> Optional[Recipe]:
    """Update a user-created or AI-saved recipe."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        return None
    if recipe.source_type not in ("user", "ai_saved"):
        return None  # cannot edit HowToCook recipes directly

    update_data = data.model_dump(exclude_unset=True, exclude={"ingredients", "steps"})
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
        db.query(RecipeStep).filter(RecipeStep.recipe_id == recipe_id).delete()
        for step in data.steps:
            db.add(RecipeStep(
                recipe_id=recipe.id,
                step_number=step.step_number,
                instruction=step.instruction,
            ))

    db.commit()
    db.refresh(recipe)
    return recipe


def delete_recipe(db: Session, recipe_id: int) -> bool:
    """Delete a user-created or AI-saved recipe."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        return False
    if recipe.source_type not in ("user", "ai_saved"):
        return False
    db.delete(recipe)
    db.commit()
    return True


def fork_recipe(db: Session, recipe_id: int) -> Optional[Recipe]:
    """Fork a recipe into a user-editable copy."""
    original = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if original is None:
        return None
    if original.source_type == "user" and original.is_user_created:
        return original  # already user-owned

    recipe = Recipe(
        source_type="user",
        source_name="User",
        source_url=original.source_url,
        title=original.title,
        category=original.category,
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

    db.commit()
    db.refresh(recipe)
    return recipe


# ─── Favorites ────────────────────────────────────────────────────


def add_favorite(db: Session, recipe_id: int) -> bool:
    """Add a recipe to favorites."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        return False
    existing = db.query(RecipeFavorite).filter(
        RecipeFavorite.recipe_id == recipe_id
    ).first()
    if existing:
        return True  # already favorited
    db.add(RecipeFavorite(recipe_id=recipe_id))
    db.add(RecipeUsageHistory(recipe_id=recipe_id, event_type="favorited"))
    db.commit()
    return True


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


def get_recommendations(
    db: Session,
    limit: int = 10,
) -> list[dict]:
    """Generate rule-based recipe recommendations from inventory.

    Scoring:
    - Matched ingredient: +10
    - Expiring ingredient: +40
    - Missing ingredient: -5
    - Favorite recipe: +15
    - Recently recommended: -10 (diversity boost)
    - Not recommended in history: +5 (novelty)
    """
    today = date.today()
    warning_days = 2

    # Gather active inventory
    items = db.query(Item).filter(
        Item.status.in_(["active", "expiring soon"])
    ).all()

    inventory_names = set()
    expiring_names = set()
    for item in items:
        item_lower = item.name.strip().lower()
        inventory_names.add(item_lower)
        if item.status == "expiring soon":
            expiring_names.add(item_lower)

    # Also add normalized names
    inv_norm = _build_normalized_set(list(inventory_names))
    exp_norm = _build_normalized_set(list(expiring_names))

    # Get all recipes with their ingredients
    recipes = db.query(Recipe).all()

    # Get recent recommendations (last 7 days)
    seven_days_ago = today - timedelta(days=7)
    recent_rec_ids = set(
        row[0] for row in db.query(RecipeUsageHistory.recipe_id).filter(
            RecipeUsageHistory.event_type == "recommended",
            RecipeUsageHistory.created_at >= seven_days_ago,
        ).all()
    )

    # Get favorite IDs
    fav_ids = set(
        row[0] for row in db.query(RecipeFavorite.recipe_id).all()
    )

    scored: list[dict] = []

    for recipe in recipes:
        ingredients = db.query(RecipeIngredient).filter(
            RecipeIngredient.recipe_id == recipe.id
        ).all()

        matched = []
        expiring_used = []
        missing = []
        missing_main = []

        for ing in ingredients:
            ing_norm = _normalize_name(ing.ingredient_name).lower()
            ing_raw = ing.ingredient_name.strip().lower()

            if ing_norm in inv_norm or ing_raw in inventory_names:
                matched.append(ing.ingredient_name)
                if ing_norm in exp_norm or ing_raw in expiring_names:
                    expiring_used.append(ing.ingredient_name)
            elif ing.is_seasoning:
                pass  # skip seasoning for missing detection
            elif ing.is_optional:
                pass  # optional ingredients can be omitted
            else:
                missing.append(ing.ingredient_name)

        score = len(matched) * 10 + len(expiring_used) * 40
        score -= len(missing) * 5
        if recipe.id in fav_ids:
            score += 15
        if recipe.id in recent_rec_ids:
            score -= 10
        else:
            score += 5  # novelty bonus

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
            "is_new_suggestion": recipe.id not in recent_rec_ids,
            "source_type": recipe.source_type,
        })


    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


# ─── Consume Preview and Cook ─────────────────────────────────────


def get_consume_preview(db: Session, recipe_id: int) -> Optional[dict]:
    """Preview which inventory items would be consumed for a recipe.
    Returns suggestions without modifying any data.
    """
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        return None

    ingredients = db.query(RecipeIngredient).filter(
        RecipeIngredient.recipe_id == recipe_id
    ).all()

    # Get active inventory
    items = db.query(Item).filter(
        Item.status.in_(["active", "expiring soon"])
    ).all()

    suggestions = []
    unmatched = []

    for ing in ingredients:
        if ing.is_seasoning or ing.is_optional:
            continue
        ing_lower = ing.ingredient_name.strip().lower()
        norm_lower = (ing.normalized_name or "").strip().lower()

        # Find best matching inventory item
        best_match = None
        for item in items:
            item_lower = item.name.strip().lower()
            if item_lower == ing_lower or item_lower == norm_lower or norm_lower == item_lower:
                if best_match is None:
                    best_match = item
                # Prefer expiring soon
                elif item.status == "expiring soon" and best_match.status != "expiring soon":
                    best_match = item
                elif item.status == best_match.status and item.current_expiration_date < best_match.current_expiration_date:
                    best_match = item

        if best_match is not None:
            try:
                suggested_qty = float(ing.quantity) if ing.quantity else 1.0
            except (ValueError, TypeError):
                suggested_qty = 1.0

            if suggested_qty > best_match.quantity_value:
                suggested_qty = best_match.quantity_value

            suggestions.append({
                "ingredient_name": ing.ingredient_name,
                "item_id": best_match.id,
                "item_name": best_match.name,
                "available_quantity": best_match.quantity_value,
                "available_unit": best_match.quantity_unit,
                "suggested_quantity": suggested_qty,
                "unit": ing.unit or best_match.quantity_unit or "",
                "status": best_match.status,
                "current_expiration_date": best_match.current_expiration_date,
                "confidence": "high",
            })
            items.remove(best_match)
        else:
            unmatched.append(ing.ingredient_name)

    return {
        "recipe_id": recipe.id,
        "title": recipe.title,
        "suggestions": suggestions,
        "unmatched_ingredients": unmatched,
    }


def cook_recipe_and_consume(
    db: Session,
    recipe_id: int,
    consume_items: list[dict],
    notes: Optional[str] = None,
) -> Optional[dict]:
    """Mark a recipe as cooked and consume specified inventory items.

    consume_items format: [{"item_id": int, "quantity": float, "ingredient_name": str}]
    """
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        return None

    consumed = []
    for ci in consume_items:
        item = db.query(Item).filter(Item.id == ci["item_id"]).first()
        if item is None:
            continue

        qty = ci["quantity"]
        if qty <= 0:
            continue
        if qty > item.quantity_value:
            qty = item.quantity_value

        original_qty = item.quantity_value
        new_qty = max(0.0, original_qty - qty)
        item.quantity_value = new_qty

        today = date.today()
        from stock_manager.api.services import _calculate_status, _get_expiration_warning_days
        warning_days = _get_expiration_warning_days(db)
        new_status = _calculate_status(
            new_qty,
            item.current_expiration_date,
            warning_days,
            today,
        )
        item.status = new_status

        consumed.append({
            "item_id": item.id,
            "item_name": item.name,
            "consumed_quantity": qty,
            "remaining_quantity": item.quantity_value,
            "status": item.status,
        })

    # Record cooked event
    import json as _json
    metadata = {
        "consumed_items": consumed,
        "notes": notes,
    }
    db.add(RecipeUsageHistory(
        recipe_id=recipe_id,
        event_type="cooked",
        metadata_json=_json.dumps(metadata, ensure_ascii=False),
    ))

    db.commit()

    return {
        "recipe_id": recipe.id,
        "title": recipe.title,
        "consumed_items": consumed,
        "notes": notes,
    }

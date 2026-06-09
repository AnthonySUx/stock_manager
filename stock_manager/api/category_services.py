"""Category system business logic."""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from stock_manager.api.models import Category

# ─── Constants ─────────────────────────────────────────────────────

RECIPE_USAGE_ALWAYS = "always"
RECIPE_USAGE_CONDITIONAL = "conditional"
RECIPE_USAGE_NEVER = "never"
RECIPE_USAGES = {"always", "conditional", "never"}
RECIPE_ALLOWED_USAGES = ("always", "conditional")

DEFAULT_CATEGORIES = [
    # (name, slug, parent_slug, recipe_usage)
    # Top-level
    ("食品", "food", None, "conditional"),
    ("药品/健康", "health", None, "never"),
    ("家居清洁", "household", None, "never"),
    ("个人护理", "personal_care", None, "never"),
    ("宠物", "pet", None, "never"),
    ("母婴", "baby", None, "never"),
    ("电子/工具", "tools_electronics", None, "never"),
    ("其他", "other", None, "never"),
    # Food subcategories
    ("蔬菜", "vegetables", "food", "always"),
    ("水果", "fruit", "food", "always"),
    ("肉类", "meat", "food", "always"),
    ("海鲜", "seafood", "food", "always"),
    ("蛋类", "eggs", "food", "always"),
    ("乳制品", "dairy", "food", "always"),
    ("主食/谷物", "staples_grains", "food", "always"),
    ("豆制品", "soy_products", "food", "always"),
    ("调味品/香料", "seasonings_spices", "food", "always"),
    ("烘焙材料", "baking", "food", "always"),
    ("饮品", "drinks", "food", "conditional"),
    ("零食", "snacks", "food", "conditional"),
    ("冷冻食品", "frozen_food", "food", "conditional"),
    ("罐头/包装食品", "canned_packaged", "food", "conditional"),
    ("即食/熟食", "ready_to_eat", "food", "conditional"),
    ("其他食品", "other_food", "food", "conditional"),
    # Health subcategories
    ("药品", "medicine", "health", "never"),
    ("保健品", "supplements", "health", "never"),
    ("急救用品", "first_aid", "health", "never"),
    ("医疗器械/耗材", "medical_supplies", "health", "never"),
    ("消毒防护", "disinfection_protection", "health", "never"),
    ("其他健康用品", "other_health", "health", "never"),
    # Household subcategories
    ("清洁剂", "cleaners", "household", "never"),
    ("洗衣用品", "laundry", "household", "never"),
    ("纸品", "paper_goods", "household", "never"),
    ("厨房耗材", "kitchen_supplies", "household", "never"),
    ("垃圾袋/收纳", "trash_storage", "household", "never"),
    ("空气/除味", "air_deodorizing", "household", "never"),
    ("其他家居用品", "other_household", "household", "never"),
    # Personal care subcategories
    ("洗发护发", "hair_care", "personal_care", "never"),
    ("沐浴身体护理", "body_care", "personal_care", "never"),
    ("护肤", "skincare", "personal_care", "never"),
    ("口腔护理", "oral_care", "personal_care", "never"),
    ("剃须/美容工具", "grooming_tools", "personal_care", "never"),
    ("女性护理", "feminine_care", "personal_care", "never"),
    ("其他个人护理", "other_personal_care", "personal_care", "never"),
    # Pet subcategories
    ("宠物食品", "pet_food", "pet", "never"),
    ("宠物零食", "pet_treats", "pet", "never"),
    ("宠物药品/保健", "pet_health", "pet", "never"),
    ("清洁护理", "pet_cleaning_care", "pet", "never"),
    ("玩具用品", "pet_toys_supplies", "pet", "never"),
    ("猫砂/垫料", "litter_bedding", "pet", "never"),
    ("其他宠物用品", "other_pet", "pet", "never"),
    # Baby subcategories
    ("婴儿食品/辅食", "baby_food", "baby", "never"),
    ("奶粉", "formula", "baby", "never"),
    ("尿布/湿巾", "diapers_wipes", "baby", "never"),
    ("喂养用品", "feeding_supplies", "baby", "never"),
    ("婴儿护理", "baby_care", "baby", "never"),
    ("玩具用品", "baby_toys", "baby", "never"),
    ("其他母婴用品", "other_baby", "baby", "never"),
    # Tools/electronics subcategories
    ("电池", "batteries", "tools_electronics", "never"),
    ("灯泡/照明", "lighting", "tools_electronics", "never"),
    ("小工具", "tools", "tools_electronics", "never"),
    ("胶带/粘合剂", "tape_adhesives", "tools_electronics", "never"),
    ("维修耗材", "repair_supplies", "tools_electronics", "never"),
    ("电子配件", "electronics_accessories", "tools_electronics", "never"),
    ("其他工具配件", "other_tools_electronics", "tools_electronics", "never"),
    # Other subcategories
    ("未分类", "uncategorized", "other", "never"),
]


def _generate_slug(name: str) -> str:
    """Generate a unique slug for user-created categories."""
    short = uuid.uuid4().hex[:8]
    return f"custom-{short}"


# ─── Seed ──────────────────────────────────────────────────────────

def seed_default_categories(db: Session) -> None:
    """Create default system categories if they do not exist. Idempotent."""
    existing = {c.slug for c in db.query(Category).all()}

    # Build lookup: slug -> Category
    cats: dict[str, Category] = {}

    for name, slug, parent_slug, recipe_usage in DEFAULT_CATEGORIES:
        if slug in existing:
            continue
        parent_id = None
        if parent_slug and parent_slug in cats:
            parent_id = cats[parent_slug].id
        cat = Category(
            name=name,
            slug=slug,
            parent_id=parent_id,
            recipe_usage=recipe_usage,
            is_system=True,
            sort_order=0,
        )
        db.add(cat)
        db.flush()
        cats[slug] = cat

    if cats:
        db.commit()


# ─── Read ───────────────────────────────────────────────────────────

def get_category(db: Session, category_id: int) -> Optional[Category]:
    """Return one category by id."""
    return db.query(Category).filter(Category.id == category_id).first()


def get_category_by_slug(db: Session, slug: str) -> Optional[Category]:
    """Return one category by slug."""
    return db.query(Category).filter(Category.slug == slug).first()


def get_categories_flat(db: Session) -> list[Category]:
    """Return all categories as a flat list."""
    return db.query(Category).order_by(Category.parent_id.is_(None).desc(), Category.sort_order, Category.id).all()


def get_category_tree(db: Session) -> list[dict]:
    """Return categories as a tree."""
    all_cats = get_categories_flat(db)
    cat_map: dict[int, dict] = {}
    roots: list[dict] = []

    for c in all_cats:
        node = {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "parent_id": c.parent_id,
            "recipe_usage": c.recipe_usage,
            "is_system": c.is_system,
            "sort_order": c.sort_order,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "children": [],
        }
        cat_map[c.id] = node

    for c in all_cats:
        node = cat_map[c.id]
        if c.parent_id and c.parent_id in cat_map:
            cat_map[c.parent_id]["children"].append(node)
        else:
            roots.append(node)

    return roots


def get_default_uncategorized(db: Session) -> Category:
    """Return the uncategorized category, creating if needed."""
    cat = get_category_by_slug(db, "uncategorized")
    if cat:
        return cat
    cat = Category(
        name="未分类",
        slug="uncategorized",
        parent_id=None,
        recipe_usage="never",
        is_system=True,
        sort_order=0,
    )
    db.add(cat)
    db.flush()
    return cat


# ─── Validation helpers ─────────────────────────────────────────────

def validate_category_exists(db: Session, category_id: int) -> Category:
    """Raise ValueError if category does not exist."""
    cat = get_category(db, category_id)
    if cat is None:
        raise ValueError(f"Category id={category_id} not found")
    return cat


def _is_top_level(cat: Category) -> bool:
    return cat.parent_id is None


def _has_children(db: Session, category_id: int) -> bool:
    return db.query(Category).filter(Category.parent_id == category_id).count() > 0


# ─── CRUD ───────────────────────────────────────────────────────────

def create_category(db: Session, data: dict) -> Category:
    """Create a new category. Validates hierarchy (max 2 levels)."""
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Category name is required")

    parent_id = data.get("parent_id")
    if parent_id is not None:
        parent = validate_category_exists(db, parent_id)
        if not _is_top_level(parent):
            raise ValueError("Only two levels are allowed. Parent must be a top-level category.")

    # Check duplicate name under same parent
    existing = db.query(Category).filter(
        Category.name == name,
        Category.parent_id == parent_id,
    ).first()
    if existing:
        raise ValueError(f"Category '{name}' already exists under this parent")

    recipe_usage = data.get("recipe_usage")
    if recipe_usage is None:
        if parent_id is not None:
            parent = get_category(db, parent_id)
            recipe_usage = parent.recipe_usage if parent else RECIPE_USAGE_NEVER
        else:
            recipe_usage = RECIPE_USAGE_NEVER

    if recipe_usage not in RECIPE_USAGES:
        raise ValueError(f"Invalid recipe_usage '{recipe_usage}'. Must be one of: always, conditional, never")

    slug = _generate_slug(name)
    sort_order = data.get("sort_order", 0)

    cat = Category(
        name=name,
        slug=slug,
        parent_id=parent_id,
        recipe_usage=recipe_usage,
        is_system=False,
        sort_order=sort_order,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def update_category(db: Session, category_id: int, data: dict) -> Optional[Category]:
    """Update a category. System categories cannot change name or parent_id."""
    cat = get_category(db, category_id)
    if cat is None:
        return None

    name = data.get("name")
    parent_id = data.get("parent_id")
    recipe_usage = data.get("recipe_usage")
    sort_order = data.get("sort_order")

    if cat.is_system:
        if name is not None or parent_id is not None:
            raise ValueError("Cannot change name or parent of system categories")

    if parent_id is not None:
        if parent_id == category_id:
            raise ValueError("Category cannot be its own parent")
        parent = validate_category_exists(db, parent_id)
        if not _is_top_level(parent):
            raise ValueError("Only two levels allowed. Parent must be a top-level category.")
        if _has_children(db, category_id):
            raise ValueError("Cannot move a category that has children")

    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("Category name is required")
        existing = db.query(Category).filter(
            Category.name == name,
            Category.parent_id == (parent_id if parent_id is not None else cat.parent_id),
            Category.id != category_id,
        ).first()
        if existing:
            raise ValueError(f"Category '{name}' already exists under this parent")
        cat.name = name

    if parent_id is not None:
        cat.parent_id = parent_id
    if recipe_usage is not None:
        if recipe_usage not in RECIPE_USAGES:
            raise ValueError(f"Invalid recipe_usage '{recipe_usage}'")
        cat.recipe_usage = recipe_usage
    if sort_order is not None:
        cat.sort_order = sort_order

    db.commit()
    db.refresh(cat)
    return cat


def delete_category(db: Session, category_id: int) -> bool:
    """Delete a category if it is not system, has no children, and is not in use."""
    cat = get_category(db, category_id)
    if cat is None:
        return False

    if cat.is_system:
        raise ValueError("Cannot delete system categories")

    if _has_children(db, category_id):
        raise ValueError("Cannot delete a category that has subcategories")

    # Check if in use by items
    from stock_manager.api.models import Item
    if db.query(Item).filter(Item.category_id == category_id).count() > 0:
        raise ValueError("Cannot delete a category that is in use by inventory items")

    # Check if in use by restock items
    from stock_manager.api.models import RestockItem
    if db.query(RestockItem).filter(RestockItem.category_id == category_id).count() > 0:
        raise ValueError("Cannot delete a category that is in use by restock items")

    db.delete(cat)
    db.commit()
    return True


# ─── Recipe candidate helpers ───────────────────────────────────────

def query_recipe_candidate_items(
    db: Session,
    include_conditional: bool = True,
):
    """Return inventory items eligible for recipe features.
    
    Always returns items with recipe_usage='always'.
    Optionally includes 'conditional' items.
    Never includes 'never' items.
    """
    from stock_manager.api.models import Item
    usages = list(RECIPE_ALLOWED_USAGES) if include_conditional else [RECIPE_USAGE_ALWAYS]
    return (
        db.query(Item)
        .join(Category, Item.category_id == Category.id)
        .filter(
            Item.status.in_(["active", "expiring soon"]),
            Category.recipe_usage.in_(usages),
        )
    )


def get_recipe_candidate_inventory(db: Session, include_conditional: bool = True) -> dict:
    """Return recipe-candidate inventory grouped by recipe_usage.
    
    Returns: {"regular": [...], "occasional": [...]}
    """
    from stock_manager.api.models import Item
    items = (
        db.query(Item)
        .join(Category, Item.category_id == Category.id)
        .filter(
            Item.status.in_(["active", "expiring soon"]),
            Category.recipe_usage.in_(RECIPE_ALLOWED_USAGES),
        )
        .all()
    )

    regular = []
    occasional = []
    for item in items:
        d = {
            "id": item.id,
            "name": item.name,
            "quantity_value": item.quantity_value,
            "quantity_unit": item.quantity_unit,
            "status": item.status,
            "current_expiration_date": item.current_expiration_date,
            "category_name": item.category.name,
            "recipe_usage": item.category.recipe_usage,
        }
        if item.category.recipe_usage == RECIPE_USAGE_ALWAYS:
            regular.append(d)
        else:
            occasional.append(d)

    return {"regular": regular, "occasional": occasional}

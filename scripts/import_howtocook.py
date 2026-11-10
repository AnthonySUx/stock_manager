#!/usr/bin/env python3
"""Import HowToCook markdown recipes into the Stock Manager MySQL database.

Usage:
    python scripts/import_howtocook.py /path/to/HowToCook [--db-url DATABASE_URL]

If --db-url is not provided, the script reads DATABASE_URL from the .env
file in the project root, or falls back to the default MySQL connection.

Re-running is safe: recipes already imported (same source_path) are skipped,
but their category is corrected if it differs from the dishes/ directory
(older versions stored the dish folder name for nested recipes), and their
ingredient list is re-parsed from the markdown, so older rows ("500克" as a
quantity, "番茄（）" names, duplicates) end up the same as a fresh import.
"""
import argparse
import os
import re
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))



def _load_env() -> None:
    """Load .env from the project root (only when run as a script)."""
    from dotenv import load_dotenv
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)


# ─── Markdown parser ─────────────────────────────────────────────


NON_RECIPE_DISH_DIRS = {"template"}


def howtocook_category(filepath) -> str:
    """Return the first directory under `dishes/`, or "" if there is none."""
    parts = [p.lower() if p.lower() == "dishes" else p for p in Path(filepath).parts[:-1]]
    if "dishes" in parts:
        index = parts.index("dishes")
        if index + 1 < len(parts):
            return parts[index + 1]
    return ""


def is_recipe_path(rel_path) -> bool:
    """True for dishes/<category>/.../*.md, except the dishes/template/ example."""
    parts = Path(rel_path).parts
    return (
        len(parts) >= 3
        and parts[0] == "dishes"
        and parts[1] not in NON_RECIPE_DISH_DIRS
        and parts[-1].endswith(".md")
    )


def parse_recipe_md(filepath: str) -> dict:
    """Parse a HowToCook markdown file into structured recipe data.

    Expected structure:
    - Title (first H1)
    - "必备原料和工具" section
    - "计算" section (optional)
    - "操作步骤" section
    - "附加内容" (optional)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")

    # Extract title
    title = ""
    for line in lines:
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            title = m.group(1).strip()
            break

    if not title:
        filename = Path(filepath).stem
        title = filename.replace("-", " ").replace("_", " ").title()

    # Category = first directory under dishes/ (e.g. dishes/meat_dish/口水鸡/口水鸡.md
    # -> meat_dish). Some recipes sit one level deeper, so the folder right above
    # the file is the dish name, not the category (#46).
    category = howtocook_category(filepath)

    # Parse sections
    ingredients = []
    steps = []
    description = ""
    servings = ""
    difficulty = ""
    cook_time = None

    current_section = None
    buffer = []

    for line in lines:
        h_match = re.match(r"^##\s+(.+)$", line)
        if h_match:
            # Flush previous section buffer
            section_text = "\n".join(buffer).strip()
            if current_section == "ingredients":
                ingredients = _parse_ingredients(section_text)
            elif current_section == "steps":
                steps = _parse_steps(section_text)
            elif current_section == "compute":
                if "至少" in section_text or "份" in section_text:
                    m = re.search(r"每份.*?(\d+)\s*[份人]", section_text)
                    if m:
                        pass  # Could extract servings info

            current_section = None
            buffer = []

            section_title = h_match.group(1).strip()
            if "原料" in section_title or "工具" in section_title:
                current_section = "ingredients"
            elif "计算" in section_title:
                current_section = "compute"
            elif "操作" in section_title or "步骤" in section_title:
                current_section = "steps"
            elif "附加" in section_title:
                current_section = None  # Skip
            elif "技巧" in section_title:
                current_section = None  # Skip
            else:
                current_section = None
        else:
            if line.strip():
                buffer.append(line)

    # Flush last buffer
    section_text = "\n".join(buffer).strip()
    if current_section == "ingredients":
        ingredients = _parse_ingredients(section_text)
    elif current_section == "steps":
        steps = _parse_steps(section_text)

    return {
        "title": title,
        "category": category,
        "description": description,
        "difficulty": difficulty,
        "servings": servings,
        "cook_time_minutes": cook_time,
        "ingredients": ingredients,
        "steps": steps,
        "raw_markdown": content,
    }


def _strip_bracket_notes(name: str) -> str:
    """Drop bracketed notes from an ingredient name (#49).

    "剑骨鱼或鲤鱼（约 1.5 斤，让店家处理内脏）" → "剑骨鱼或鲤鱼", and "番茄（2个）"
    → "番茄". The quantity inside the note is read before this, and the full
    text stays in raw_markdown. Nested brackets (a markdown link inside a
    note) are removed from the inside out. If nothing is left, the note text
    itself is the name: "（色拉油 或 菜籽油）" → "色拉油 或 菜籽油".
    """
    stripped = name
    while True:
        shorter = re.sub(r"[（(][^（()）]*[）)]", "", stripped)
        if shorter == stripped:
            break
        stripped = shorter
    stripped = stripped.strip()
    if stripped:
        return stripped
    return re.sub(r"[（()）]", " ", name).strip()


def _parse_ingredients(text: str) -> list[dict]:
    """Parse ingredient section into structured list."""
    results = []
    seen: set[str] = set()
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Check for markdown list item
        line = re.sub(r"^[-\*\d+\.\s]+", "", line).strip()
        if not line:
            continue
        # Skip tool lines
        if any(kw in line for kw in ["锅", "刀", "勺", "碗", "板", "炉", "烤箱", "蒸"]):
            continue

        is_seasoning = any(kw in line for kw in [
            "盐", "糖", "酱油", "醋", "料酒", "油", "胡椒", "花椒",
            "八角", "桂皮", "香叶", "生抽", "老抽", "蚝油", "味精",
            "鸡精", "淀粉", "葱", "姜", "蒜",
        ])

        # Try to extract quantity
        qty_match = re.search(
            r"([\d.]+)\s*(克|毫升|升|斤|两|kg|g|ml|l|勺|汤匙|茶匙|根|条|片|个|只|颗|包|袋|把|捆|块|份|碗|盒|瓶|罐|扎|打)",
            line,
        )
        # Remove "500克" from the name; store 500 and 克 separately (#47).
        name = line
        if qty_match:
            name = name.replace(qty_match.group(0), "", 1)
        name = _strip_bracket_notes(name)
        # Clean up leading punctuation/spaces
        name = re.sub(r"^[\s,，、；;]+", "", name) or line

        # Some recipes list an ingredient twice (口水鸡: 花椒); keep the first.
        if name in seen:
            continue
        seen.add(name)

        results.append({
            "ingredient_name": name,
            "quantity": qty_match.group(1) if qty_match else None,
            "unit": qty_match.group(2) if qty_match else None,
            "is_seasoning": is_seasoning,
            "is_optional": False,
            "sort_order": len(results),
        })

    return results


def _parse_steps(text: str) -> list[dict]:
    """Parse operation steps section."""
    results = []
    counter = 1
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-\*\d+\.\s]+", "", line).strip()
        if line:
            results.append({
                "step_number": counter,
                "instruction": line,
            })
            counter += 1
    return results


# ─── DB operations ───────────────────────────────────────────────


def _get_db_session(db_url: str):
    """Create a SQLAlchemy session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, pool_pre_ping=True)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_local()


def import_howtocook(howtocook_path: str, db_url: str = "", prune_non_recipes: bool = False):
    """Import all HowToCook recipes into the database.

    HowToCook rows that are not recipes (imported from tips/, .github/ or
    dishes/template/ by older versions) are listed; with
    `prune_non_recipes=True` they are deleted, with their favorites and history.
    """
    if not db_url:
        db_url = os.getenv(
            "DATABASE_URL",
            "mysql+pymysql://stock_user:stock_password@127.0.0.1:3306/stock_manager",
        )

    howtocook_dir = Path(howtocook_path)
    if not howtocook_dir.is_dir():
        print(f"Error: {howtocook_path} is not a directory")
        sys.exit(1)

    # Only dishes/ holds recipes; tips/, .github/ and the root files are articles
    # or templates, and dishes/template/ is the example for contributors.
    dishes_dir = howtocook_dir / "dishes"
    if not dishes_dir.is_dir():
        print(f"Error: {dishes_dir} not found (expected the HowToCook repository root)")
        sys.exit(1)
    md_files = [
        f for f in dishes_dir.rglob("*.md")
        if is_recipe_path(f.relative_to(howtocook_dir))
    ]

    print(f"Found {len(md_files)} recipe files")

    session = _get_db_session(db_url)

    # Import metadata
    source_url = "https://github.com/Anduin2017/HowToCook"
    howtocook_name = "HowToCook"
    license_name = "The Unlicense"

    imported_count = 0
    existing_count = 0
    fixed_count = 0
    error_count = 0
    synced_count = 0

    for md_file in sorted(md_files):
        # Check if already imported (by source_path)
        rel_path = str(md_file.relative_to(howtocook_dir))
        from stock_manager.api.models import Recipe

        existing = session.query(Recipe).filter(
            Recipe.source_path == rel_path
        ).first()
        if existing:
            existing_count += 1
            category = howtocook_category(md_file.relative_to(howtocook_dir)) or None
            if existing.category != category:
                print(f"  ↻ {rel_path}: category {existing.category!r} → {category!r}")
                existing.category = category
                fixed_count += 1
            try:
                parsed = parse_recipe_md(str(md_file))["ingredients"]
            except Exception as e:  # keep going; report like a failed import
                session.rollback()
                error_count += 1
                print(f"  ✗ {rel_path}: {e}")
                continue
            if _sync_ingredients(session, existing, parsed):
                print(f"  ↻ {rel_path}: ingredients re-parsed")
                synced_count += 1
            session.commit()
            continue

        try:
            recipe_data = parse_recipe_md(str(md_file))

            if not recipe_data["title"]:
                print(f"  ⚠ Skipping {rel_path}: no title found")
                error_count += 1
                continue

            from stock_manager.api.models import Recipe, RecipeIngredient, RecipeStep

            recipe = Recipe(
                source_type="howtocook",
                source_name=howtocook_name,
                source_url=source_url,
                source_path=rel_path,
                license_name=license_name,
                title=recipe_data["title"],
                # From the path relative to the repo root, so folders above it
                # (e.g. ~/dishes/HowToCook) cannot be mistaken for dishes/.
                category=howtocook_category(md_file.relative_to(howtocook_dir)) or None,
                description=recipe_data["description"] or None,
                difficulty=recipe_data["difficulty"] or None,
                servings=recipe_data["servings"] or None,
                cook_time_minutes=recipe_data["cook_time_minutes"],
                raw_markdown=recipe_data["raw_markdown"],
                is_user_created=False,
            )
            session.add(recipe)
            session.flush()

            for ing in recipe_data["ingredients"]:
                session.add(RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_name=ing["ingredient_name"],
                    quantity=ing["quantity"],
                    unit=ing["unit"],
                    is_seasoning=ing["is_seasoning"],
                    is_optional=ing["is_optional"],
                    sort_order=ing["sort_order"],
                ))

            for step in recipe_data["steps"]:
                session.add(RecipeStep(
                    recipe_id=recipe.id,
                    step_number=step["step_number"],
                    instruction=step["instruction"],
                ))

            session.commit()
            imported_count += 1
            print(f"  ✓ {rel_path} → {recipe_data['title']}")

        except Exception as e:
            session.rollback()
            error_count += 1
            print(f"  ✗ {rel_path}: {e}")

    non_recipe, pruned = _handle_non_recipe_rows(session, prune_non_recipes)
    session.close()
    print(
        f"\nImport complete: {imported_count} imported, {existing_count} existing "
        f"({fixed_count} categories fixed, {synced_count} ingredient lists re-parsed), "
        f"{error_count} errors"
    )
    return {"imported": imported_count, "existing": existing_count,
            "fixed": fixed_count, "ingredients_synced": synced_count,
            "errors": error_count, "non_recipe": non_recipe, "pruned": pruned}


_INGREDIENT_FIELDS = ("ingredient_name", "quantity", "unit", "is_seasoning", "is_optional", "sort_order")


def _sync_ingredients(session, recipe, parsed: list[dict]) -> bool:
    """Make an existing HowToCook recipe's ingredients match a fresh parse.

    HowToCook recipes cannot be edited in the app, so their ingredient rows
    are always what the importer wrote. Older importers stored "500克" as
    the quantity, left "番茄（）" / "（约 ，…）" in names and kept duplicates;
    rewriting the rows gives the same result as a fresh import. Returns
    True when the rows changed.
    """
    from stock_manager.api.models import RecipeIngredient

    current = sorted(recipe.ingredients, key=lambda i: (i.sort_order, i.id))
    as_rows = [tuple(getattr(i, f) for f in _INGREDIENT_FIELDS) for i in current]
    wanted = [tuple(p[f] for f in _INGREDIENT_FIELDS) for p in parsed]
    if as_rows == wanted:
        return False
    for ing in current:
        session.delete(ing)
    session.flush()
    for p in parsed:
        session.add(RecipeIngredient(recipe_id=recipe.id, **{f: p[f] for f in _INGREDIENT_FIELDS}))
    session.expire(recipe, ["ingredients"])
    return True


def _handle_non_recipe_rows(session, prune: bool) -> tuple[int, int]:
    """List (and optionally delete) HowToCook rows that are not recipes."""
    from stock_manager.api.models import Recipe, RecipeFavorite, RecipeUsageHistory

    rows = [
        r for r in session.query(Recipe).filter(Recipe.source_type == "howtocook").all()
        if not is_recipe_path(r.source_path or "")
    ]
    if not rows:
        return 0, 0
    print(f"\n{len(rows)} HowToCook row(s) are not recipes (tips/, .github/, template):")
    for r in rows:
        print(f"  - {r.source_path}")
    if not prune:
        print("They are not recommended. Re-run with --prune-non-recipes to delete them.")
        return len(rows), 0

    ids = [r.id for r in rows]
    session.query(RecipeFavorite).filter(RecipeFavorite.recipe_id.in_(ids)).delete(synchronize_session=False)
    session.query(RecipeUsageHistory).filter(RecipeUsageHistory.recipe_id.in_(ids)).delete(synchronize_session=False)
    for r in rows:
        session.delete(r)  # ingredients and steps cascade; forks keep a NULL link
    session.commit()
    print(f"Deleted {len(rows)} non-recipe row(s).")
    return len(rows), len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Import HowToCook recipes into Stock Manager database"
    )
    parser.add_argument("howtocook_path", help="Path to HowToCook repository root")
    parser.add_argument(
        "--prune-non-recipes",
        action="store_true",
        help="Delete previously imported rows that are not recipes (tips/, .github/, template)",
    )
    parser.add_argument(
        "--db-url",
        default="",
        help="Database URL (default: from .env or default MySQL connection)",
    )
    args = parser.parse_args()
    _load_env()
    import_howtocook(args.howtocook_path, args.db_url, args.prune_non_recipes)


if __name__ == "__main__":
    main()

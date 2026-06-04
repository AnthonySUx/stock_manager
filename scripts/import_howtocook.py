#!/usr/bin/env python3
"""Import HowToCook markdown recipes into the Stock Manager MySQL database.

Usage:
    python scripts/import_howtocook.py /path/to/HowToCook [--db-url DATABASE_URL]

If --db-url is not provided, the script reads DATABASE_URL from the .env
file in the project root, or falls back to the default MySQL connection.
"""
import argparse
import os
import re
import sys
import glob
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# Load .env from project root
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)


# ─── Markdown parser ─────────────────────────────────────────────


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

    # Extract category from path
    rel_path = Path(filepath)
    category = ""
    for part in rel_path.parts:
        if part.lower() in ("dishes",):
            continue
        if part.endswith(".md"):
            continue
        if rel_path.parent.name.lower() != "dishes":
            category = rel_path.parent.name
            break

    # Parse sections
    ingredients = []
    steps = []
    description = ""
    servings = ""
    difficulty = ""
    cook_time = None

    current_section = None
    step_counter = 0
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


def _parse_ingredients(text: str) -> list[dict]:
    """Parse ingredient section into structured list."""
    results = []
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
        quantity = qty_match.group(0) if qty_match else ""

        # Remove the quantity from ingredient name
        name = line
        if quantity:
            name = name.replace(quantity, "", 1).strip()
        # Clean up leading punctuation/spaces
        name = re.sub(r"^[\s,，、；;]+", "", name)

        results.append({
            "ingredient_name": name or line,
            "quantity": quantity or None,
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
    from sqlalchemy.orm import Session, sessionmaker

    engine = create_engine(db_url, pool_pre_ping=True)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_local()


def import_howtocook(howtocook_path: str, db_url: str = ""):
    """Import all HowToCook recipes into the database."""
    if not db_url:
        db_url = os.getenv(
            "DATABASE_URL",
            "mysql+pymysql://stock_user:stock_password@127.0.0.1:3306/stock_manager",
        )

    howtocook_dir = Path(howtocook_path)
    if not howtocook_dir.is_dir():
        print(f"Error: {howtocook_path} is not a directory")
        sys.exit(1)

    md_files = list(howtocook_dir.rglob("*.md"))

    # Filter out root-level README, LICENSE, etc.
    md_files = [
        f for f in md_files
        if "dishes" in str(f) or f.parent.name != howtocook_dir.name
    ]

    # Also exclude common non-recipe files
    exclude_files = {"README.md", "CONTRIBUTING.md", "LICENSE", "CODE_OF_CONDUCT.md"}
    md_files = [f for f in md_files if f.name not in exclude_files]

    if not md_files:
        print(f"No recipe markdown files found under {howtocook_path}")
        print("Looking for files in 'dishes/' subdirectory...")
        dishes_dir = howtocook_dir / "dishes"
        if dishes_dir.is_dir():
            md_files = list(dishes_dir.rglob("*.md"))

    print(f"Found {len(md_files)} recipe files")

    session = _get_db_session(db_url)

    # Import metadata
    source_url = "https://github.com/Anduin2017/HowToCook"
    howtocook_name = "HowToCook"
    license_name = "The Unlicense"

    imported_count = 0
    existing_count = 0
    error_count = 0

    for md_file in sorted(md_files):
        # Check if already imported (by source_path)
        rel_path = str(md_file.relative_to(howtocook_dir))
        from stock_manager.api.models import Recipe

        existing = session.query(Recipe).filter(
            Recipe.source_path == rel_path
        ).first()
        if existing:
            existing_count += 1
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
                category=recipe_data["category"] or None,
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

    session.close()
    print(f"\nImport complete: {imported_count} imported, {existing_count} existing, {error_count} errors")


def main():
    parser = argparse.ArgumentParser(
        description="Import HowToCook recipes into Stock Manager database"
    )
    parser.add_argument("howtocook_path", help="Path to HowToCook repository root")
    parser.add_argument(
        "--db-url",
        default="",
        help="Database URL (default: from .env or default MySQL connection)",
    )
    args = parser.parse_args()
    import_howtocook(args.howtocook_path, args.db_url)


if __name__ == "__main__":
    main()

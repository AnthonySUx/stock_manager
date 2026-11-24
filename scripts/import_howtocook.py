#!/usr/bin/env python3
"""Import HowToCook markdown recipes into the Stock Manager MySQL database.

Usage:
    python scripts/import_howtocook.py /path/to/HowToCook [--db-url DATABASE_URL] [--with-photos]

If --db-url is not provided, the script requires DATABASE_URL from the .env
file in the project root. It never guesses a local MySQL connection.

Re-running is safe: recipes already imported (same source_path) are skipped,
but their category is corrected if it differs from the dishes/ directory
(older versions stored the dish folder name for nested recipes), and their
ingredients and steps are re-parsed from the markdown, so older rows ("500克"
as a quantity, "番茄（）" names, duplicates, preview images as steps) end up
the same as a fresh import.
"""
import argparse
import os
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from urllib.parse import unquote

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stock_manager.api.equipment import (
    BASIC_TOOL_TERMS,
    EQUIPMENT_TERMS,
    INGREDIENT_EXCEPTIONS,
    TOOL_SUFFIXES,
    catalog_order,
)


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
            original = m.group(1).strip()
            title = original.removesuffix("的做法").strip() or original
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
    tool_groups = []
    unclassified_tools = []
    steps = []
    step_groups = []
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
                ingredients, tool_groups, unclassified_tools = _parse_ingredient_section(section_text)
            elif current_section == "steps":
                steps = _parse_steps(section_text)
                step_groups = _step_equipment(section_text)
            elif current_section == "compute":
                if "至少" in section_text or "份" in section_text:
                    m = re.search(r"每份.*?(\d+)\s*[份人]", section_text)
                    if m:
                        pass  # Could extract servings info

            current_section = None
            buffer = []

            section_title = h_match.group(1).strip()
            if re.search(r"附加|小贴士|技巧", section_title):
                continue
            if "原料" in section_title or "工具" in section_title:
                current_section = "ingredients"
            elif "计算" in section_title:
                current_section = "compute"
            elif "操作" in section_title or "步骤" in section_title:
                current_section = "steps"
        else:
            if line.strip():
                buffer.append(line)

    # Flush last buffer
    section_text = "\n".join(buffer).strip()
    if current_section == "ingredients":
        ingredients, tool_groups, unclassified_tools = _parse_ingredient_section(section_text)
    elif current_section == "steps":
        steps = _parse_steps(section_text)
        step_groups = _step_equipment(section_text)

    return {
        "title": title,
        "category": category,
        "description": description,
        "difficulty": difficulty,
        "servings": servings,
        "cook_time_minutes": cook_time,
        "ingredients": ingredients,
        "steps": steps,
        "equipment": _merge_equipment(
            [[code] for code in _special_codes(title)] + tool_groups + step_groups
        ),
        "unclassified_tools": unclassified_tools,
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


# A list marker at the start of a line: "-", "*", "+", or "1." / "1)" / "1、"
# (not followed by a digit, so "3.5 克盐" is a quantity, not item 3). Only the
# marker is removed, so "1. 2 个鸡蛋打散" keeps its "2".
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+[.)、](?!\d))\s*")
_HORIZONTAL_RULE_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
# A link or image target may contain one level of balanced parentheses, as in
# "./血浆鸭(特辣).jpg"; stopping at the first ")" would cut the path short.
_TARGET = r"(?:[^()]|\([^()]*\))*"
_IMAGE_RE = re.compile(rf"!\[[^\]]*\]\({_TARGET}\)")
_LINK_RE = re.compile(rf"\[([^\]]*)\]\({_TARGET}\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_line(line: str) -> str:
    """Plain text of one markdown line, or "" when it is not content.

    Images are removed (HowToCook puts preview images inside the steps
    section), links keep their text, HTML tags and the quote marker are
    dropped. Sub-headings and table rows are not steps or ingredients.
    """
    line = line.strip()
    if not line or line.startswith(("#", "|")) or _HORIZONTAL_RULE_RE.match(line.replace(" ", "")):
        return ""
    line = _IMAGE_RE.sub("", line)
    line = _LINK_RE.sub(r"\1", line)
    line = _HTML_TAG_RE.sub("", line)
    # Quote and list markers can nest (">- 11.硅油纸"): remove them all.
    while True:
        stripped = _LIST_MARKER_RE.sub("", line.lstrip(">").strip(), count=1).strip()
        if stripped == line:
            break
        line = stripped
    # Nothing but punctuation left (e.g. a stray "-"): not content.
    return line if re.search(r"\w", line) else ""


_SPECIAL_CODES = {
    term: code for code, terms in EQUIPMENT_TERMS.items() for term in terms
}
_SPECIAL_RE = re.compile("|".join(sorted(_SPECIAL_CODES, key=len, reverse=True)))
_LABEL_RE = re.compile(r"^(需要|必备|工具|可选)\s*[：:]?\s*")
_SIZE_RE = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:厘米|公分|毫米|cm|mm|°C|℃|个|把|口|只|件|升|克|kg|ml|g)?"
    r"(?:以上|以下|左右)?(?:的)?\s*", re.IGNORECASE,
)
_HEAD_SEPARATOR_RE = re.compile(r"\s|[（(，,、/]|或者?")
_ALTERNATIVE_RE = re.compile(r"或者?|/")
_NOTE_ALTERNATIVE_RE = re.compile(r"可替代|代替|即可|也行|也可以|没有的话")
_STEP_ALTERNATIVE_RE = re.compile(r"或|也可以|可以用|如果没有|没有的话|代替|替代|可选")


def _tool_subject(segment: str) -> tuple[str, bool]:
    segment = re.sub(r"^[①-⑩]|^\d+[.、](?!\d)", "", segment.strip()).lstrip()
    optional = False
    while label := _LABEL_RE.match(segment):
        optional |= label[1] == "可选"
        segment = segment[label.end():]
    subject = re.split(r"[：:]", segment, maxsplit=1)[0]
    subject = _SIZE_RE.sub("", subject)
    subject = _HEAD_SEPARATOR_RE.split(subject, maxsplit=1)[0]
    return re.sub(r"一个$|一把$|一口$|若干$", "", subject), optional


def _special_codes(text: str) -> list[str]:
    return list(dict.fromkeys(_SPECIAL_CODES[match[0]] for match in _SPECIAL_RE.finditer(text)))


def _bracket_parts(segment: str) -> tuple[str, list[str]]:
    """Split text and notes, including a note with an unclosed parenthesis."""
    body, notes, note = [], [], []
    depth = 0
    for char in segment:
        if char in "(（":
            depth += 1
        elif char in ")）" and depth:
            depth -= 1
            if not depth:
                notes.append("".join(note))
                note.clear()
        elif depth:
            note.append(char)
        else:
            body.append(char)
    if note:
        notes.append("".join(note))
    return "".join(body), notes


def _basic_note_alternative(note: str) -> bool:
    # Remove appliance names before testing standalone basic-tool mentions.
    # In particular, the 锅 in 电饭锅 or 锅胆 is not an alternative.
    text = _SPECIAL_RE.sub(" ", note)
    for phrase in re.split(r"[，,。；;、\s]|可替代|代替|即可|也行|也可以|没有的话", text):
        phrase = re.sub(r"^(?:可以用|改用|就用|用)", "", phrase)
        subject, _ = _tool_subject(phrase)
        if subject in BASIC_TOOL_TERMS:
            return True
    return False


def _tool_groups(segment: str, optional: bool) -> list[list[str]]:
    if optional or "可选" in segment:
        return []
    body, notes = _bracket_parts(segment)
    codes = _special_codes(body)
    if not codes:
        return []
    alternative = bool(_ALTERNATIVE_RE.search(body))
    if alternative and any(
        _tool_subject(part)[0] in BASIC_TOOL_TERMS for part in _ALTERNATIVE_RE.split(body)
    ):
        return []
    for note in notes:
        if _NOTE_ALTERNATIVE_RE.search(note):
            if _basic_note_alternative(note):
                return []
            note_codes = _special_codes(note)
            alternative |= bool(note_codes)
            codes.extend(note_codes)
    return [catalog_order(codes)] if alternative else [[code] for code in codes]


def _step_equipment(text: str) -> list[list[str]]:
    groups = []
    in_notes = False
    for line in text.splitlines():
        heading = re.match(r"^#{3,6}\s+(.+)", line.strip())
        if heading:
            in_notes = bool(re.search(r"附加|小贴士|技巧", heading[1]))
        if in_notes:
            continue
        for sentence in re.split(r"[。！？!?；;]", _clean_line(line)):
            if not _STEP_ALTERNATIVE_RE.search(sentence):
                groups.extend([code] for code in _special_codes(sentence))
    return groups


def _merge_equipment(groups: list[list[str]]) -> list[list[str]]:
    required = {group[0] for group in groups if len(group) == 1}
    return [
        list(group) for group in dict.fromkeys(map(tuple, groups))
        if len(group) == 1 or required.isdisjoint(group)
    ]


def _parse_ingredients(text: str) -> list[dict]:
    """Parse ingredient rows without the equipment metadata."""
    return _parse_ingredient_section(text)[0]


def _parse_ingredient_section(text: str) -> tuple[list[dict], list[list[str]], list[str]]:
    """Split ingredients and equipment, then parse ingredients as before."""
    ingredients, groups, unclassified = [], [], []
    for raw_line in text.splitlines():
        line = _clean_line(raw_line)
        if not line or line.startswith(("注：", "注意", "建议")):
            continue
        for segment in map(str.strip, line.split("+")):
            if not segment:
                continue
            subject, optional = _tool_subject(segment)
            listed_tool = subject in _SPECIAL_CODES or subject in BASIC_TOOL_TERMS
            if listed_tool or (
                subject.endswith(TOOL_SUFFIXES) and subject not in INGREDIENT_EXCEPTIONS
            ):
                if not listed_tool:
                    unclassified.append(subject)
                groups.extend(_tool_groups(segment, optional))
            else:
                ingredients.append(segment)

    results = []
    seen: set[str] = set()
    for line in ingredients:
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

    return results, _merge_equipment(groups), unclassified


def _parse_steps(text: str) -> list[dict]:
    """Parse operation steps section."""
    results = []
    counter = 1
    for line in text.split("\n"):
        line = _clean_line(line)
        if line:
            results.append({
                "step_number": counter,
                "instruction": line,
            })
            counter += 1
    return results


_PHOTO_REF = re.compile(rf"!\[([^\]]*)\]\(({_TARGET})\)")
_PHOTO_STATS = ("added", "updated", "removed", "missing", "remote_skipped")


def _photo_steps(markdown: str, step_numbers: list[int]) -> list[tuple[str, str, int | None]]:
    """Extract images while counting steps with the same rules as _parse_steps."""
    refs = []
    in_steps = False
    step_number = 0
    section_start = 0
    for line in markdown.split("\n"):
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            title = heading.group(1)
            in_steps = not ("原料" in title or "工具" in title or "计算" in title) and (
                "操作" in title or "步骤" in title
            )
            if in_steps:
                # Like parse_recipe_md, the last steps section replaces earlier ones.
                refs[section_start:] = [(alt, path, None) for alt, path, _ in refs[section_start:]]
                section_start = len(refs)
                step_number = 0
        for match in _PHOTO_REF.finditer(line):
            alt, path = match.groups()
            step = None
            if refs and in_steps and "预览图" not in alt and "成品" not in alt:
                step = step_number + bool(_clean_line(line[:match.start()])) or None
            refs.append((alt, path.strip().removeprefix("<").removesuffix(">"), step))
        if in_steps and _clean_line(line):
            step_number += 1
    return [
        (alt, path, step_numbers[index - 1] if index is not None else None)
        for alt, path, index in refs
    ]


def _sync_photos(session, recipe, parsed, md_file, root, stored_hashes, old_hashes):
    from stock_manager.api import media
    from stock_manager.api.errors import APIError
    from stock_manager.api.models import RecipePhoto

    stats = Counter()
    existing = {
        photo.source_path: photo for photo in session.query(RecipePhoto).filter(
            RecipePhoto.recipe_id == recipe.id, RecipePhoto.origin == "howtocook",
            RecipePhoto.source_path.is_not(None),
        )
    }
    positions = Counter()
    referenced = set()
    seen = set()
    step_numbers = [step["step_number"] for step in parsed["steps"]]
    for caption, ref, step in _photo_steps(parsed["raw_markdown"], step_numbers):
        if ref.lower().startswith(("http://", "https://")):
            stats["remote_skipped"] += 1
            continue
        path = (md_file.parent / unquote(ref)).resolve()
        if not path.is_relative_to(root):
            stats["missing"] += 1
            continue
        source_path = path.relative_to(root).as_posix()
        referenced.add(source_path)
        if not path.is_file():
            stats["missing"] += 1
            continue
        if source_path in seen:
            continue
        try:
            with path.open("rb") as image:
                stored = media.store_image(image.read(media.MAX_IMAGE_BYTES + 1))
        except APIError as exc:
            print(f"  ⚠ {source_path}: {exc.code}")
            continue
        stored_hashes.add(stored.sha256)
        photo = existing.get(source_path)
        seen.add(source_path)
        fields = {
            **asdict(stored), "step_number": step, "position": positions[step],
            "caption": caption[:255],
        }
        positions[step] += 1
        if photo is None:
            session.add(RecipePhoto(
                recipe_id=recipe.id, origin="howtocook", source_path=source_path, **fields,
            ))
            stats["added"] += 1
        elif any(getattr(photo, key) != value for key, value in fields.items()):
            if photo.sha256 != stored.sha256:
                old_hashes.add(photo.sha256)
            for key, value in fields.items():
                setattr(photo, key, value)
            stats["updated"] += 1

    # A sparse checkout may temporarily lack a referenced source. Remove rows
    # only when the Markdown reference itself has disappeared.
    for source_path, photo in existing.items():
        if source_path not in referenced:
            session.delete(photo)
            old_hashes.add(photo.sha256)
            stats["removed"] += 1
    return stats


# ─── DB operations ───────────────────────────────────────────────


def _get_db_session(db_url: str):
    """Create a SQLAlchemy session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, pool_pre_ping=True)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_local()


def import_howtocook(
    howtocook_path: str, db_url: str = "", prune_non_recipes: bool = False, *, with_photos: bool = False,
):
    """Import all HowToCook recipes into the database.

    HowToCook rows that are not recipes (imported from tips/, .github/ or
    dishes/template/ by older versions) are listed; with
    `prune_non_recipes=True` they are deleted, with their favorites and history.
    """
    if not db_url:
        db_url = (os.getenv("DATABASE_URL") or "").strip()
        if not db_url:
            raise RuntimeError(
                "DATABASE_URL is required. Copy .env.example to .env or pass --db-url explicitly."
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

    from stock_manager.api import media
    from stock_manager.api.models import Recipe, RecipeIngredient, RecipeStep

    if with_photos or prune_non_recipes:
        media.reload_config()
    if with_photos and not media.available():
        raise RuntimeError("MEDIA_DIR is required with --with-photos")

    session = _get_db_session(db_url)
    root = howtocook_dir.resolve()

    # Import metadata
    source_url = "https://github.com/Anduin2017/HowToCook"
    howtocook_name = "HowToCook"
    license_name = "The Unlicense"

    imported_count = 0
    existing_count = 0
    fixed_count = 0
    error_count = 0
    synced_count = 0
    steps_synced_count = 0
    titles_synced_count = 0

    photo_stats = Counter()
    for md_file in sorted(md_files):
        rel_path = str(md_file.relative_to(howtocook_dir))
        with media.file_transaction(enabled=with_photos):
            stored_hashes = set()
            old_hashes = set()
            try:
                recipe_data = parse_recipe_md(str(md_file))
                if not recipe_data["title"]:
                    print(f"  ⚠ Skipping {rel_path}: no title found")
                    error_count += 1
                    continue

                recipe = session.query(Recipe).filter(
                    Recipe.source_path == rel_path, Recipe.source_type == "howtocook",
                ).with_for_update().first()
                new_recipe = recipe is None
                category = howtocook_category(md_file.relative_to(howtocook_dir)) or None
                messages = []
                if new_recipe:
                    recipe = Recipe(
                        source_type="howtocook", source_name=howtocook_name,
                        source_url=source_url, source_path=rel_path, license_name=license_name,
                        title=recipe_data["title"], category=category,
                        description=recipe_data["description"] or None,
                        difficulty=recipe_data["difficulty"] or None,
                        servings=recipe_data["servings"] or None,
                        cook_time_minutes=recipe_data["cook_time_minutes"],
                        raw_markdown=recipe_data["raw_markdown"], is_user_created=False,
                    )
                    session.add(recipe)
                    session.flush()
                    for ing in recipe_data["ingredients"]:
                        session.add(RecipeIngredient(recipe_id=recipe.id, **ing))
                    for step in recipe_data["steps"]:
                        session.add(RecipeStep(recipe_id=recipe.id, **step))
                    category_changed = title_changed = ingredients_changed = steps_changed = False
                else:
                    category_changed = recipe.category != category
                    title_changed = recipe.title != recipe_data["title"]
                    if category_changed:
                        messages.append(f"  ↻ {rel_path}: category {recipe.category!r} → {category!r}")
                        recipe.category = category
                    if title_changed:
                        messages.append(f"  ↻ {rel_path}: title '{recipe.title}' → '{recipe_data['title']}'")
                        recipe.title = recipe_data["title"]
                    ingredients_changed = _sync_ingredients(session, recipe, recipe_data["ingredients"])
                    if ingredients_changed:
                        messages.append(f"  ↻ {rel_path}: ingredients re-parsed")
                    steps_changed = _sync_steps(session, recipe, recipe_data["steps"])
                    if steps_changed:
                        messages.append(f"  ↻ {rel_path}: steps re-parsed")

                if with_photos:
                    stats = _sync_photos(
                        session, recipe, recipe_data, md_file, root, stored_hashes, old_hashes,
                    )
                session.commit()
            except Exception as e:
                session.rollback()
                for sha256 in stored_hashes:
                    media.delete_files_if_unused(session, sha256)
                session.rollback()
                error_count += 1
                print(f"  ✗ {rel_path}: {e}")
                continue

            if with_photos:
                photo_stats.update(stats)
                for sha256 in old_hashes:
                    media.delete_files_if_unused(session, sha256)
                if old_hashes:
                    session.rollback()
        if new_recipe:
            imported_count += 1
            print(f"  ✓ {rel_path} → {recipe_data['title']}")
        else:
            existing_count += 1
            fixed_count += category_changed
            titles_synced_count += title_changed
            synced_count += ingredients_changed
            steps_synced_count += steps_changed
            for message in messages:
                print(message)

    with media.file_transaction(enabled=prune_non_recipes):
        non_recipe, pruned = _handle_non_recipe_rows(session, prune_non_recipes)
    session.close()
    print(
        f"\nImport complete: {imported_count} imported, {existing_count} existing "
        f"({fixed_count} categories fixed, {synced_count} ingredient lists and "
        f"{steps_synced_count} step lists re-parsed, {titles_synced_count} titles updated), "
        f"{error_count} errors"
    )
    result = {"imported": imported_count, "existing": existing_count,
            "fixed": fixed_count, "ingredients_synced": synced_count,
            "steps_synced": steps_synced_count, "titles_synced": titles_synced_count,
              "errors": error_count, "non_recipe": non_recipe, "pruned": pruned}
    if with_photos:
        result["photos"] = {key: photo_stats[key] for key in _PHOTO_STATS}
        print("photos: " + ", ".join(f"{key} {photo_stats[key]}" for key in _PHOTO_STATS))
        if photo_stats["missing"]:
            print(f"Images are missing. Run: git -C {howtocook_path} sparse-checkout disable")
    return result


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


def _sync_steps(session, recipe, parsed: list[dict]) -> bool:
    """Same as _sync_ingredients, for steps: older imports kept preview
    images, headings and HTML as steps. Returns True when the rows changed."""
    from stock_manager.api.models import RecipeStep

    current = sorted(recipe.steps, key=lambda s: (s.step_number, s.id))
    if [(s.step_number, s.instruction) for s in current] == [
        (p["step_number"], p["instruction"]) for p in parsed
    ]:
        return False
    for step in current:
        session.delete(step)
    session.flush()
    for p in parsed:
        session.add(RecipeStep(recipe_id=recipe.id, step_number=p["step_number"], instruction=p["instruction"]))
    session.expire(recipe, ["steps"])
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

    from stock_manager.api import media
    from stock_manager.api.photo_services import delete_recipe_photos

    ids = [r.id for r in rows]
    hashes = delete_recipe_photos(session, ids)
    session.query(RecipeFavorite).filter(RecipeFavorite.recipe_id.in_(ids)).delete(synchronize_session=False)
    session.query(RecipeUsageHistory).filter(RecipeUsageHistory.recipe_id.in_(ids)).delete(synchronize_session=False)
    for r in rows:
        session.delete(r)  # ingredients and steps cascade; forks keep a NULL link
    session.commit()
    for sha256 in hashes:
        media.delete_files_if_unused(session, sha256)
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
        help="Database URL (default: required from .env)",
    )
    parser.add_argument("--with-photos", action="store_true", help="Import local recipe photos")
    args = parser.parse_args()
    _load_env()
    try:
        import_howtocook(
            args.howtocook_path, args.db_url, args.prune_non_recipes, with_photos=args.with_photos,
        )
    except RuntimeError as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()

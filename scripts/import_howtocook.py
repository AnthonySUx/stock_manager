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
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path
from urllib.parse import unquote

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# The script can be run directly from scripts/, with the repository on sys.path.
from stock_manager.api.equipment import (  # noqa: E402
    BASIC_TOOL_TERMS,
    EQUIPMENT_CODES,
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

    ingredients, computed, calc_unparsed, steps, unclassified_tools = [], [], [], [], []
    equipment = [[code] for code in _special_codes(title)]
    for section, section_text in _recipe_sections(content):
        if section == "ingredients":
            rows, groups, unclassified = _parse_ingredient_section(section_text)
            ingredients.extend(rows)
            equipment.extend(groups)
            unclassified_tools.extend(unclassified)
        elif section == "steps":
            steps = _parse_steps(section_text)
            equipment.extend(_step_equipment(section_text))
        elif section == "compute":
            rows, unparsed = _parse_calculations(section_text)
            computed.extend(rows)
            calc_unparsed.extend(unparsed)

    return {
        "title": title,
        "category": category,
        "description": "",
        "difficulty": "",
        "servings": "",
        "cook_time_minutes": None,
        "ingredients": _merge_ingredients(ingredients, computed),
        "calc_unparsed": calc_unparsed,
        "steps": steps,
        "equipment": _merge_equipment(equipment),
        "unclassified_tools": unclassified_tools,
        "raw_markdown": content,
    }


def _section_kind(title: str) -> str | None:
    if re.search(r"附加|小贴士|技巧", title):
        return None
    if "计算" in title:
        return "compute"
    if "原料" in title or "工具" in title:
        return "ingredients"
    if "操作" in title or "步骤" in title:
        return "steps"
    return None


def _recipe_sections(content: str) -> Iterator[tuple[str, str]]:
    section = None
    lines = []
    for line in content.splitlines():
        if heading := re.match(r"^##\s+(.+)$", line):
            if section:
                yield section, "\n".join(lines)
            section = _section_kind(heading[1])
            lines = []
        elif section:
            lines.append(line)
    if section:
        yield section, "\n".join(lines)


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
_LIST_MARKER_RE = re.compile(r"^(?:[-+]|\*(?=\s)|\d+[.)、](?!\d))\s*")
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
    # Remove Markdown emphasis without losing the first character of bold text.
    line = re.sub(r"\*\*|__|`", "", line)
    line = re.sub(r"([*_])([^*_]+)\1", r"\2", line)
    # Nothing but punctuation left (e.g. a stray "-"): not content.
    return line if re.search(r"\w", line) else ""


_SPECIAL_CODES = {
    term: code for code, terms in EQUIPMENT_TERMS.items() for term in terms
}
_SPECIAL_RE = re.compile("|".join(sorted(_SPECIAL_CODES, key=len, reverse=True)))
_MARKDOWN_EMPHASIS = str.maketrans("", "", "`*")
_SENTENCE_PUNCTUATION_RE = re.compile(r"[。！!；;]")
_INGREDIENT_CATEGORIES = frozenset({"调味料", "主料", "辅料", "配料", "原料", "材料", "其他调味料"})
_CATEGORY_PROSE_RE = re.compile(r"[。！!；;]|随便|建议|可以|例如|即可")
_INGREDIENT_PROSE_PREFIXES = ("注", "注意", "建议", "原则", "说明", "提示")
_COLON_RE = re.compile(r"[：:]")
_LABEL_RE = re.compile(r"^(需要|必备|工具|可选)\s*[：:]?\s*")
_SIZE_RE = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:厘米|公分|毫米|cm|mm|°C|℃|个|把|口|只|件|升|克|kg|ml|g)?"
    r"(?:以上|以下|左右)?(?:的)?\s*", re.IGNORECASE,
)
_HEAD_SEPARATOR_RE = re.compile(r"\s|[（(，,、/]|或者?")
_ALTERNATIVE_RE = re.compile(r"或者?|/")
_NOTE_ALTERNATIVE_RE = re.compile(r"可替代|代替|即可|也行|也可以|没有的话")
_TOOL_OPTIONS = "|".join(map(re.escape, sorted(_SPECIAL_CODES.keys() | BASIC_TOOL_TERMS, key=lambda term: (-len(term), term))))
_STEP_OPTION_BEFORE_RE = re.compile(
    rf"(?:{_TOOL_OPTIONS})\s*(?:或者?|/)\s*$|(?:也可以(?:使用|用)?|可以用|改用)\s*$"
)
_STEP_OPTION_AFTER_RE = re.compile(rf"^\s*(?:或者?|/)\s*(?:{_TOOL_OPTIONS})|^[^，,]*?(?:代替|替代)")
_STEP_FALLBACK_RE = re.compile(rf"(?:如果没有|没有的话).*?(?:{_SPECIAL_RE.pattern})")
_INGREDIENT_MARKUP = str.maketrans("", "", "*`[]")
_EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\ufe0f\u200d\u20e3]")
_INGREDIENT_QUANTITY_UNITS = (
    "汤匙|茶匙|毫升|千克|ml|mL|kg|cm|克|升|斤|个|只|根|颗|瓣|片|勺|碗|杯|"
    "盒|包|袋|罐|块|条|把|株|朵|粒|头|g|L"
)
_DECIMAL = r"\d+(?:\.\d+)?"
_QUANTITY = rf"(?:{_DECIMAL}(?:\s*[-～~]\s*{_DECIMAL})?|[半一二三四五六七八九十两几]+)"
_INGREDIENT_QUANTITY_RE = re.compile(
    rf"({_QUANTITY})\s*({_INGREDIENT_QUANTITY_UNITS})"
    rf"(?:(?:\s*\+\s*{_DECIMAL}\s*(?:{_INGREDIENT_QUANTITY_UNITS}))+(?=\s*(?:[（(]|$)))?"
)
_TRAILING_QUANTITY_RE = re.compile(rf"\s*({_DECIMAL})(?:\s*[-～~])?\s*$")
_OPTIONAL_INGREDIENT_RE = re.compile(r"\[?可选\]?|二选一")
_INGREDIENT_ALTERNATIVE_RE = re.compile(r"and/or|\s+or\s+|或者|或|(?<!\d)/(?!\d)", re.IGNORECASE)
_CALC_ALTERNATIVE_RE = re.compile(r"/(?=\s*[^\d\s/][^：:/]*[：:])")
_CALC_PROSE_PREFIXES = ("每次制作前", "每份", "总量", "使用上述条件", "一份正好够", "以上")
_CALC_NAME_SUFFIX_RE = re.compile(r"(?:的数量|的用量为|的用量|用量为|用量|数量|量)$")
_SEASONING_TERMS = (
    "盐", "糖", "酱油", "醋", "料酒", "油", "胡椒", "花椒", "八角", "桂皮", "香叶",
    "生抽", "老抽", "蚝油", "味精", "鸡精", "淀粉", "葱", "姜", "蒜",
)


def _strip_ingredient_prefix(segment: str) -> tuple[str, bool]:
    """Strip list numbering and labels while tracking optional ingredients."""
    segment = re.sub(r"^(?:[①-⑩]|\d+[.)、](?!\d))\s*", "", segment.strip())
    optional = False
    while label := _LABEL_RE.match(segment):
        optional |= label[1] == "可选"
        segment = segment[label.end():]
    return segment, optional


def _tool_subject(segment: str) -> tuple[str, bool]:
    segment, optional = _strip_ingredient_prefix(segment.translate(_MARKDOWN_EMPHASIS))
    subject = _COLON_RE.split(segment, maxsplit=1)[0]
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


def _split_outside_notes(line: str, separators: str | re.Pattern) -> list[str]:
    """Split at separators outside parenthetical notes."""
    pattern = re.compile(f"[{re.escape(separators)}]") if isinstance(separators, str) else separators
    tokens = re.compile(r"[（()）]|" + pattern.pattern, pattern.flags)
    depth = start = 0
    segments = []
    for token in tokens.finditer(line):
        if token[0] in "(（":
            depth += 1
        elif token[0] in ")）":
            depth = max(0, depth - 1)
        elif not depth:
            segments.append(line[start:token.start()].strip())
            start = token.end()
    segments.append(line[start:].strip())
    return segments


def _ingredient_segments(line: str) -> list[str]:
    """Split top-level plus signs unless a segment starts with a quantity."""
    if "+" not in line:
        return [line]
    segments = _split_outside_notes(line, "+")
    if any(segment and segment[0].isdigit() for segment in segments):
        return [line]
    return segments


def _is_explanatory_line(line: str) -> bool:
    body, _ = _bracket_parts(line)
    if _SENTENCE_PUNCTUATION_RE.search(body):
        return True
    parts = re.split(r"[，,]", body)
    return len(parts) > 1 and len(body.strip()) > 30 and any(len(part.strip()) > 10 for part in parts)


def _ingredient_text(segment: str, explanatory: bool) -> tuple[str, str | None, bool] | None:
    """Return ingredient text and an optional name override, skipping headings and prose."""
    plain = segment.translate(_MARKDOWN_EMPHASIS)
    stripped, _ = _strip_ingredient_prefix(plain)
    body, _ = _bracket_parts(stripped)
    body = body.strip()
    if (not body and _bracket_parts(plain)[0].strip()) or body.rstrip("：:").strip() == "原料":
        return None

    ingredient, _ = _strip_ingredient_prefix(segment)
    parts = _COLON_RE.split(body, maxsplit=1)
    if len(parts) == 2 and (name := parts[0].strip()):
        if _COLON_RE.split(stripped, maxsplit=1)[1].strip() == "可选":
            return ingredient, name, True
        if len(name) <= 8:
            description = parts[1]
            if "、" not in description or _SENTENCE_PUNCTUATION_RE.search(description):
                return ingredient, name, False
            return ingredient, None, False
    return (ingredient, None, False) if ingredient and not explanatory else None


def _basic_note_alternative(note: str) -> bool:
    # Remove appliance names before testing standalone basic-tool mentions.
    # In particular, the 锅 in 电饭锅 or 锅胆 is not an alternative.
    text = _SPECIAL_RE.sub(" ", note)
    if any(len(term) > 1 and term in text for term in BASIC_TOOL_TERMS):
        return True
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


def _lines_outside_notes(text: str) -> Iterator[str]:
    """Skip tips subheadings and everything nested under them."""
    notes_level = 0
    for line in text.splitlines():
        heading = re.match(r"^(#{3,6})\s+(.+)", line.strip())
        if heading:
            level = len(heading[1])
            if not notes_level or level <= notes_level:
                notes_level = level if re.search(r"附加|小贴士|技巧", heading[2]) else 0
        elif not notes_level:
            yield line


def _step_equipment(text: str) -> list[list[str]]:
    groups = []
    for line in _lines_outside_notes(text):
        step = _clean_line(line)
        if re.match(r"^(?:小贴士|附加内容)\s*[：:]", step):
            continue
        body, _ = _bracket_parts(step)
        for sentence in re.split(r"[。！？!?；;]", body):
            fallbacks = {match.end() for match in _STEP_FALLBACK_RE.finditer(sentence)}
            for tool in _SPECIAL_RE.finditer(sentence):
                if (
                    tool.end() not in fallbacks
                    and not _STEP_OPTION_BEFORE_RE.search(sentence[:tool.start()])
                    and not _STEP_OPTION_AFTER_RE.match(sentence[tool.end():])
                ):
                    groups.append([_SPECIAL_CODES[tool[0]]])
    return groups


def _merge_equipment(groups: list[list[str]]) -> list[list[str]]:
    required = {group[0] for group in groups if len(group) == 1}
    return [
        list(group) for group in dict.fromkeys(map(tuple, groups))
        if len(group) == 1 or required.isdisjoint(group)
    ]


def _parse_ingredients(text: str) -> list[dict]:
    """Parse ingredient rows without the equipment metadata."""
    return _merge_ingredients(_parse_ingredient_section(text)[0], [])


def _parse_ingredient_section(text: str) -> tuple[list[dict], list[list[str]], list[str]]:
    """Split ingredients and equipment, then parse ingredients as before."""
    ingredients, groups, unclassified = [], [], []
    for raw_line in _lines_outside_notes(text):
        line = _clean_line(raw_line)
        plain = line.translate(_MARKDOWN_EMPHASIS).strip()
        content, line_optional = _strip_ingredient_prefix(plain)
        if not plain or plain.endswith(("：", ":")) or content.startswith(_INGREDIENT_PROSE_PREFIXES):
            continue

        category, *description = _COLON_RE.split(content, maxsplit=1)
        category = category.strip()
        if description and category == "其他" and "随便" in description[0]:
            continue
        category_list = bool(description and (category in _INGREDIENT_CATEGORIES or category.endswith("材料")))
        if category_list:
            if _CATEGORY_PROSE_RE.search(description[0]):
                continue
            segments = [
                segment
                for item in _split_outside_notes(description[0], "、，,")
                for segment in _ingredient_segments(item)
            ]
            explanatory = False
        else:
            line_optional = False
            segments = _ingredient_segments(line)
            explanatory = _is_explanatory_line(line)

        for segment in segments:
            if not segment:
                continue
            subject, optional = _tool_subject(segment)
            listed_tool = subject in _SPECIAL_CODES or subject in BASIC_TOOL_TERMS
            if listed_tool or (
                subject.endswith(TOOL_SUFFIXES) and subject not in INGREDIENT_EXCEPTIONS
            ):
                if not listed_tool:
                    unclassified.append(subject)
                groups.extend(_tool_groups(segment, optional or line_optional))
            else:
                ingredients.extend(_ingredient_items(segment, explanatory, optional or line_optional))

    return _dedupe_ingredients(ingredients), _merge_equipment(groups), unclassified


def _ingredient_items(segment: str, explanatory: bool, optional: bool) -> list[dict]:
    if _OPTIONAL_INGREDIENT_RE.search(segment):
        optional = True
    segment = segment.split("—", 1)[0].strip()
    if not (prepared := _ingredient_text(segment, explanatory)):
        return []
    line, name_override, optional_suffix = prepared
    if name_override is not None:
        row = _ingredient_row(line, name_override, optional or optional_suffix)
        return [row] if row else []

    rows = []
    for item in _split_outside_notes(line, "、，,"):
        for index, part in enumerate(_split_outside_notes(item, _INGREDIENT_ALTERNATIVE_RE)):
            if row := _ingredient_row(part, None, optional or index > 0):
                rows.append(row)
    return rows


def _ingredient_row(
    text: str, name: str | None = None, optional: bool = False, *, calculation: bool = False,
) -> dict | None:
    text = _EMOJI_RE.sub("", _OPTIONAL_INGREDIENT_RE.sub("", text).translate(_INGREDIENT_MARKUP)).strip()
    quantity_match = _INGREDIENT_QUANTITY_RE.search(text)
    quantity = quantity_match[1] if quantity_match else None
    unit = quantity_match[2] if quantity_match else None
    if name is None:
        name = text
        if calculation:
            # An assignment can express a per-serving formula or multiple people.
            sides = re.split(r"[=:：]", text, maxsplit=1)
            if len(sides) == 2:
                name, value = sides
                quantity_match = _INGREDIENT_QUANTITY_RE.search(value)
                quantity = quantity_match[1] if quantity_match else None
                unit = quantity_match[2] if quantity_match else None
                if quantity is None and re.fullmatch(_QUANTITY, value.strip()):
                    quantity = value.strip()
            elif quantity_match:
                name = text[:quantity_match.start()] + text[quantity_match.end():]
        elif quantity_match:
            name = text[:quantity_match.start()] + text[quantity_match.end():]
        if quantity is None and (trailing := _TRAILING_QUANTITY_RE.search(name)):
            quantity = trailing[1]
            name = name[:trailing.start()]

    name = _strip_bracket_notes(_EMOJI_RE.sub("", name.translate(_INGREDIENT_MARKUP)))
    name = name.strip(" \t=：:、，,；;")
    if calculation:
        name = _CALC_NAME_SUFFIX_RE.sub("", name).strip()
    if not any(char.isalpha() for char in name):
        return None
    return {
        "ingredient_name": name,
        "quantity": quantity,
        "unit": unit,
        "is_seasoning": any(term in name for term in _SEASONING_TERMS),
        "is_optional": optional,
        "sort_order": 0,
    }


def _parse_calculations(text: str) -> tuple[list[dict], list[str]]:
    rows, unparsed = [], []
    table_started = False
    for raw in _lines_outside_notes(text):
        raw = raw.lstrip()
        if raw.startswith("|"):
            cells = [cell.strip() for cell in raw.strip("|").split("|")]
            if not table_started:
                table_started = True
                continue
            if len(cells) < 2 or re.fullmatch(r":?-+:?", cells[0]):
                continue
            amount = cells[1]
            if len(cells) > 2 and re.fullmatch(_QUANTITY, amount):
                amount += " " + cells[2]
            line = f"{_clean_line(cells[0])} = {_clean_line(amount)}"
        else:
            table_started = False
            if not _LIST_MARKER_RE.match(raw):
                continue
            line = _clean_line(raw) or _LIST_MARKER_RE.sub("", raw, count=1).strip()

        plain, optional = _strip_ingredient_prefix(line.translate(_INGREDIENT_MARKUP))
        if (
            not plain or plain.startswith(_INGREDIENT_PROSE_PREFIXES + _CALC_PROSE_PREFIXES)
            or "→" in plain or ("份数" in plain and not _INGREDIENT_QUANTITY_RE.search(plain))
        ):
            continue
        category, *description = _COLON_RE.split(plain, maxsplit=1)
        category = category.strip()
        if description and (category in _INGREDIENT_CATEGORIES or category.endswith("材料")):
            if _CATEGORY_PROSE_RE.search(description[0]):
                continue
            segments = _split_outside_notes(description[0], "、，,")
        else:
            if not _ingredient_text(line, _is_explanatory_line(line)):
                continue
            segments = [plain]

        for segment in segments:
            for index, item in enumerate(_split_outside_notes(segment, _CALC_ALTERNATIVE_RE)):
                if row := _ingredient_row(item, optional=optional or index > 0, calculation=True):
                    rows.append(row)
                elif item:
                    unparsed.append(item)
    return _dedupe_ingredients(rows), unparsed


def _dedupe_ingredients(rows: list[dict]) -> list[dict]:
    seen = {}
    for row in rows:
        name = row["ingredient_name"]
        if name not in seen:
            seen[name] = {**row, "sort_order": len(seen)}
        elif row["quantity"] is not None:
            seen[name].update(quantity=row["quantity"], unit=row["unit"])
    return list(seen.values())


def _merge_ingredients(required: list[dict], computed: list[dict]) -> list[dict]:
    if not computed:
        return _dedupe_ingredients(required)
    from stock_manager.api.recipe_services import _normalize_name

    result = _dedupe_ingredients(required)
    exact = {row["ingredient_name"]: row for row in result}
    aliases = {}
    for row in result:
        aliases.setdefault(_normalize_name(row["ingredient_name"]), row)
    for row in _dedupe_ingredients(computed):
        name = row["ingredient_name"]
        match = exact.get(name) or aliases.get(_normalize_name(name))
        if match is not None:
            if row["quantity"] is not None:
                match.update(quantity=row["quantity"], unit=row["unit"])
        else:
            result.append({**row, "sort_order": len(result)})
    return result


def _is_nested_step(line: str) -> bool:
    indentation = line[:len(line) - len(line.lstrip(" 	"))]
    return "	" in indentation or len(indentation) >= 2


def _step_layout(text: str) -> tuple[list[str], list[tuple[int, int]]]:
    """Build steps and record the step before and after each source line."""
    lines = text.splitlines()
    list_positions = [index for index, line in enumerate(lines) if _LIST_MARKER_RE.match(line.lstrip())]
    has_lists = bool(list_positions)
    steps, anchors = [], []
    previous_blank = True
    in_subitem = False
    has_subitems = False
    for index, raw in enumerate(lines):
        previous = len(steps)
        line = _clean_line(raw)
        list_item = bool(_LIST_MARKER_RE.match(raw.lstrip()))
        nested = _is_nested_step(raw)
        if line:
            between_items = has_lists and list_positions[0] < index < list_positions[-1]
            standalone = has_lists and not list_item and not between_items and not (nested and in_subitem)
            if not steps or (list_item and not nested) or (not has_lists and previous_blank) or standalone:
                steps.append(line)
                in_subitem = has_subitems = False
            elif has_lists and nested and list_item:
                separator = "；" if has_subitems else ("" if steps[-1].endswith(("：", ":")) else "：")
                steps[-1] += separator + line
                in_subitem = has_subitems = True
            elif has_lists and not (nested and in_subitem):
                steps[-1] += "；" + line
                in_subitem = False
            else:
                steps[-1] += " " + line
        if not raw.strip():
            in_subitem = False
        previous_blank = not raw.strip()
        anchors.append((previous, len(steps)))
    return steps, anchors


def _parse_steps(text: str) -> list[dict]:
    instructions, _ = _step_layout(text)
    return [
        {"step_number": number, "instruction": instruction}
        for number, instruction in enumerate(instructions, start=1)
    ]


_PHOTO_REF = re.compile(rf"!\[([^\]]*)\]\(({_TARGET})\)")
_PHOTO_STATS = ("added", "updated", "removed", "missing", "remote_skipped")


def _photo_steps(markdown: str, step_numbers: list[int]) -> list[tuple[str, str, int | None]]:
    """Extract images with the same source-line grouping as the step parser."""
    lines = markdown.splitlines()
    start = stop = 0
    for index, line in enumerate(lines):
        if heading := re.match(r"^##\s+(.+)$", line):
            if start and not stop:
                stop = index
            if _section_kind(heading[1]) == "steps":
                start, stop = index + 1, 0
    if not stop:
        stop = len(lines)
    _, anchors = _step_layout("\n".join(lines[start:stop])) if start else ([], [])
    refs = []
    for index, line in enumerate(lines):
        for match in _PHOTO_REF.finditer(line):
            alt, path = match.groups()
            step = None
            if refs and start <= index < start + len(anchors) and "预览图" not in alt and "成品" not in alt:
                before, after = anchors[index - start]
                attached = after if _clean_line(line[:match.start()]) else before
                if 0 < attached <= len(step_numbers):
                    step = step_numbers[attached - 1]
            refs.append((alt, path.strip().removeprefix("<").removesuffix(">"), step))
    return refs


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
    from stock_manager.api.equipment_services import replace_recipe_equipment
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
    equipment_counts = Counter()
    recipes_with_equipment = group_count = 0
    unclassified_tools = []
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

                replace_recipe_equipment(session, recipe.id, recipe_data["equipment"])
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
        groups = recipe_data["equipment"]
        recipes_with_equipment += bool(groups)
        group_count += len(groups)
        equipment_counts.update(code for group in groups for code in group)
        unclassified_tools.extend((rel_path, term) for term in recipe_data["unclassified_tools"])
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
    per_code = ", ".join(f"{code} {equipment_counts[code]}" for code in EQUIPMENT_CODES)
    print(
        f"equipment: recipes {recipes_with_equipment}, groups {group_count}; "
        f"per code: {per_code}; unclassified tool lines {len(unclassified_tools)}"
    )
    for path, term in unclassified_tools:
        print(f"  ? {path}: {term}")
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
    from stock_manager.api.equipment_services import delete_recipe_equipment
    from stock_manager.api.photo_services import delete_recipe_photos

    ids = [r.id for r in rows]
    delete_recipe_equipment(session, ids)
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

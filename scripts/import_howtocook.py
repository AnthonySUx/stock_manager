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
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import asdict
from functools import lru_cache
import hashlib
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
_OVERRIDE_PATH = Path(__file__).with_name("howtocook_overrides.json")
_ALIASES_PATH = Path(__file__).with_name("howtocook_aliases.json")
_INGREDIENT_NAMES_PATH = Path(__file__).with_name("howtocook_ingredient_names.txt")


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


def parse_recipe_md(filepath: str, override: dict | None = None) -> dict:
    """Parse a HowToCook markdown file into structured recipe data.

    Expected structure:
    - Title (first H1)
    - "必备原料和工具" section
    - "计算" section (optional)
    - "操作步骤" section
    - "附加内容" (optional)
    """
    source = Path(filepath).read_bytes()
    content = source.decode("utf-8")

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
    ingredient_source = []
    equipment = [[code] for code in _special_codes(title)]
    for section, section_text in _recipe_sections(content):
        if section == "ingredients":
            ingredient_source.append(section_text)
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

    parsed = {
        "title": title,
        "category": category,
        "description": "",
        "difficulty": "",
        "servings": "",
        "cook_time_minutes": None,
        "ingredients": _merge_ingredients(ingredients, computed),
        "required_names": {row["ingredient_name"] for row in ingredients},
        "ingredient_source": "\n".join(ingredient_source),
        "calc_unparsed": calc_unparsed,
        "steps": steps,
        "equipment": _merge_equipment(equipment),
        "unclassified_tools": unclassified_tools,
        "raw_markdown": content,
        "source_sha256": hashlib.sha256(source).hexdigest(),
    }
    if override is not None:
        _apply_override(parsed, override)
    return parsed


def _load_overrides() -> dict:
    with _OVERRIDE_PATH.open(encoding="utf-8") as source:
        overrides = json.load(source)
    for path, override in overrides.items():
        if not isinstance(override.get("reason"), str) or not override["reason"].strip():
            raise RuntimeError(f"Missing override reason for {path}")
    return overrides


def _apply_override(recipe: dict, override: dict) -> None:
    if override["sha256"] != recipe["source_sha256"]:
        recipe["override_stale"] = True
        return
    normalized_source = _source_text(recipe["raw_markdown"])
    texts = list(override.get("steps", [])) + [row["ingredient_name"] for row in override.get("ingredients", [])]
    recipe["override_unverified"] = [
        text for text in texts if not (normalized := _source_text(text)) or normalized not in normalized_source
    ]
    if recipe["override_unverified"]:
        return
    for field in ("title", "equipment"):
        if field in override:
            recipe[field] = override[field]
    if "ingredients" in override:
        from stock_manager.api.recipe_schemas import IngredientSchema

        recipe["ingredients"] = [
            IngredientSchema(**{**row, "sort_order": index}).model_dump()
            for index, row in enumerate(override["ingredients"])
        ]
        recipe["calc_unparsed"] = []
    if "steps" in override:
        recipe["steps"] = [
            {"step_number": index, "instruction": instruction}
            for index, instruction in enumerate(override["steps"], start=1)
        ]


def _source_text(markdown: str) -> str:
    """Compare original wording after ignoring Markdown and display punctuation."""
    parts = []
    for line in markdown.splitlines():
        line = line.lstrip().lstrip(" >#").lstrip()
        line = _LIST_MARKER_RE.sub("", line, count=1)
        line = re.sub(r"^[①-⑳]|^【[^】]+】", "", line)
        line = _IMAGE_RE.sub("", line)
        line = _LINK_RE.sub(r"\1", line)
        parts.append("".join(char for char in line if char.isalnum()))
    return "".join(parts)


@lru_cache(maxsize=4)
def _load_aliases(path: Path) -> tuple[dict[str, set[str]], set[frozenset[str]]]:
    with path.open(encoding="utf-8") as source:
        pairs = json.load(source)
    same = {}
    for left, right in pairs["same"]:
        same.setdefault(left, set()).add(right)
        same.setdefault(right, set()).add(left)
    return same, {frozenset(pair) for pair in pairs["different"]}


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
_INGREDIENT_CATEGORIES = frozenset({"调味料", "主料", "辅料", "配料", "原料", "材料", "其他调味料", "全香料", "炒料"})
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
    "盒|包|袋|罐|块|条|把|株|朵|粒|头|份|两|瓶盖|瓶|片|小块|小段|拇指块|"
    "段|棵|叶|撮|滴|圈|卷|枚|张|节|扎|点|杯|cup|公分|厘米|毫米|小盒|g|L"
)
_DECIMAL = r"\d+(?:\.\d+)?"
_AMOUNT = rf"(?:{_DECIMAL}(?:\s+\d+/\d+|/\d+|[¼½¾⅓⅔⅛])?|[¼½¾⅓⅔⅛])"
_QUANTITY = rf"(?:{_AMOUNT}(?:\s*(?:[-–—～~]|到|至)\s*{_AMOUNT})?|[半一二三四五六七八九十两几]+)"
_INGREDIENT_QUANTITY_RE = re.compile(
    rf"({_QUANTITY})\s*({_INGREDIENT_QUANTITY_UNITS})"
    rf"(?:(?:\s*\+\s*{_DECIMAL}\s*(?:{_INGREDIENT_QUANTITY_UNITS}))+(?=\s*(?:[（(]|$)))?"
)
_TRAILING_QUANTITY_RE = re.compile(
    rf"\s*({_AMOUNT})(?:\s*[-～~]|\s*[x×*]\s*{_DECIMAL})?\s*$", re.IGNORECASE,
)
_TEMPERATURE_RE = re.compile(r"(?:约\s*)?\d+(?:\.\d+)?\s*(?:°\s*[CF]|[℃℉])", re.IGNORECASE)
_INGREDIENT_COMMENT_RE = re.compile(r"\s+#.*$")
_CALC_ANNOTATION_RE = re.compile(
    r"^(?:根据|按照|该配方|基于|如果|视|取决于|具体|可以|也可|若|实际|约|最|没有|只需|参考|"
    r"切|拍|去壳|去皮|去籽|备用|长度|直径|条状|品牌|即可|推荐|中断|煮沸|总计|大概|多一点|每|"
    r"此分量|可根据|到达|参见|米粥能够|冷藏时间|油的质量|浓度|煲汤盅|带皮$|一般|取|作为主食|作为小食|按\s*\d+\s*人)"
)
_CALC_UNIT_CONTEXT_RE = re.compile(r"\s*/\s*(?:per\b|[一二三四五六七八九十\d]*人|份)(?=$|[、，,。；;\s])", re.IGNORECASE)
_INGREDIENT_NUMBER_PREFIX_RE = re.compile(r"^\d+\s*[:：]\s*\d+\s*")

_OPTIONAL_INGREDIENT_RE = re.compile(r"\[?可选\]?|二选一")
_INGREDIENT_ALTERNATIVE_RE = re.compile(r"and/or|\s+or\s+|或者|或|(?<!\d)/(?!\d)", re.IGNORECASE)
_CALC_PROSE_PREFIXES = ("每次制作前", "每份", "总量", "使用上述条件", "一份正好够", "以上")
_CALC_NAME_SUFFIX_RE = re.compile(r"(?:的数量|的用量为|的用量|用量为|用量|数量|量)$")
_INGREDIENT_PROSE_RE = re.compile(
    r"建议|可以|即可|按照|根据|口味|备用|切开|切段|准备|大小|左右|用于|用量|注|必须|进阶|方法|"
    r"都可以|减半|取整|搭配|总共|差不多|依次|忽略|本教程|份数|[¼½¾⅓⅔⅛]|cup", re.IGNORECASE,
)
_INGREDIENT_PROSE_WORDS = frozenset("个 各 调 料 袋 份 只 根 片 块 勺 克".split())
_TOOL_INGREDIENT_SUFFIXES = ("袋", "模具", "容器", "筷子", "一双")
_CALC_NOTES_RE = re.compile(
    r"^(?:男人$|女人$|按人|提前|方便|然后|正常|中间|看锅|此处|和味精|适量$|约$|"
    r"整锅|以正常|必选配料|实测|该步骤|推荐合计|淹过|比拳头|用猪骨也|向上取整|"
    r"非黑暗料理|带皮$|一般$|其中青菜|调一个|单人(?:$|[，,])|腌制.*部分$|(?:蒸|焖|煮|炒|烤).{0,6}(?:用水|用油)$)"
)


def _is_ingredient_prose(name: str) -> bool:
    return name in _INGREDIENT_PROSE_WORDS or bool(_INGREDIENT_PROSE_RE.search(name))


def _is_ingredient_tool(name: str) -> bool:
    return name != "袋泡红茶" and (
        name == "研杵" or name.endswith(_TOOL_INGREDIENT_SUFFIXES) or "燃气灶" in name or "锅用水" in name
    )


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
    segment, optional = _strip_ingredient_prefix(segment.translate(_INGREDIENT_MARKUP))
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
        if (
            not plain or plain.endswith(("：", ":"))
            or content.startswith(_INGREDIENT_PROSE_PREFIXES + ("该配方", "其余配菜例如"))
        ):
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
            # Capacity and shape descriptions can precede a generic container.
            body, _ = _bracket_parts(segment)
            if re.match(r"^(?:一个|容器)?容量", body) and body.rstrip().endswith("容器"):
                subject = "容器"
            listed_tool = subject in _SPECIAL_CODES or subject in BASIC_TOOL_TERMS
            if listed_tool or _is_ingredient_tool(subject) or (
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
        return [row] if row and not (_is_ingredient_tool(row["ingredient_name"])
                                    or _is_ingredient_prose(row["ingredient_name"])) else []

    rows = []
    for item in _split_outside_notes(line, "、，,"):
        if item.startswith(("参见", "详见")):
            continue
        for index, part in enumerate(_split_outside_notes(item, _INGREDIENT_ALTERNATIVE_RE)):
            if row := _ingredient_row(part, None, optional or index > 0):
                name = row["ingredient_name"]
                if not (_is_ingredient_tool(name) or _is_ingredient_prose(name)):
                    rows.append(row)
    return rows


def _ingredient_row(
    text: str, name: str | None = None, optional: bool = False,
) -> dict | None:
    text = _EMOJI_RE.sub("", _OPTIONAL_INGREDIENT_RE.sub("", text).translate(_INGREDIENT_MARKUP)).strip()
    text = _INGREDIENT_COMMENT_RE.sub("", text)
    text = _TEMPERATURE_RE.sub("", text).strip()
    outer, _ = _bracket_parts(text)
    quantity_match = _INGREDIENT_QUANTITY_RE.search(text)
    if not _INGREDIENT_QUANTITY_RE.search(outer):
        quantity_match = next(
            (match for match in _INGREDIENT_QUANTITY_RE.finditer(text) if match[1][0].isascii()),
            quantity_match,
        )
    quantity = quantity_match[1] if quantity_match else None
    unit = quantity_match[2] if quantity_match else None
    if name is None:
        if outer_match := _INGREDIENT_QUANTITY_RE.search(outer):
            before = outer[:outer_match.start()].strip(" \t=：:、，,；;～~-±")
            after = outer[outer_match.end():].strip()
            if before:
                # Quantified ingredient lines often continue with handling notes.
                name = re.sub(r"\s*(?:大约|约为|约|至少|不少于|大概)\s*$", "", before)
            else:
                name = after or _strip_bracket_notes(text.replace(outer_match[0], "", 1))
            number_list = re.search(rf"({_AMOUNT})\s*\+\s*$", name)
            if number_list and before:
                name = name[:number_list.start()]
            quantity, unit = outer_match[1], outer_match[2]
            if number_list:
                quantity = f"{number_list[1]} + {quantity}"
        else:
            name = outer if any(char.isalpha() for char in outer) else text
            if quantity is None and (trailing := _TRAILING_QUANTITY_RE.search(name)):
                quantity = trailing[1]
                name = name[:trailing.start()]

    name = _strip_bracket_notes(_EMOJI_RE.sub("", name.translate(_INGREDIENT_MARKUP)))
    name = re.sub(r"\s+品牌(?:不限|自选).*$|足够涂满.*$", "", name)
    name = name.strip(" \t=：:、，,；;。()-（）")
    if name.startswith("新鲜") and len(name) > 2:
        name = name[2:].strip()
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


def _valid_calculation_name(name: str) -> bool:
    return (
        0 < len(name) <= 12
        and any(char.isalpha() for char in name)
        and not (_is_ingredient_prose(name) or _is_ingredient_tool(name) or _CALC_NOTES_RE.match(name))
        and not re.search(r"[0-9]", name)
        and not _INGREDIENT_PUNCT_RE.search(name)
    )


def _calculation_item(text: str, optional: bool) -> list[dict]:
    # Parenthetical notes can hold a quantity but never supply a separate item.
    body, notes = _bracket_parts(text)
    body = _INGREDIENT_NUMBER_PREFIX_RE.sub("", _TEMPERATURE_RE.sub("", _EMOJI_RE.sub("", body))).strip()
    first = _INGREDIENT_QUANTITY_RE.search(body)
    separator = re.search(r"[=:：]", body)
    boundaries = [match.start() for match in (first, separator) if match]
    end = min(boundaries, default=len(body))
    name_text = body[:end]
    quantity = first or next(
        (match for note in notes if (match := _INGREDIENT_QUANTITY_RE.search(note))), None,
    )
    # A quoted quantity or a decimal before a count delimiter can still
    # express a single amount (for example, 干辣椒 = 5，6 个).
    if first and separator and (bare := re.fullmatch(r"\s*(\d+)\s*[，,]\s*", body[end + 1:first.start()])):
        if row := _ingredient_row(f"{name_text} {bare[1]}-{first[0]}", optional=optional):
            return [row] if _valid_calculation_name(row["ingredient_name"]) else []
    name_text = name_text.strip(" \t、，,=:：")
    names = _split_outside_notes(name_text, "、，,")
    alternatives = [
        (part, index > 0)
        for name in names
        for index, part in enumerate(_split_outside_notes(name, _INGREDIENT_ALTERNATIVE_RE))
    ]
    cleaned = []
    for name, alternate in alternatives:
        name = re.sub(r"注\s*$|用量通常来说为.*$|足够涂满.*$|总共\s*$", "", name)
        name = re.sub(r"(?:总量|共)$", "", name.strip())
        if quantity and quantity[1].startswith("半"):
            name = re.sub(r"[大小]$", "", name)
        name = _CALC_NAME_SUFFIX_RE.sub("", name.strip()).strip()
        if name == "盐量":
            name = "盐"
        name = re.sub(r"\s*(?:大约|约为|约|至少|左右|各)\s*$", "", name)
        name = name.split(maxsplit=1)[0] if name.split() else ""
        # The previous step calculated a name only. A quantity at the end
        # without a unit still belongs to that name.
        row = _ingredient_row(name, optional=optional or alternate)
        cleaned.append(row)
    if any(row is None or not _valid_calculation_name(row["ingredient_name"]) for row in cleaned):
        named = name_text.split(maxsplit=1)[0] if name_text.split() else ""
        primary, *notes = _split_outside_notes(name_text, "、，,")
        if notes and all(_CALC_NOTES_RE.match(note) or _CALC_ANNOTATION_RE.match(note) for note in notes):
            named = primary.strip().split(maxsplit=1)[0] if primary.strip() else ""
        row = _ingredient_row(named, optional=optional)
        cleaned = [row] if row and _valid_calculation_name(row["ingredient_name"]) else []
    if not cleaned:
        return []
    if quantity and not (
        separator is None and re.search(r"\s+(?:建议|按照|根据|可以|如果|正常)", name_text)
    ):
        for row in cleaned:
            row.update(quantity=quantity[1], unit=quantity[2])
    elif separator:
        amount = body[separator.end():].strip()
        if re.fullmatch(_QUANTITY, amount):
            for row in cleaned:
                row["quantity"] = amount
    return cleaned


def _parse_calculations(text: str) -> tuple[list[dict], list[str]]:
    rows, unparsed = [], []
    table_started = False
    lines = list(_lines_outside_notes(text))
    for index, raw in enumerate(lines):
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
            if not _LIST_MARKER_RE.match(raw) or _HORIZONTAL_RULE_RE.fullmatch(raw.replace(" ", "")):
                continue
            marker = _LIST_MARKER_RE.match(raw)
            item = raw[marker.end():]
            if re.fullmatch(r"\*\*[^*]+\*\*|__[^_]+__", item) and any(
                _is_nested_step(next_line) and _LIST_MARKER_RE.match(next_line.lstrip())
                for next_line in lines[index + 1:index + 2]
            ):
                continue
            line = _clean_line(raw) or item.strip()

        # An asterisk between a named factor or amount and a number is
        # multiplication in this section, even though asterisks also mark emphasis.
        formula = re.sub(r"(?<=\w)\s*\*\s*(?=\d)", " × ", line)
        plain, optional = _strip_ingredient_prefix(formula.translate(_INGREDIENT_MARKUP))
        if (
            not plain or plain.startswith(_INGREDIENT_PROSE_PREFIXES + _CALC_PROSE_PREFIXES)
            or _CALC_ANNOTATION_RE.match(plain)
            or _CALC_NOTES_RE.match(plain)
            or _CALC_NOTES_RE.match(_bracket_parts(plain)[0].strip())
            or plain.endswith(("：", ":"))
            or _bracket_parts(plain)[0].strip() in {"必须配料", "进阶配料", "配料", "调料", "其他调料", "调味品", "蘸料"}
            or re.match(r"^其他调料(?:\s|$)|^鸡[一二三四五六七八九十]+到.+人的量", plain)
            or "→" in plain or ("份数" in plain and not _INGREDIENT_QUANTITY_RE.search(plain))
            or re.match(rf"^{_QUANTITY}\s*(?:{_INGREDIENT_QUANTITY_UNITS})\s*=", plain)
            or re.match(r"^\d+\s*人\s*\d+\s*顿", plain)
        ):
            continue
        category, *description = _COLON_RE.split(plain, maxsplit=1)
        category = category.strip()
        if description and (category in _INGREDIENT_CATEGORIES or category.endswith("材料")
                            or category in {"调料", "蘸料", "香料包"}):
            if _CATEGORY_PROSE_RE.search(description[0].rstrip("。")):
                continue
            segments = _split_outside_notes(description[0].rstrip("。"), "、，,")
        else:
            if not _ingredient_text(line, _is_explanatory_line(line)):
                continue
            segments = [plain]

        for segment in segments:
            segment = _CALC_UNIT_CONTEXT_RE.sub("", segment)
            segment = re.sub(r"^方法[一二三四五六七八九十\d]+[：:]\s*", "", segment)
            # A slash starts a new ingredient only when directly followed by
            # another named assignment. Formula suffixes stay with the first.
            line_items = _split_outside_notes(segment, re.compile(r"/(?=\s*[^\d\s/][^：:=,/、，]*[：:])"))
            for index, item in enumerate(line_items):
                if not item or _CALC_ANNOTATION_RE.match(item) or _tool_subject(item)[0] in BASIC_TOOL_TERMS:
                    continue
                if _is_ingredient_tool(_tool_subject(item)[0]):
                    continue
                item_rows = _calculation_item(
                    item, optional or index > 0 or bool(_OPTIONAL_INGREDIENT_RE.search(item)),
                )
                if item_rows:
                    rows.extend(item_rows)
                else:
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
    from stock_manager.api.recipe_services import _normalize_name

    same, different = _load_aliases(_ALIASES_PATH)

    def explicit_match(name: str, rows: list[dict]) -> dict | None:
        return next(
            (row for row in rows if row["ingredient_name"] == name
             or row["ingredient_name"] in same.get(name, ())),
            None,
        )

    result = []
    for row in _dedupe_ingredients(required):
        prior = explicit_match(row["ingredient_name"], result)
        if prior is None:
            result.append({**row, "sort_order": len(result)})
        elif prior["quantity"] is None and row["quantity"] is not None:
            prior.update(quantity=row["quantity"], unit=row["unit"])
    required_rows = list(result)
    for row in _dedupe_ingredients(computed):
        name = row["ingredient_name"]
        match = explicit_match(name, result)
        if match is None:
            normalized = _normalize_name(name)
            match = next(
                (candidate for candidate in required_rows
                 if frozenset((name, candidate["ingredient_name"])) not in different
                 and _normalize_name(candidate["ingredient_name"]) == normalized),
                None,
            )
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
    pending_heading = ""
    for index, raw in enumerate(lines):
        previous = len(steps)
        if heading := re.match(r"^\s*###\s+(.+)$", raw):
            pending_heading = _clean_line(heading[1])
            in_subitem = has_subitems = False
            anchors.append((previous, previous))
            continue
        line = _clean_line(raw)
        list_item = bool(_LIST_MARKER_RE.match(raw.lstrip()))
        nested = _is_nested_step(raw)
        if line:
            between_items = has_lists and list_positions[0] < index < list_positions[-1]
            standalone = has_lists and not list_item and not between_items and not (nested and in_subitem)
            if raw.lstrip().startswith(">") and steps and not pending_heading:
                steps[-1] += "；" + line
            elif pending_heading or not steps or (list_item and not nested) or (not has_lists and previous_blank) or standalone:
                steps.append(f"【{pending_heading}】{line}" if pending_heading else line)
                pending_heading = ""
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
    try:
        md_files = _recipe_files(howtocook_dir)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print(f"Found {len(md_files)} recipe files")

    from stock_manager.api import media
    from stock_manager.api.equipment_services import replace_recipe_equipment
    from stock_manager.api.models import Recipe, RecipeIngredient, RecipeStep

    if with_photos or prune_non_recipes:
        media.reload_config()
    if with_photos and not media.available():
        raise RuntimeError("MEDIA_DIR is required with --with-photos")

    overrides = _load_overrides()
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
    for md_file in md_files:
        rel_path = str(md_file.relative_to(howtocook_dir))
        with media.file_transaction(enabled=with_photos):
            stored_hashes = set()
            old_hashes = set()
            try:
                recipe_data = parse_recipe_md(str(md_file), overrides.get(md_file.relative_to(howtocook_dir).as_posix()))
                if recipe_data.get("override_stale"):
                    print(f"  ⚠ {rel_path}: override_stale (source SHA-256 differs)")
                if recipe_data.get("override_unverified"):
                    print(f"  ⚠ {rel_path}: override_text_not_in_source")
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


_INGREDIENT_FIELDS = (
    "ingredient_name", "normalized_name", "quantity", "unit", "is_seasoning", "is_optional", "sort_order",
)


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
    wanted = [tuple(p.get(f) for f in _INGREDIENT_FIELDS) for p in parsed]
    if as_rows == wanted:
        return False
    for ing in current:
        session.delete(ing)
    session.flush()
    for p in parsed:
        session.add(RecipeIngredient(recipe_id=recipe.id, **{f: p.get(f) for f in _INGREDIENT_FIELDS}))
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


_ERROR_CODES = (
    "ingredient_markup", "ingredient_punct", "ingredient_digit", "ingredient_long",
    "ingredient_duplicate", "step_markup", "step_empty", "recipe_empty", "calc_unparsed", "override_stale",
    "ingredient_prose", "ingredient_tool", "ingredient_unknown", "ingredient_maybe_duplicate",
    "override_text_not_in_source",
)
_WARNING_CODES = (
    "ingredient_no_quantity", "equipment_mentioned_not_required", "step_count_changed",
)
_INGREDIENT_PUNCT_RE = re.compile(r"[：:、，,；;。（）()/或]|\s+or\s+", re.IGNORECASE)
_STEP_MARKUP_RE = re.compile(r"\*\*|`|!\[|\]\(|<[a-zA-Z]")


def _recipe_files(root: Path) -> list[Path]:
    dishes = root / "dishes"
    if not root.is_dir():
        raise RuntimeError(f"{root} is not a directory")
    if not dishes.is_dir():
        raise RuntimeError(f"{dishes} not found (expected the HowToCook repository root)")
    return sorted(path for path in dishes.rglob("*.md") if is_recipe_path(path.relative_to(root)))


def _audit_recipe(recipe: dict, vocabulary: set[str] | None = None) -> Iterator[tuple[str, str]]:
    ingredients, steps = recipe["ingredients"], recipe["steps"]
    names = set()
    original = recipe.get("ingredient_source", "").translate(_INGREDIENT_MARKUP)
    same, different = _load_aliases(_ALIASES_PATH)
    if not ingredients or not steps:
        missing = ", ".join(label for label, rows in (("ingredients", ingredients), ("steps", steps)) if not rows)
        yield "recipe_empty", f"Missing {missing}"
    for row in ingredients:
        name = row["ingredient_name"]
        if re.search(r"[*`\[\]#]", name) or _EMOJI_RE.search(name):
            yield "ingredient_markup", name
        if _INGREDIENT_PUNCT_RE.search(name):
            yield "ingredient_punct", name
        if re.search(r"[0-9]", name):
            yield "ingredient_digit", name
        if len(name) > 12:
            yield "ingredient_long", name
        if name in names:
            yield "ingredient_duplicate", name
        names.add(name)
        if _is_ingredient_prose(name):
            yield "ingredient_prose", name
        if _is_ingredient_tool(name):
            yield "ingredient_tool", name
        if vocabulary is not None and name not in vocabulary and name not in original:
            yield "ingredient_unknown", name
        if not row["quantity"]:
            yield "ingredient_no_quantity", name

    for inner in sorted(names, key=lambda name: (len(name), name)):
        if len(inner) < 2:
            continue
        for outer in sorted(names):
            if (len(outer) > len(inner) and inner in outer
                    and outer not in same.get(inner, ()) and frozenset((inner, outer)) not in different):
                yield "ingredient_maybe_duplicate", f"{inner} / {outer}"

    for step in steps:
        instruction = step["instruction"]
        detail = f'{step["step_number"]}: {instruction}'
        if _STEP_MARKUP_RE.search(instruction):
            yield "step_markup", detail
        if not _clean_line(re.sub(r"^【[^】]+】", "", instruction)):
            yield "step_empty", detail

    for line in recipe.get("calc_unparsed", []):
        yield "calc_unparsed", line
    for text in recipe.get("override_unverified", []):
        yield "override_text_not_in_source", text
    if recipe.get("override_stale"):
        yield "override_stale", "Override SHA-256 does not match the source"

    raw = recipe["raw_markdown"]
    required = {code for group in recipe["equipment"] for code in group}
    for code in catalog_order(set(_special_codes(raw)) - required):
        yield "equipment_mentioned_not_required", code
    operation = ""
    for kind, text in _recipe_sections(raw):
        if kind == "steps":
            operation = text
    top_level = sum(
        bool(_LIST_MARKER_RE.match(line.lstrip())) and not _is_nested_step(line)
        for line in operation.splitlines()
    )
    if top_level != len(steps):
        yield "step_count_changed", f"{top_level} source list items → {len(steps)} steps"


def _report_cell(value) -> str:
    return str(value if value is not None else "").replace("|", r"\|").replace("\n", "<br>")


def _write_review(report: Path, reviewed: list[tuple[str, dict, list[tuple[str, str]]]]) -> None:
    with report.open("w", encoding="utf-8") as output:
        print("# HowToCook import review\n", file=output)
        for path, recipe, issues in reviewed:
            print(f'## {recipe["title"]}\n', file=output)
            print(f'- Category: {recipe["category"]}\n- Source: `{path}`', file=output)
            print(f'- SHA-256: `{recipe["source_sha256"]}`\n', file=output)
            print("### Ingredients\n\n| Name | Quantity | Unit | Seasoning | Optional |", file=output)
            print("| --- | --- | --- | --- | --- |", file=output)
            for row in recipe["ingredients"]:
                cells = (
                    row["ingredient_name"], row["quantity"], row["unit"],
                    "Yes" if row["is_seasoning"] else "No", "Yes" if row["is_optional"] else "No",
                )
                print("| " + " | ".join(map(_report_cell, cells)) + " |", file=output)
            print("\n### Steps\n", file=output)
            for step in recipe["steps"]:
                print(f'{step["step_number"]}. {step["instruction"]}', file=output)
            print("\n### Equipment groups\n", file=output)
            for group in recipe["equipment"]:
                print("- " + " / ".join(group), file=output)
            print("\n### Photos\n", file=output)
            photos = _photo_steps(recipe["raw_markdown"], [step["step_number"] for step in recipe["steps"]])
            for index, (label, reference, step) in enumerate(photos):
                location = f"Step {step}" if step else ("Cover" if not index else "Recipe")
                print(f"- {location}: {label} (`{reference}`)", file=output)
            print("\n### Warnings and errors\n", file=output)
            for code, detail in issues:
                print(f"- `{code}`: {detail}", file=output)
            # Include the source for line-by-line verification of joins and omissions.
            print("\n<details><summary>Source Markdown</summary>\n\n~~~~markdown", file=output)
            print(recipe["raw_markdown"].rstrip(), file=output)
            print("~~~~\n\n</details>\n", file=output)


def audit_howtocook(root: Path, report: Path | None = None) -> int:
    """Review the local Markdown and return a failing status for audit errors."""
    counts = Counter()
    reviewed = []
    ingredient_total = quantified = multi_ingredient = 0
    overrides = _load_overrides()
    from stock_manager.api.recipe_services import SYNONYM_MAP

    vocabulary = set(SYNONYM_MAP) | {alias for names in SYNONYM_MAP.values() for alias in names}
    with _INGREDIENT_NAMES_PATH.open(encoding="utf-8") as names:
        vocabulary.update(name for line in names if (name := line.strip()) and not name.startswith("#"))
    parsed = []
    for file in _recipe_files(root):
        path = file.relative_to(root).as_posix()
        recipe = parse_recipe_md(str(file), overrides.get(path))
        parsed.append((path, recipe))
        vocabulary.update(recipe["required_names"])
    for path, recipe in parsed:
        issues = list(_audit_recipe(recipe, vocabulary))
        counts.update(code for code, _ in issues)
        reviewed.append((path, recipe, issues))
        ingredient_total += len(recipe["ingredients"])
        quantified += sum(row["quantity"] is not None for row in recipe["ingredients"])
        multi_ingredient += sum(
            bool(re.search(r"[、，,或/]|\s+or\s+", row["ingredient_name"], re.IGNORECASE))
            for row in recipe["ingredients"]
        )

    errors = sum(counts[code] for code in _ERROR_CODES)
    warnings = sum(counts[code] for code in _WARNING_CODES)
    for codes in (_ERROR_CODES, _WARNING_CODES):
        for code in codes:
            print(f"{code}: {counts[code]}")
    print(f"Totals: errors {errors}, warnings {warnings}, recipes {len(reviewed)}")
    print(f"Ingredients: {ingredient_total}, with quantity {quantified}, multi-ingredient {multi_ingredient}")
    for path, _, issues in reviewed:
        for code, detail in issues:
            print(f"{code}  {path}  {detail}")
    if report is not None:
        _write_review(report, reviewed)
    return int(bool(errors))


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
    parser.add_argument("--audit", action="store_true", help="Review parsed recipes without a database")
    parser.add_argument("--report", type=Path, help="Write a Markdown review when auditing")
    args = parser.parse_args()
    if args.report and not args.audit:
        parser.error("--report requires --audit")
    if args.audit:
        try:
            sys.exit(audit_howtocook(Path(args.howtocook_path), args.report))
        except (RuntimeError, OSError) as exc:
            parser.exit(1, f"Error: {exc}\n")
    _load_env()
    try:
        import_howtocook(
            args.howtocook_path, args.db_url, args.prune_non_recipes, with_photos=args.with_photos,
        )
    except RuntimeError as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()

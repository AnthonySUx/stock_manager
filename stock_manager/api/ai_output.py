"""Validation of AI output for Explore / Expand (#65).

The prompt asks; this module enforces. Nothing the model returns reaches the
client without passing through here:

- user-facing text must be in the request locale (no mixed languages);
- machine fields are fixed English enums;
- quantities are numbers (or a locale "to taste" word) and units come from a
  per-locale list or from the matching stock item;
- ingredient names that match inventory (synonyms included) are replaced by
  the stock item's exact name, and matched / expiring / missing lists are
  recomputed from the inventory that was sent.
"""
import re
from dataclasses import dataclass, field as dc_field
from typing import Optional, get_args

from stock_manager.api.localization import LANGUAGE_NAMES
from stock_manager.api.quantity import normalize_unit, parse_quantity
from stock_manager.api.recipe_schemas import CookingMethod, CuisineGroup, Difficulty, RecipeCategory

COOKING_METHODS: tuple[str, ...] = get_args(CookingMethod)
CUISINE_GROUPS: tuple[str, ...] = get_args(CuisineGroup)
DIFFICULTIES: tuple[str, ...] = get_args(Difficulty)
RECIPE_CATEGORIES: tuple[str, ...] = get_args(RecipeCategory)

# Units the AI may use, per locale, as written in that locale.
UNITS: dict[str, tuple[str, ...]] = {
    "zh-CN": ("克", "千克", "毫升", "升", "个", "只", "颗", "根", "片", "瓣", "块", "把", "汤匙", "茶匙", "杯"),
    "en": ("g", "kg", "ml", "l", "pcs", "tbsp", "tsp", "cup", "clove", "slice"),
    "ja": ("g", "kg", "ml", "l", "個", "本", "枚", "かけ", "大さじ", "小さじ", "カップ", "束", "パック"),
}

# Quantities that are not numbers. The unit is cleared for these.
TO_TASTE: dict[str, tuple[str, ...]] = {
    "zh-CN": ("适量", "少许"),
    "en": ("to taste",),
    "ja": ("適量", "少々"),
}

_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿ｦ-ﾟ]")
_KANA_RE = re.compile(r"[぀-ヿｦ-ﾟ]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+")
_LETTER_RE = re.compile(r"[^\W\d_]")
# Latin tokens allowed inside Chinese / Japanese text: units and °C / °F.
_ALLOWED_LATIN = {"g", "kg", "mg", "ml", "l", "cm", "mm", "c", "f"}


def warning(code: str, **params) -> dict:
    return {"code": code, "params": {k: str(v) for k, v in params.items()}}


def dedupe_warnings(warnings: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for w in warnings:
        key = (w["code"], tuple(sorted(w["params"].items())))
        if key not in seen:
            seen.add(key)
            result.append(w)
    return result


def text_or_none(value) -> Optional[str]:
    """A trimmed string for scalar AI output, otherwise None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def positive_int_or_none(value) -> Optional[int]:
    """An int > 0 from an int or a digit string; otherwise None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().isascii() and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int) and value > 0:
        return value
    return None


# ─── Inventory ───────────────────────────────────────────────────


class Inventory:
    """The inventory sent to the AI, for name matching and units."""

    def __init__(self, items: list[dict]):
        from stock_manager.api.recipe_services import _normalize_name

        self._normalize = _normalize_name
        self.items = [i for i in items if text_or_none(i.get("name"))]
        self._by_key: dict[str, dict] = {}
        for item in self.items:
            for key in self._keys(item["name"]):
                self._by_key.setdefault(key, item)
        # Longest first, so "番茄酱" is removed before "番茄".
        self.names = sorted({i["name"].strip() for i in self.items}, key=len, reverse=True)

    def _keys(self, name: str) -> set[str]:
        text = (name or "").strip()
        if not text:
            return set()
        return {text.lower(), self._normalize(text).lower()}

    def match(self, name: Optional[str]) -> Optional[dict]:
        """The stock item this name refers to (exact or synonym), or None."""
        for key in self._keys(name or ""):
            if key in self._by_key:
                return self._by_key[key]
        return None

    def without_names(self, text: str) -> str:
        """`text` with inventory names removed (they are copied verbatim and
        may be in any language)."""
        for name in self.names:
            text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
        return text


# ─── Language ────────────────────────────────────────────────────


def in_locale(text: Optional[str], locale: str, inventory: Inventory) -> bool:
    """True when `text` is written in `locale`.

    Inventory names are ignored. Text with no letters left (digits, symbols)
    passes.
    - zh-CN / ja: contains CJK; Latin words only for units (g, ml, °C).
      zh-CN additionally rejects Japanese kana.
    - en: no CJK at all.
    """
    if not text:
        return True
    rest = inventory.without_names(text)
    if not _LETTER_RE.search(rest):
        return True
    if locale == "en":
        return not _CJK_RE.search(rest)
    if not _CJK_RE.search(rest):
        return False
    if locale == "zh-CN" and _KANA_RE.search(rest):
        return False
    return all(word.lower() in _ALLOWED_LATIN for word in _LATIN_WORD_RE.findall(rest))


def clean_text_list(values, field: str, locale: str, inventory: Inventory, warnings: list[dict]) -> list[str]:
    """Strings in `values` that are in the locale; others are dropped."""
    result = []
    if not isinstance(values, list):
        return result
    for value in values:
        text = text_or_none(value) if isinstance(value, str) else None
        if text is None:
            continue
        if not in_locale(text, locale, inventory):
            warnings.append(warning("field_value_dropped", field=field, value=text[:50]))
            continue
        if text not in result:
            result.append(text)
    return result


def clean_enum(value, allowed: tuple[str, ...], field: str, warnings: list[dict]) -> Optional[str]:
    """`value` if it is one of `allowed` (case-insensitive), else None."""
    text = text_or_none(value)
    if text is None:
        return None
    key = text.lower().replace("-", "_").replace(" ", "_")
    if key in allowed:
        return key
    warnings.append(warning("field_value_dropped", field=field, value=text[:50]))
    return None


# ─── Quantities ──────────────────────────────────────────────────


def _format_number(number: float) -> str:
    return f"{number:g}"


def clean_quantity(
    quantity, unit, locale: str, stock_unit: Optional[str]
) -> tuple[Optional[str], Optional[str], bool]:
    """Return (quantity, unit, ok).

    `ok` is False when the AI gave a quantity or unit that cannot be used; the
    caller then clears both and adds `quantity_dropped`.
    """
    qty_text = text_or_none(quantity)
    unit_text = text_or_none(unit)
    if qty_text is None:
        return None, None, unit_text is None
    to_taste = TO_TASTE.get(locale, ())
    if qty_text.lower() in to_taste:
        return qty_text.lower() if locale == "en" else qty_text, None, True

    number, parsed_unit = parse_quantity(qty_text, unit_text)
    if number is None or number <= 0:
        return None, None, False
    if parsed_unit is None:
        if unit_text is not None:
            return None, None, False  # the text and the unit field disagree
        return _format_number(number), None, True

    if stock_unit and normalize_unit(parsed_unit) == normalize_unit(stock_unit):
        return _format_number(number), stock_unit, True
    allowed = {normalize_unit(u): u for u in UNITS.get(locale, ())}
    canonical = normalize_unit(parsed_unit)
    if canonical in allowed:
        return _format_number(number), allowed[canonical], True
    return None, None, False


# ─── Explore ideas ───────────────────────────────────────────────


def _quote(text: str) -> str:
    return '"' + text[:80] + '"'


def clean_idea(
    raw,
    locale: str,
    inventory: Inventory,
    warnings: list[dict],
    problems: Optional[list[str]] = None,
    position: int = 0,
) -> Optional[dict]:
    """A validated idea dict, or None (with a warning) when it is unusable.

    When an idea is dropped, a description of what is wrong is added to
    `problems`; Explore sends it back to the model to fix (#65).
    """
    problems = problems if problems is not None else []
    language = LANGUAGE_NAMES[locale]
    if not isinstance(raw, dict):
        warnings.append(warning("idea_dropped_malformed"))
        problems.append(f"Idea #{position}: not a JSON object.")
        return None
    title = text_or_none(raw.get("title"))
    list_fields = ("matched_ingredients", "expiring_ingredients", "missing_ingredients", "flavors", "textures")
    bad_lists = [f for f in list_fields if raw.get(f) is not None and not isinstance(raw.get(f), list)]
    if title is None or bad_lists:
        warnings.append(warning("idea_dropped_malformed"))
        if title is None:
            problems.append(f"Idea #{position}: missing title.")
        for field in bad_lists:
            problems.append(f"Idea #{position}: {field} must be a list of strings.")
        return None
    description = text_or_none(raw.get("description"))
    reason = text_or_none(raw.get("reason"))
    wrong = [(f, t) for f, t in (("title", title), ("description", description), ("reason", reason))
             if not in_locale(t, locale, inventory)]
    if wrong:
        warnings.append(warning("idea_dropped_wrong_language", title=title[:50]))
        for field, text in wrong:
            problems.append(f"Idea #{position} {field} {_quote(text)} is not in {language}.")
        return None

    cuisine = text_or_none(raw.get("cuisine"))
    if cuisine and not in_locale(cuisine, locale, inventory):
        warnings.append(warning("field_value_dropped", field="cuisine", value=cuisine[:50]))
        cuisine = None

    # The model's own lists are only hints: the backend decides what the user
    # has, through the inventory that was actually sent.
    claimed = []
    for field in ("matched_ingredients", "expiring_ingredients", "missing_ingredients"):
        values = raw.get(field)
        if isinstance(values, list):
            claimed.extend(v for v in values if isinstance(v, str))
    matched, expiring, missing_raw = [], [], []
    for name in claimed:
        item = inventory.match(name)
        if item is None:
            missing_raw.append(name)
            continue
        if item["name"] not in matched:
            matched.append(item["name"])
        if item.get("status") == "expiring soon" and item["name"] not in expiring:
            expiring.append(item["name"])
    missing = clean_text_list(missing_raw, "missing_ingredients", locale, inventory, warnings)

    return {
        "title": title,
        "description": description,
        # Only the backend may link an idea to a local recipe (#66 part 6).
        "source_type": "ai_idea",
        "recipe_id": None,
        "matched_ingredients": matched,
        "expiring_ingredients": expiring,
        "missing_ingredients": missing,
        "flavors": clean_text_list(raw.get("flavors"), "flavors", locale, inventory, warnings),
        "textures": clean_text_list(raw.get("textures"), "textures", locale, inventory, warnings),
        "cuisine_group": clean_enum(raw.get("cuisine_group"), CUISINE_GROUPS, "cuisine_group", warnings),
        "cuisine": cuisine,
        "cooking_method": clean_enum(raw.get("cooking_method"), COOKING_METHODS, "cooking_method", warnings),
        "estimated_time_minutes": positive_int_or_none(raw.get("estimated_time_minutes")),
        "reason": reason,
        "can_expand_to_recipe": True,
    }


# ─── Expand draft ────────────────────────────────────────────────


@dataclass
class DraftResult:
    """The outcome of validating one Expand reply.

    - `draft` is None when the reply cannot be used at all (not an object, no
      title, no usable step, or text in the wrong language).
    - `problems` lists what the model should fix, in English, for a repair
      round. It is non-empty whenever `draft` is None, and also when a
      quantity or unit had to be cleared.
    """
    draft: Optional[dict]
    warnings: list[dict] = dc_field(default_factory=list)
    problems: list[str] = dc_field(default_factory=list)


def clean_draft(data, idea: dict, locale: str, inventory: Inventory) -> DraftResult:
    """Validate one Expand reply (see DraftResult)."""
    language = LANGUAGE_NAMES[locale]
    units = ", ".join(UNITS[locale])
    to_taste = " / ".join(TO_TASTE[locale])
    if not isinstance(data, dict):
        return DraftResult(None, [], ["The reply must be one JSON object with title, ingredients and steps."])
    warnings: list[dict] = [warning("draft_ai_generated")]
    problems: list[str] = []
    fatal = False

    def check_language(label: str, text: Optional[str]) -> None:
        nonlocal fatal
        if not in_locale(text, locale, inventory):
            fatal = True
            problems.append(f"{label} {_quote(text)} is not in {language}.")

    title = text_or_none(data.get("title")) or text_or_none(idea.get("title"))
    if title is None:
        fatal = True
        problems.append("title is missing.")
    check_language("title", title)
    description = text_or_none(data.get("description"))
    check_language("description", description)

    ingredients = []
    raw_ingredients = data.get("ingredients")
    for position, raw in enumerate(raw_ingredients if isinstance(raw_ingredients, list) else [], 1):
        name = text_or_none(raw.get("ingredient_name") or raw.get("name")) if isinstance(raw, dict) else None
        if name is None:
            warnings.append(warning("ingredient_dropped_malformed", index=position))
            continue
        item = inventory.match(name)
        if item is not None:
            name = item["name"]  # the exact stock name, so cooking matches it
        else:
            check_language(f"ingredients[{position}].ingredient_name", name)
        quantity, unit, ok = clean_quantity(
            raw.get("quantity"), raw.get("unit"), locale, item.get("unit") if item else None
        )
        if not ok:
            warnings.append(warning("quantity_dropped", ingredient=name))
            problems.append(
                f"ingredients[{position}] {_quote(name)}: quantity {_quote(str(raw.get('quantity')))} "
                f"with unit {_quote(str(raw.get('unit')))} is not allowed. Use one number and one of: "
                f"{units}; or exactly {to_taste} with no unit."
            )
        ingredients.append({
            "ingredient_name": name,
            "normalized_name": None,
            "quantity": quantity,
            "unit": unit,
            "is_optional": raw.get("is_optional") is True,
            "is_seasoning": raw.get("is_seasoning") is True,
            "sort_order": len(ingredients),
        })

    steps = []
    raw_steps = data.get("steps")
    for position, raw in enumerate(raw_steps if isinstance(raw_steps, list) else [], 1):
        if isinstance(raw, dict):
            instruction = text_or_none(raw.get("instruction") or raw.get("description") or raw.get("text"))
        else:
            instruction = text_or_none(raw) if isinstance(raw, str) else None
        if instruction is None:
            warnings.append(warning("step_dropped_malformed", index=position))
            continue
        check_language(f"steps[{position}].instruction", instruction)
        steps.append({"step_number": len(steps) + 1, "instruction": instruction})
    if not steps:
        fatal = True
        problems.append('steps is empty: give at least one {"step_number", "instruction"}.')

    category = text_or_none(data.get("category"))
    if category is not None and category not in RECIPE_CATEGORIES:
        warnings.append(warning("field_value_dropped", field="category", value=category[:50]))
        problems.append(f"category {_quote(category)} must be one of: {', '.join(RECIPE_CATEGORIES)}.")
        category = None

    servings = text_or_none(data.get("servings"))
    if servings is not None:
        count = positive_int_or_none(servings)
        if count is not None:
            servings = str(count)
        elif servings.isdigit() or len(servings) > 50 or not in_locale(servings, locale, inventory):
            warnings.append(warning("field_value_dropped", field="servings", value=servings[:50]))
            problems.append(f"servings {_quote(servings)} must be a whole number of people.")
            servings = None

    difficulty_warnings: list[dict] = []
    difficulty = clean_enum(data.get("difficulty"), DIFFICULTIES, "difficulty", difficulty_warnings)
    if difficulty_warnings:
        warnings.extend(difficulty_warnings)
        problems.append(
            f"difficulty {_quote(str(data.get('difficulty')))} must be one of: {', '.join(DIFFICULTIES)}."
        )

    cook_time = data.get("cook_time_minutes")
    cook_time = positive_int_or_none(cook_time) or positive_int_or_none(idea.get("estimated_time_minutes"))

    if fatal:
        return DraftResult(None, [], problems)
    draft = {
        "title": title,
        "category": category,
        "description": description,
        "difficulty": difficulty,
        "servings": servings,
        "cook_time_minutes": cook_time,
        "raw_markdown": None,
        "ingredients": ingredients,
        "steps": steps,
    }
    return DraftResult(draft, dedupe_warnings(warnings), problems)


def needs_repair(result: DraftResult) -> bool:
    """A repair round is worth its tokens when the draft is unusable or a
    quantity was lost. Wrong enums / servings are only cleared."""
    if result.draft is None:
        return True
    return any(w["code"] == "quantity_dropped" for w in result.warnings)

"""Explore Recipes service - generates cooking ideas via AI.

Supports both structured preferences and natural language input.
Both modes are converted into an AI prompt that generates idea candidates.
"""
import logging
from typing import Optional
from uuid import uuid4

from stock_manager.api.ai_client import AIUpstreamError, chat_json

logger = logging.getLogger(__name__)


def _recipe_category_values() -> tuple[str, ...]:
    from typing import get_args
    from stock_manager.api.recipe_schemas import RecipeCategory
    return get_args(RecipeCategory)


_RECIPE_CATEGORIES = _recipe_category_values()


def _build_explore_prompt(inventory_items: list[dict], structured: Optional[dict], natural_language: Optional[str]) -> tuple[str, str]:
    system = (
        "You are a creative cooking assistant for a family stock management app. "
        "Your task is to suggest cooking ideas based on available ingredients and user preferences.\n\n"
        "RULES:\n"
        "1. Suggest 5-8 different cooking ideas.\n"
        "2. Each idea must include a title, short description, and explanation.\n"
        "3. Prioritize using ingredients nearing expiration.\n"
        "4. Mark each idea as 'ai_idea' (new) or 'existing_recipe' (known dish).\n"
        "5. List which ingredients are used and which are missing.\n"
        "6. Do NOT claim the user has ingredients not listed.\n"
        "7. Output ONLY valid JSON.\n\n"
        "OUTPUT FORMAT:\n"
        "```json\n"
        "{\n"
        '  "ideas": [\n'
        "    {\n"
        '      "title": "Dish Name",\n'
        '      "description": "Short description",\n'
        '      "source_type": "ai_idea",\n'
        '      "matched_ingredients": [],\n'
        '      "expiring_ingredients": [],\n'
        '      "missing_ingredients": [],\n'
        '      "flavors": [],\n'
        '      "textures": [],\n'
        '      "cuisine_group": "chinese",\n'
        '      "cooking_method": "stir_fry",\n'
        '      "estimated_time_minutes": 15,\n'
        '      "reason": "Why this idea fits."\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```"
    )

    parts = []
    if inventory_items:
        lines = []
        for item in inventory_items:
            exp = " (EXPIRING SOON)" if item.get("status") == "expiring soon" else ""
            lines.append(f"- {item['name']} x {item.get('quantity', '?')} {item.get('unit', '')}{exp}")
        parts.append("Current inventory:\n" + "\n".join(lines))

    if structured:
        s = structured
        prefs = []
        if s.get("flavors"):
            prefs.append(f"Flavors: {', '.join(s['flavors'])}")
        if s.get("textures"):
            prefs.append(f"Textures: {', '.join(s['textures'])}")
        if s.get("cuisine_group"):
            prefs.append(f"Cuisine group: {s['cuisine_group']}")
        if s.get("cuisine"):
            prefs.append(f"Cuisine: {s['cuisine']}")
        if s.get("cooking_methods"):
            prefs.append(f"Cooking methods: {', '.join(s['cooking_methods'])}")
        if s.get("max_time_minutes"):
            prefs.append(f"Max time: {s['max_time_minutes']} minutes")
        if s.get("extra_ingredients"):
            prefs.append(f"Additional: {', '.join(s['extra_ingredients'])}")
        if prefs:
            parts.append("User preferences:\n" + "\n".join(prefs))

    if natural_language:
        parts.append(f"User request:\n{natural_language}")

    user = "\n\n".join(parts) + "\n\nPlease suggest cooking ideas based on the above."
    return system, user


def _extract_ideas(data) -> list[dict]:
    """Valid ideas from the parsed AI reply ({"ideas": [...]} or a bare list).

    Malformed ideas are dropped (#45). Raises AIUpstreamError when nothing
    usable is left, so the client gets 502 and can retry (#66).
    """
    if isinstance(data, list):
        ideas = data
    elif isinstance(data, dict):
        ideas = data.get("ideas", [])
    else:
        ideas = []
    if not isinstance(ideas, list):
        ideas = []

    from pydantic import ValidationError
    from stock_manager.api.recipe_schemas import ExploreIdea

    validated = []
    for idea in ideas:
        if not isinstance(idea, dict) or not idea.get("title"):
            continue
        idea.setdefault("source_type", "ai_idea")
        idea.setdefault("matched_ingredients", [])
        idea.setdefault("expiring_ingredients", [])
        idea.setdefault("missing_ingredients", [])
        idea.setdefault("flavors", [])
        idea.setdefault("textures", [])
        idea.setdefault("estimated_time_minutes", None)
        idea.setdefault("reason", "")
        idea.setdefault("cuisine_group", None)
        idea.setdefault("cuisine", None)
        idea.setdefault("cooking_method", None)
        try:
            # Drop ideas whose fields have the wrong types instead of failing
            # response validation with a 500.
            ExploreIdea(**idea)
        except (ValidationError, TypeError):
            logger.warning("Skipping malformed explore idea: %r", idea.get("title"))
            continue
        validated.append(idea)

    if not validated:
        raise AIUpstreamError("AI reply contained no usable ideas")
    return validated


async def explore_ideas(inventory_items: list[dict], structured: Optional[dict] = None, natural_language: Optional[str] = None) -> dict:
    """Cooking ideas from the AI. Raises AIUnavailableError / AIUpstreamError."""
    input_mode = "structured" if structured else "natural_language"
    system_prompt, user_prompt = _build_explore_prompt(inventory_items, structured, natural_language)
    ideas = _extract_ideas(await chat_json(system_prompt, user_prompt))
    for idea in ideas:
        idea["idea_id"] = str(uuid4())[:8]
    return {"mode": "ai", "input_mode": input_mode, "ideas": ideas, "warnings": []}


async def expand_to_recipe_draft(idea: dict) -> dict:
    """A recipe draft for one idea. Raises AIUnavailableError / AIUpstreamError."""
    system = (
        "You are a cooking assistant. "
        "Expand a cooking idea into a structured recipe.\n\n"
        "RULES:\n"
        "1. Estimate realistic ingredient quantities for 2 servings.\n"
        "2. Include clear step-by-step instructions.\n"
        "3. Set category to exactly one of: " + ", ".join(_RECIPE_CATEGORIES) + ".\n"
        "4. Output ONLY valid JSON.\n\n"
        "OUTPUT FORMAT:\n"
        "```json\n"
        "{\n"
        '  "title": "Dish Name",\n'
        '  "category": "meat_dish",\n'
        '  "description": "Description",\n'
        '  "difficulty": "easy",\n'
        '  "servings": "2 servings",\n'
        '  "cook_time_minutes": 30,\n'
        '  "ingredients": [{"ingredient_name": "item", "quantity": "2", "unit": "pieces"}],\n'
        '  "steps": [{"step_number": 1, "instruction": "Step description"}]\n'
        "}\n"
        "```"
    )
    user = (
        f"Idea: {idea.get('title', '')}\n"
        f"Description: {idea.get('description', '')}\n"
        f"Matched ingredients: {', '.join(idea.get('matched_ingredients', []))}\n"
        f"Flavors: {', '.join(idea.get('flavors', []))}\n"
        f"Cooking method: {idea.get('cooking_method', '')}\n"
        f"Estimated time: {idea.get('estimated_time_minutes', '')} minutes\n\n"
        "Please expand this into a complete recipe."
    )

    data = await chat_json(system, user)
    if not isinstance(data, dict):
        # Valid JSON but not a recipe object (e.g. a list): nothing to show.
        # There is no fallback draft any more (#66); the client offers a retry.
        raise AIUpstreamError("AI reply is not a recipe object")
    return {
        "recipe_draft": _normalize_recipe_draft(
            data,
            idea,
            warning="This is an AI-generated recipe draft. Please confirm ingredients and steps before saving.",
        )
    }


def _text_or_none(value) -> Optional[str]:
    """Return a trimmed string for AI scalar output, otherwise None."""
    if value is None:
        return None
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        text = str(value).strip()
        return text or None
    return None


def _normalize_recipe_draft(data: dict, idea: dict, warning: str) -> dict:
    """Convert unpredictable AI JSON into a stable RecipeCreate-compatible draft."""
    raw_ingredients = data.get("ingredients")
    ingredients = []
    if isinstance(raw_ingredients, list):
        for index, raw in enumerate(raw_ingredients):
            if not isinstance(raw, dict):
                continue
            name = _text_or_none(raw.get("ingredient_name") or raw.get("name"))
            if not name:
                continue
            ingredients.append(
                {
                    "ingredient_name": name,
                    "normalized_name": _text_or_none(raw.get("normalized_name")),
                    "quantity": _text_or_none(raw.get("quantity")),
                    "unit": _text_or_none(raw.get("unit")),
                    "is_optional": raw.get("is_optional") is True,
                    "is_seasoning": raw.get("is_seasoning") is True,
                    "sort_order": index,
                }
            )

    raw_steps = data.get("steps")
    steps = []
    if isinstance(raw_steps, list):
        for index, raw in enumerate(raw_steps):
            if not isinstance(raw, dict):
                continue
            instruction = _text_or_none(
                raw.get("instruction") or raw.get("description") or raw.get("text")
            )
            if not instruction:
                continue
            number = raw.get("step_number")
            if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
                number = index + 1
            steps.append({"step_number": number, "instruction": instruction})

    category = data.get("category")
    if category not in _RECIPE_CATEGORIES:
        category = None
    cook_time = data.get("cook_time_minutes")
    if not isinstance(cook_time, int) or isinstance(cook_time, bool) or cook_time < 0:
        cook_time = idea.get("estimated_time_minutes")
    if not isinstance(cook_time, int) or isinstance(cook_time, bool) or cook_time < 0:
        cook_time = 30

    return {
        "title": _text_or_none(data.get("title"))
        or _text_or_none(idea.get("title"))
        or "",
        "category": category,
        "description": _text_or_none(data.get("description"))
        or _text_or_none(idea.get("description")),
        "difficulty": _text_or_none(data.get("difficulty")) or "medium",
        "servings": _text_or_none(data.get("servings")) or "2 servings",
        "cook_time_minutes": cook_time,
        "raw_markdown": _text_or_none(data.get("raw_markdown")),
        "ingredients": ingredients,
        "steps": steps,
        "warnings": [warning],
    }

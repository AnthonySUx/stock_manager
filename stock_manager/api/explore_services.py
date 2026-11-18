"""Explore Recipes service - generates cooking ideas via AI.

Supports both structured preferences and natural language input.
Both modes are converted into an AI prompt that generates idea candidates.
"""
import asyncio
import json
import logging
from typing import Optional
from uuid import uuid4

from stock_manager.api import ai_client
from stock_manager.api.ai_client import AIUpstreamError, chat_json
from stock_manager.api.ai_output import (
    COOKING_METHODS,
    CUISINE_GROUPS,
    DIFFICULTIES,
    RECIPE_CATEGORIES,
    TO_TASTE,
    UNITS,
    Inventory,
    clean_draft,
    clean_idea,
    dedupe_warnings,
    needs_repair,
)
from stock_manager.api.localization import LANGUAGE_NAMES

logger = logging.getLogger(__name__)


# The same rules the backend checks (ai_output.in_locale), stated up front so
# the first reply usually passes (#65).
_SCRIPT_RULES = {
    "zh-CN": "Use Chinese characters. Do not use Japanese kana. Do not use Latin letters, "
             "except unit symbols such as g, kg, ml and °C.",
    "ja": "Use Japanese. Do not use Latin letters, except unit symbols such as g, kg, ml and °C.",
    "en": "Do not use Chinese or Japanese characters.",
}


def _language_rules(locale: str) -> str:
    language = LANGUAGE_NAMES[locale]
    return (
        f"LANGUAGE: Write every user-facing text in {language} only. {_SCRIPT_RULES[locale]} "
        "Do not mix languages and do not add translations in brackets.\n"
        "INVENTORY NAMES: when you use an ingredient from the inventory, copy its name exactly "
        "as listed, whatever language it is in (this is the only exception to the language rule).\n"
        "ENUM FIELDS keep the exact English values listed below; never translate them.\n"
    )


def _feedback(problems: list[str], instruction: str) -> str:
    """The repair request sent after a reply that failed validation."""
    lines = "\n".join(f"- {p}" for p in problems)
    return f"Your reply has these problems:\n{lines}\n\n{instruction}"


def _repair_messages(previous_reply, feedback: str) -> list[dict]:
    return [
        {"role": "assistant", "content": json.dumps(previous_reply, ensure_ascii=False)},
        {"role": "user", "content": feedback},
    ]


# Explore asks for a repair when fewer usable ideas than this are left.
MIN_IDEAS = 3


def _inventory_lines(inventory_items: list[dict]) -> list[str]:
    lines = []
    for item in inventory_items:
        exp = " (EXPIRING SOON)" if item.get("status") == "expiring soon" else ""
        lines.append(f"- {item['name']} x {item.get('quantity', '?')} {item.get('unit', '')}{exp}")
    return lines


def _build_explore_prompt(
    inventory_items: list[dict],
    structured: Optional[dict],
    natural_language: Optional[str],
    locale: str = "zh-CN",
) -> tuple[str, str]:
    language = LANGUAGE_NAMES[locale]
    system = (
        "You are a creative cooking assistant for a family stock management app. "
        "Your task is to suggest cooking ideas based on available ingredients and user preferences.\n\n"
        + _language_rules(locale)
        + "\nRULES:\n"
        "1. Suggest 5-8 different cooking ideas.\n"
        "2. Each idea must include a title, short description, and reason.\n"
        "3. Prioritize using ingredients nearing expiration.\n"
        "4. matched_ingredients: inventory names you use, copied exactly. "
        "missing_ingredients: other ingredients the dish needs.\n"
        "5. Do NOT claim the user has ingredients not listed.\n"
        f"6. cooking_method must be one of: {', '.join(COOKING_METHODS)}.\n"
        f"7. cuisine_group must be one of: {', '.join(CUISINE_GROUPS)}.\n"
        f"8. flavors, textures and cuisine are short words in {language}.\n"
        "9. estimated_time_minutes is a whole number.\n"
        "10. Output ONLY valid JSON.\n\n"
        "OUTPUT FORMAT:\n"
        "```json\n"
        + json.dumps(
            {"ideas": [{
                "title": f"<dish name in {language}>",
                "description": f"<one sentence in {language}>",
                "matched_ingredients": ["<inventory name>"],
                "missing_ingredients": [f"<ingredient in {language}>"],
                "flavors": [f"<word in {language}>"],
                "textures": [f"<word in {language}>"],
                "cuisine_group": "chinese",
                "cuisine": f"<cuisine in {language}>",
                "cooking_method": "stir_fry",
                "estimated_time_minutes": 15,
                "reason": f"<why this fits, in {language}>",
            }]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n```"
    )

    parts = []
    if inventory_items:
        parts.append("Current inventory:\n" + "\n".join(_inventory_lines(inventory_items)))

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

    user = "\n\n".join(parts) + f"\n\nPlease suggest cooking ideas based on the above, in {language}."
    return system, user


def _extract_ideas(data, locale: str, inventory: Inventory) -> tuple[list[dict], list[dict], list[str]]:
    """Valid ideas from the parsed AI reply ({"ideas": [...]} or a bare list),
    plus warnings and the problems of the dropped ideas (for a repair round).

    Malformed ideas and ideas in the wrong language are dropped (#45, #65).
    """
    if isinstance(data, list):
        ideas = data
    elif isinstance(data, dict):
        ideas = data.get("ideas", [])
    else:
        ideas = []
    if not isinstance(ideas, list):
        ideas = []

    warnings: list[dict] = []
    problems: list[str] = []
    validated = []
    for position, raw in enumerate(ideas, 1):
        idea = clean_idea(raw, locale, inventory, warnings, problems, position)
        if idea is not None:
            validated.append(idea)
    if not ideas:
        problems.append('The reply must be {"ideas": [...]} with at least one idea.')
    return validated, warnings, problems


def _is_drop_warning(w: dict) -> bool:
    return w["code"] in ("idea_dropped_malformed", "idea_dropped_wrong_language")


async def explore_ideas(
    inventory_items: list[dict],
    structured: Optional[dict] = None,
    natural_language: Optional[str] = None,
    locale: str = "zh-CN",
    warnings: Optional[list[dict]] = None,
) -> dict:
    """Cooking ideas from the AI. Raises AIUnavailableError / AIUpstreamError.

    When fewer than MIN_IDEAS ideas pass validation, the dropped ideas and
    what is wrong with them are sent back once for repair (#65). Both rounds
    share the per-call time budget; if the repair fails, the ideas from the
    first round are returned. With no usable idea at all: 502.
    """
    input_mode = "structured" if structured else "natural_language"
    system_prompt, user_prompt = _build_explore_prompt(inventory_items, structured, natural_language, locale)
    inventory = Inventory(inventory_items)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + ai_client.get_config().text_total_timeout

    first = await chat_json(system_prompt, user_prompt)
    ideas, idea_warnings, problems = _extract_ideas(first, locale, inventory)

    if len(ideas) < MIN_IDEAS and problems:
        feedback = _feedback(
            problems,
            'Reply with {"ideas": [...]} containing corrected versions of only the ideas listed '
            "above, in the same format. Do not repeat the ideas that had no problems.",
        )
        try:
            repaired = await asyncio.wait_for(
                chat_json(system_prompt, user_prompt, followup=_repair_messages(first, feedback)),
                max(deadline - loop.time(), 0.001),
            )
            more, more_warnings, _ = _extract_ideas(repaired, locale, inventory)
            seen = {i["title"] for i in ideas}
            for idea in more:
                if idea["title"] not in seen:
                    seen.add(idea["title"])
                    ideas.append(idea)
            # Drop warnings now come from the repair round only.
            idea_warnings = [w for w in idea_warnings if not _is_drop_warning(w)] + more_warnings
        except (AIUpstreamError, asyncio.TimeoutError) as exc:
            logger.warning("Explore repair round failed: %s", exc)

    if not ideas:
        raise AIUpstreamError("AI reply contained no usable ideas")
    for idea in ideas:
        idea["idea_id"] = str(uuid4())[:8]
    return {
        "mode": "ai",
        "input_mode": input_mode,
        "locale": locale,
        "ideas": ideas,
        "warnings": dedupe_warnings(list(warnings or []) + idea_warnings),
    }


def _build_expand_prompt(idea: dict, inventory_items: list[dict], locale: str) -> tuple[str, str]:
    language = LANGUAGE_NAMES[locale]
    units = ", ".join(UNITS[locale])
    to_taste = " / ".join(TO_TASTE[locale])
    system = (
        "You are a cooking assistant. Expand a cooking idea into a structured recipe.\n\n"
        + _language_rules(locale)
        + "\nRULES:\n"
        "1. Estimate realistic ingredient quantities for 2 servings.\n"
        "2. Include clear step-by-step instructions.\n"
        f"3. category must be exactly one of: {', '.join(RECIPE_CATEGORIES)}.\n"
        f"4. difficulty must be one of: {', '.join(DIFFICULTIES)}.\n"
        f"5. quantity is a single number such as \"2\" or \"0.5\" (no ranges, no fractions), "
        f"or exactly \"{to_taste}\" when it cannot be measured.\n"
        f"6. unit is one of: {units}. For an inventory ingredient you may instead use its "
        "inventory unit. Leave unit empty for \"to taste\" quantities.\n"
        "7. Mark seasonings with is_seasoning and optional ingredients with is_optional.\n"
        "8. servings is a whole number of people.\n"
        "9. Output ONLY valid JSON.\n\n"
        "OUTPUT FORMAT:\n"
        "```json\n"
        + json.dumps(
            {
                "title": f"<dish name in {language}>",
                "category": "vegetable_dish",
                "description": f"<one sentence in {language}>",
                "difficulty": "easy",
                "servings": 2,
                "cook_time_minutes": 30,
                "ingredients": [{
                    "ingredient_name": "<inventory name, or a name in " + language + ">",
                    "quantity": "2",
                    "unit": UNITS[locale][0],
                    "is_seasoning": False,
                    "is_optional": False,
                }],
                "steps": [{"step_number": 1, "instruction": f"<step in {language}>"}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n```"
    )
    parts = []
    if inventory_items:
        lines = [f"- {i['name']} (unit: {i.get('unit') or '-'})" for i in inventory_items]
        parts.append("Inventory (copy these names exactly when used):\n" + "\n".join(lines))
    parts.append(
        f"Idea: {idea.get('title', '')}\n"
        f"Description: {idea.get('description') or ''}\n"
        f"Matched ingredients: {', '.join(idea.get('matched_ingredients') or [])}\n"
        f"Missing ingredients: {', '.join(idea.get('missing_ingredients') or [])}\n"
        f"Flavors: {', '.join(idea.get('flavors') or [])}\n"
        f"Cooking method: {idea.get('cooking_method') or ''}\n"
        f"Estimated time: {idea.get('estimated_time_minutes') or ''} minutes"
    )
    user = "\n\n".join(parts) + f"\n\nPlease expand this into a complete recipe, in {language}."
    return system, user


async def expand_to_recipe_draft(
    idea: dict,
    inventory_items: Optional[list[dict]] = None,
    locale: str = "zh-CN",
    warnings: Optional[list[dict]] = None,
) -> dict:
    """A recipe draft for one idea. Raises AIUnavailableError / AIUpstreamError.

    If the first draft is unusable (wrong language, no steps, not an object)
    or lost a quantity, the draft and a list of its problems are sent back
    once for repair (#65). Both rounds share the per-call time budget. The
    better of the usable drafts is returned (fewer problems; the repaired one
    on a tie); with no usable draft: 502. There is no fallback draft (#66).
    """
    inventory_items = inventory_items or []
    inventory = Inventory(inventory_items)
    system, user = _build_expand_prompt(idea, inventory_items, locale)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + ai_client.get_config().text_total_timeout

    first = await chat_json(system, user)
    results = [clean_draft(first, idea, locale, inventory)]
    if needs_repair(results[0]):
        feedback = _feedback(
            results[0].problems,
            "Fix these problems and reply with the complete corrected recipe JSON in the same "
            "format. Keep everything else unchanged.",
        )
        try:
            repaired = await asyncio.wait_for(
                chat_json(system, user, followup=_repair_messages(first, feedback)),
                max(deadline - loop.time(), 0.001),
            )
            results.append(clean_draft(repaired, idea, locale, inventory))
        except (AIUpstreamError, asyncio.TimeoutError) as exc:
            logger.warning("Expand repair round failed: %s", exc)

    usable = [r for r in results if r.draft is not None]
    if not usable:
        raise AIUpstreamError("AI draft was unusable")
    best = min(reversed(usable), key=lambda r: len(r.problems))
    return {
        "recipe_draft": best.draft,
        "locale": locale,
        "warnings": dedupe_warnings(list(warnings or []) + best.warnings),
    }

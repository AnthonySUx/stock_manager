"""Explore Recipes service - generates cooking ideas via AI.

Supports both structured preferences and natural language input.
Both modes are converted into an AI prompt that generates idea candidates.
"""
import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field as dc_field
from typing import AsyncIterator, Optional
from uuid import uuid4

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
from stock_manager.api.json_stream import ArrayItemStream
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
    """The model's previous reply (text, or parsed JSON) and the problems."""
    if not isinstance(previous_reply, str):
        previous_reply = json.dumps(previous_reply, ensure_ascii=False)
    return [
        {"role": "assistant", "content": previous_reply},
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


def _extract_ideas(data) -> list:
    """The raw idea list from a parsed reply ({"ideas": [...]} or a bare list)."""
    if isinstance(data, list):
        ideas = data
    elif isinstance(data, dict):
        ideas = data.get("ideas", [])
    else:
        ideas = []
    return ideas if isinstance(ideas, list) else []


def _summary(problems: list[str], limit: int = 5) -> str:
    """The first problems, for the server log when a request ends in 502."""
    if not problems:
        return "no details"
    more = len(problems) - limit
    return " | ".join(problems[:limit]) + (f" | (+{more} more)" if more > 0 else "")


def _is_drop_warning(w: dict) -> bool:
    return w["code"] in ("idea_dropped_malformed", "idea_dropped_wrong_language")


@dataclass
class _Round:
    """One AI call of Explore: what it said and what was wrong with it."""
    label: str
    warnings: list[dict] = dc_field(default_factory=list)
    problems: list[str] = dc_field(default_factory=list)
    text: str = ""
    error: Optional[AIUpstreamError] = None


async def _stream_round(
    system: str,
    user: str,
    followup: Optional[list[dict]],
    state: _Round,
    locale: str,
    inventory: Inventory,
    titles: set[str],
) -> AsyncIterator[dict]:
    """Yield each idea of one AI reply as soon as it is complete and valid.

    The reply text is cut into ideas while it streams (ArrayItemStream) and
    each one goes through clean_idea before it is yielded; invalid ideas only
    add to `state.problems`. When the reply does not have the expected shape,
    the whole parsed reply is validated at the end instead. A failed call is
    kept in `state.error` (ideas yielded before it stay valid).
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def call() -> None:
        try:
            result = await chat_json(
                system, user, followup=followup, label=state.label,
                on_text=lambda text: queue.put_nowait(("text", text)),
            )
            queue.put_nowait(("end", result))
        except Exception as exc:  # passed to the consumer below
            queue.put_nowait(("error", exc))

    parser = ArrayItemStream("ideas")
    parts: list[str] = []
    position = 0

    def accept(raw) -> Optional[dict]:
        nonlocal position
        position += 1
        idea = clean_idea(raw, locale, inventory, state.warnings, state.problems, position)
        if idea is None or idea["title"] in titles:
            return None
        titles.add(idea["title"])
        idea["idea_id"] = str(uuid4())[:8]
        return idea

    task = asyncio.create_task(call())
    try:
        while True:
            kind, value = await queue.get()
            if kind == "text":
                parts.append(value)
                for raw in parser.feed(value):
                    idea = accept(raw)
                    if idea is not None:
                        yield idea
                continue
            state.text = "".join(parts)
            if kind == "error":
                if not isinstance(value, AIUpstreamError):
                    raise value
                state.error = value
                return
            if not parser.found:
                # Unexpected shape (or the text never reached us): validate
                # the whole reply now.
                for raw in _extract_ideas(value):
                    idea = accept(raw)
                    if idea is not None:
                        yield idea
            if position == 0:
                state.problems.append('The reply must be {"ideas": [...]} with at least one idea.')
            if not state.text:
                state.text = json.dumps(value, ensure_ascii=False)
            return
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def explore_stream(
    inventory_items: list[dict],
    structured: Optional[dict] = None,
    natural_language: Optional[str] = None,
    locale: str = "zh-CN",
    warnings: Optional[list[dict]] = None,
) -> AsyncIterator[tuple[str, dict]]:
    """Cooking ideas from the AI, one at a time, each already validated.

    Yields ("idea", idea) for every idea that passed validation, as soon as
    the AI has written it, then one ("done", meta). Nothing unvalidated is
    yielded. Raises AIUnavailableError / AIUpstreamError when there is no
    usable idea at all.

    When fewer than MIN_IDEAS ideas pass, the rejected ideas and what is wrong
    with them are sent back once for repair (#65); the repair round has its
    own time limits. A failed repair keeps the ideas already sent. A first
    round that fails partway keeps its valid ideas and is not repaired.
    """
    input_mode = "structured" if structured else "natural_language"
    system_prompt, user_prompt = _build_explore_prompt(inventory_items, structured, natural_language, locale)
    inventory = Inventory(inventory_items)
    titles: set[str] = set()
    count = 0

    first = _Round("explore/first")
    async for idea in _stream_round(system_prompt, user_prompt, None, first, locale, inventory, titles):
        count += 1
        yield "idea", idea
    idea_warnings = first.warnings
    last = first

    if first.error is None and count < MIN_IDEAS and first.problems:
        feedback = _feedback(
            first.problems,
            'Reply with {"ideas": [...]} containing corrected versions of only the ideas listed '
            "above, in the same format. Do not repeat the ideas that had no problems.",
        )
        repair = _Round("explore/repair")
        followup = _repair_messages(first.text, feedback)
        async for idea in _stream_round(system_prompt, user_prompt, followup, repair, locale, inventory, titles):
            count += 1
            yield "idea", idea
        last = repair
        if repair.error is None:
            # Drop warnings now come from the repair round only.
            idea_warnings = [w for w in idea_warnings if not _is_drop_warning(w)] + repair.warnings
        else:
            idea_warnings = idea_warnings + [w for w in repair.warnings if not _is_drop_warning(w)]

    if count == 0:
        if first.error is not None:
            raise first.error
        raise AIUpstreamError(
            "AI reply contained no usable ideas: " + _summary(last.problems), "no_usable_ideas"
        )
    yield "done", {
        "mode": "ai",
        "input_mode": input_mode,
        "locale": locale,
        "warnings": dedupe_warnings(list(warnings or []) + idea_warnings),
        "count": count,
    }


async def explore_ideas(
    inventory_items: list[dict],
    structured: Optional[dict] = None,
    natural_language: Optional[str] = None,
    locale: str = "zh-CN",
    warnings: Optional[list[dict]] = None,
) -> dict:
    """All ideas at once (POST /api/recipes/explore): the same validated ideas
    as explore_stream, collected. Raises AIUnavailableError / AIUpstreamError."""
    ideas: list[dict] = []
    meta: dict = {}
    async for kind, value in explore_stream(inventory_items, structured, natural_language, locale, warnings):
        if kind == "idea":
            ideas.append(value)
        else:
            meta = value
    meta.pop("count", None)
    return {**meta, "ideas": ideas}


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
    once for repair (#65). Each round has its own time limits. The
    better of the usable drafts is returned (fewer problems; the repaired one
    on a tie); with no usable draft: 502. There is no fallback draft (#66).
    """
    inventory_items = inventory_items or []
    inventory = Inventory(inventory_items)
    system, user = _build_expand_prompt(idea, inventory_items, locale)
    first = await chat_json(system, user, label="expand/first")
    results = [clean_draft(first, idea, locale, inventory)]
    if needs_repair(results[0]):
        feedback = _feedback(
            results[0].problems,
            "Fix these problems and reply with the complete corrected recipe JSON in the same "
            "format. Keep everything else unchanged.",
        )
        try:
            # The repair round has its own time limits (ai_client).
            repaired = await chat_json(
                system, user, followup=_repair_messages(first, feedback), label="expand/repair"
            )
            results.append(clean_draft(repaired, idea, locale, inventory))
        except AIUpstreamError:
            pass  # logged by ai_client; the first draft is used if it is usable

    usable = [r for r in results if r.draft is not None]
    if not usable:
        raise AIUpstreamError(
            "AI draft was unusable: " + _summary(results[-1].problems), "draft_unusable"
        )
    best = min(reversed(usable), key=lambda r: len(r.problems))
    return {
        "recipe_draft": best.draft,
        "locale": locale,
        "warnings": dedupe_warnings(list(warnings or []) + best.warnings),
    }

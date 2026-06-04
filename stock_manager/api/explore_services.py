"""Explore Recipes service - generates cooking ideas via AI.

Supports both structured preferences and natural language input.
Both modes are converted into an AI prompt that generates idea candidates.
"""
import json
import logging
import os
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


async def _call_ai(prompt: str, system_prompt: str) -> Optional[str]:
    import httpx
    base_url = os.getenv("AI_BASE_URL", "https://api.deepseek.com")
    api_key = os.getenv("AI_API_KEY", "")
    model = os.getenv("AI_MODEL", "deepseek-chat")
    timeout = int(os.getenv("AI_TIMEOUT_SECONDS", "60"))
    temperature = float(os.getenv("AI_TEMPERATURE", "0.2"))
    enabled = os.getenv("AI_RECIPE_ENABLED", "false").lower() == "true"

    if not enabled or not api_key:
        logger.info("AI not configured, skipping")
        return None

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": 4096,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
            return result.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        logger.error("AI call failed: %s", e)
        return None


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


def _parse_explore_response(raw: str) -> Optional[list[dict]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        if match:
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        else:
            return None

    ideas = data.get("ideas", [])
    if not isinstance(ideas, list) or not ideas:
        return None

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
        validated.append(idea)

    return validated if validated else None


async def explore_ideas(inventory_items: list[dict], structured: Optional[dict] = None, natural_language: Optional[str] = None) -> dict:
    input_mode = "structured" if structured else "natural_language"
    system_prompt, user_prompt = _build_explore_prompt(inventory_items, structured, natural_language)
    raw = await _call_ai(user_prompt, system_prompt)

    if raw is None:
        return {"mode": "ai", "input_mode": input_mode, "ideas": [], "warnings": ["AI is not configured or unavailable. Unable to generate ideas."]}

    ideas = _parse_explore_response(raw)
    if ideas is None:
        return {"mode": "ai", "input_mode": input_mode, "ideas": [], "warnings": ["Failed to parse AI response."]}

    for idea in ideas:
        idea["idea_id"] = str(uuid4())[:8]

    return {"mode": "ai", "input_mode": input_mode, "ideas": ideas, "warnings": []}


async def expand_to_recipe_draft(idea: dict) -> dict:
    system = (
        "You are a cooking assistant. "
        "Expand a cooking idea into a structured recipe.\n\n"
        "RULES:\n"
        "1. Estimate realistic ingredient quantities for 2 servings.\n"
        "2. Include clear step-by-step instructions.\n"
        "3. Output ONLY valid JSON.\n\n"
        "OUTPUT FORMAT:\n"
        "```json\n"
        "{\n"
        '  "title": "Dish Name",\n'
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

    raw = await _call_ai(user, system)
    if raw is None:
        return {"recipe_draft": {"title": idea.get("title", ""), "ingredients": [], "steps": [], "warnings": ["AI not available for expansion."]}}

    try:
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        if match:
            data = json.loads(match.group(1))
        else:
            data = json.loads(raw)
    except Exception:
        data = {"title": idea.get("title", ""), "ingredients": [], "steps": []}

    data.setdefault("title", idea.get("title", ""))
    data.setdefault("description", idea.get("description", ""))
    data.setdefault("ingredients", [])
    data.setdefault("steps", [])
    data["warnings"] = ["This is an AI-generated recipe draft. Please confirm ingredients and steps before saving."]
    data["difficulty"] = data.get("difficulty", "medium")
    data["servings"] = data.get("servings", "2 servings")
    data["cook_time_minutes"] = data.get("cook_time_minutes", idea.get("estimated_time_minutes", 30))

    return {"recipe_draft": data}

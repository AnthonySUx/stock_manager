"""AI-powered recipe recommendation service.

This module calls an OpenAI-compatible API to sort and explain
recipe candidates. It never generates recipes outside the candidate list.
"""
import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _load_config() -> dict:
    """Load AI configuration from environment."""
    return {
        "enabled": os.getenv("AI_RECIPE_ENABLED", "false").lower() == "true",
        "base_url": os.getenv("AI_BASE_URL", "https://api.openai.com/v1"),
        "api_key": os.getenv("AI_API_KEY", ""),
        "model": os.getenv("AI_MODEL", "gpt-4o-mini"),
        "timeout": int(os.getenv("AI_TIMEOUT_SECONDS", "60")),
        "temperature": float(os.getenv("AI_TEMPERATURE", "0.2")),
    }


def _build_system_prompt() -> str:
    """Build the system prompt for AI recipe recommendation."""
    return (
        "You are a helpful recipe recommendation assistant for a family stock management app. "
        "Your task is to help the user decide what to cook based on their current food inventory "
        "and a list of candidate recipes.\n\n"
        "RULES:\n"
        "1. You MUST only choose from the `provided_candidates` list. Do NOT invent new recipes.\n"
        "2. Each recommendation must have a `recipe_id` that exists in the candidate list.\n"
        "3. Do NOT claim the user has ingredients that are not in `inventory_items`.\n"
        "4. If a recipe needs ingredients not in inventory, list them in `missing_ingredients`.\n"
        "5. Prioritize recipes that use `expiring_soon_items` - these are ingredients about to expire.\n"
        "6. Mix favorite recipes and new suggestions for variety.\n"
        "7. Output ONLY valid JSON in the format specified below.\n\n"
        "OUTPUT FORMAT:\n"
        "```json\n"
        "{\n"
        '  "summary": "Brief explanation of today\u2019s top pick",\n'
        '  "recommendations": [\n'
        "    {\n"
        '      "recipe_id": 123,\n'
        '      "reason": "Why this recipe is recommended today",\n'
        '      "use_first": ["ingredient1"],\n'
        '      "missing_warning": "Optional note about missing items"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n"
        "Return the recommendations sorted by priority (most recommended first). "
        "Recommend no more than 5 recipes."
    )


def _build_user_prompt(
    candidates: list[dict],
    inventory_items: list[str],
    expiring_soon_items: list[str],
    favorite_ids: list[int],
) -> str:
    """Build the user prompt with current data."""
    cand_lines = []
    for c in candidates:
        fav = " [FAVORITE]" if c["recipe_id"] in favorite_ids else ""
        exp = ""
        if c["expiring_inventory_items"]:
            exp = " [uses expiring: " + ", ".join(c["expiring_inventory_items"]) + "]"
        cand_lines.append(
            f"- recipe_id={c['recipe_id']}: {c['title']}{fav}{exp}"
        )

    return (
        f"CURRENT INVENTORY ITEMS:\n{', '.join(inventory_items)}\n\n"
        f"EXPIRING SOON ITEMS:\n{', '.join(expiring_soon_items)}\n\n"
        f"CANDIDATE RECIPES:\n" + "\n".join(cand_lines) + "\n\n"
        "Please recommend the best recipes for today. "
        "Output ONLY JSON."
    )


def _validate_ai_response(
    raw: str,
    candidate_ids: set[int],
    inventory_names: set[str],
) -> Optional[dict]:
    """Validate AI response against candidates and inventory."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        if match:
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        else:
            return None

    if not isinstance(data, dict):
        return None

    recommendations = data.get("recommendations", [])
    if not isinstance(recommendations, list):
        return None

    valid_recs = []
    for rec in recommendations:
        rid = rec.get("recipe_id")
        if rid not in candidate_ids:
            logger.warning("AI returned invalid recipe_id=%s, skipping", rid)
            continue

        # Check use_first items exist in inventory
        use_first = rec.get("use_first", [])
        for item in use_first:
            if item.lower() not in {n.lower() for n in inventory_names}:
                logger.warning("AI claimed item '%s' not in inventory", item)
                # Don't skip the whole recipe, just log

        valid_recs.append(rec)

    if not valid_recs:
        return None

    data["recommendations"] = valid_recs
    return data


async def get_ai_recommendations(
    candidates: list[dict],
    inventory_items: list[str],
    expiring_soon_items: list[str],
    favorite_ids: list[int],
) -> Optional[dict]:
    """Call AI API to sort and explain recipe recommendations.

    Returns None if AI is disabled, misconfigured, or returns invalid output.
    """
    config = _load_config()
    if not config["enabled"] or not config["api_key"]:
        return None

    candidate_ids = {c["recipe_id"] for c in candidates}
    inv_names = set(inventory_items)

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(
        candidates, inventory_items, expiring_soon_items, favorite_ids
    )

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": config["temperature"],
        "max_tokens": 2048,
    }

    try:
        async with httpx.AsyncClient(timeout=config["timeout"]) as client:
            resp = await client.post(
                f"{config['base_url'].rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception as e:
        logger.error("AI API call failed: %s", e)
        return None

    raw_content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not raw_content:
        return None

    validated = _validate_ai_response(raw_content, candidate_ids, inv_names)
    return validated

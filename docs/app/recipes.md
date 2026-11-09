# Recipes

Recipes are an feature for app only. They provide a browsing, searching, favoriting, editing, creating, and exploring experience integrated with the user's inventory.

---

## Recipe Library

Users can:

- Browse recipes sorted by relevance
- Search recipes by title or description
- View recipe details (categories, difficulty, servings, cook time, ingredients, steps)
- Filter by source type (`howtocook`, `user`, `ai_saved`)
- Filter by category
- Show only favorites
- Create personal recipes
- Fork existing recipes as personal editable copies
- Edit user-created recipes
- Delete user-created recipes (its favorite and cooking history are removed with it;
  recipes forked from it are kept)

### Sources

Recipes come from:

- **HowToCook** (imported from [Anduin2017/HowToCook](https://github.com/Anduin2017/HowToCook), The Unlicense)
- **User-created** (created via the API or frontend)
- **AI-saved** (saved from Explore Recipes drafts)

### Favorites

Users can favorite/unfavorite recipes. Favorites are prioritized in search results and recommendations.

---

## Today Recommendations

`GET /api/recipes/recommendations?scene=<scene>&limit=<n>`

Generates a daily list of recipes to cook based on current inventory. The call is
**read-only**: refreshing the page gives the same list until inventory, favorites or
cooking history change.

### Scenes (`scene`, default `all`)

| `scene` | Recipe `category` (HowToCook `dishes/` directory) |
|---|---|
| `breakfast` | `breakfast` |
| `meal` (lunch / dinner) | `meat_dish`, `vegetable_dish`, `aquatic`, `soup`, `staple`, `semi-finished` |
| `dessert_drink` | `dessert`, `drink` |
| `all` | everything |

New user recipes must have a `category` from this list (plus `condiment`): `POST /api/recipes`
without it, or with another value, returns `422`; `PATCH` cannot set it to `null`. AI drafts from
`explore/expand` suggest a category; an invalid suggestion becomes `null` so the user picks one.
Older user recipes saved before this rule keep working: free-text categories such as 早餐 / 甜品 /
饮品 are mapped, and ones with no or an unknown category count as `meal`.

Nothing is excluded for good: desserts and drinks are recommended under `dessert_drink` and `all`.
`condiment` only appears under `all`. An unknown `scene` returns `422`. HowToCook rows that are
not dishes (`tips/`, `.github/`, `dishes/template/`, imported by older importer versions) are never
recommended.

For HowToCook recipes the directory is read from `source_path` (`dishes/<dir>/...`), because
many recipes are nested one level deeper (`dishes/meat_dish/口水鸡/口水鸡.md`).

### How It Works

1. Gathers all `active` and `expiring soon` inventory items whose category is recipe-eligible (`recipe_usage` is `always` or `conditional`; see [Categories](features.md#categories))
2. Normalizes item names using the [ingredient synonym table](#ingredient-matching) for matching
3. Scores each recipe using local rules
4. Returns the top-ranked recipes

### Scoring Rules

| Condition | Score |
|---|---|
| Per matched inventory ingredient | +10 |
| Per expiring-soon inventory ingredient | +40 (additional) |
| Per missing required ingredient | −5 |
| Recipe is favorited | +15 |
| Cooked in the last 7 days | −10 (give other dishes a turn) |
| Not cooked in the last 7 days | +5 |

Ingredients matched from `conditional` categories (drinks, snacks, frozen, canned, etc.) get reduced weight: +6 instead of +10, and +20 instead of +40 when expiring. Whether an ingredient counts as `always` is checked after synonym resolution, so `西红柿` in a vegetables category keeps full weight when it matches a recipe's `番茄`.

### Ingredient Matching

To handle cases where inventory names don't exactly match recipe ingredient names (e.g., `西红柿` vs `番茄`, `potato` vs `土豆`, `じゃがいも`), the app uses a local synonym table (`DEFAULT_SYNONYM_MAP`).

This is **deterministic**, not AI-based. It covers common names in Chinese, English, and Japanese while being conservative to avoid over-normalization.

### Recommendation History

History comes from cooking, not from viewing. `POST /api/recipes/{id}/cook` writes a `cooked`
event; recipes cooked in the last 7 days (`RECENT_COOKED_DAYS`) get −10 instead of +5, so a dish
you just made is pushed down for a week. `GET /api/recipes/recommendations` writes nothing.
`is_new_suggestion` is `true` when the recipe was not cooked in that window. Older `recommended`
events (written before this change) are ignored.

Ties in score are ordered by recipe id, so the list order is stable.

### Consume Preview and Cook

After choosing a recipe:

- **Consume Preview** (`GET /api/recipes/{id}/consume-preview`): Suggests which inventory items match the recipe's ingredients and could be consumed. Nothing is changed.
- **Cook** (`POST /api/recipes/{id}/cook`): Marks the recipe as cooked. The user confirms which items to consume, and inventory quantities are updated accordingly.

#### Suggested amounts and units

Each suggestion carries the amount in the **stock item's unit** (`unit`), because that is what
Cook deducts. Units are compared, never converted:

| Recipe amount | Stock unit | `suggested_quantity` | `needs_user_input` |
| --- | --- | --- | --- |
| `2 个` | `个` | `2` | `false` |
| `500克` | `g` | `500` (aliases: 克/g, 千克/公斤/kg, 毫升/ml, 升/l, 个/pcs) | `false` |
| `3 个` | `个`, only 1 in stock | `1` (capped at stock) | `false` |
| `500 g` | `个` | `null` | `true` |
| `适量`, `1/2`, `2` (no unit), none | any | `null` | `true` |

When `needs_user_input` is `true`, the app must ask the user how much to deduct (in `unit`).
`recipe_quantity` is the recipe amount as written (e.g. `500克`), for display; `confidence` is
`high` when an amount is suggested and `low` otherwise.

---

## Explore Recipes

`POST /api/recipes/explore`

Generate creative cooking ideas from your current inventory. Unlike Today Recommendations, Explore is **AI-powered** and designed for open-ended discovery.

### How It Works

1. Sends your recipe-eligible inventory (active / expiring soon) to the AI provider
2. Uses **one** input, chosen by `mode`:
   - `structured`: preferences (flavors, cuisine, cooking methods, max time, …)
   - `natural_language`: a free-text prompt (e.g., "I want something light for dinner")
3. Returns a list of creative cooking ideas with reasoning

### Request rules

| `mode` | Required | Must be empty / null |
|---|---|---|
| `structured` | `structured` (object; `{}` is fine) | `natural_language` |
| `natural_language` | `natural_language` (non-blank text) | `structured` |

A mismatch returns `422`.

`structured.inventory_item_ids` (optional): when non-empty, only those stock items are sent
to the AI. Each id must be an active / expiring-soon item in a category with
`recipe_usage` `always` or `conditional`; otherwise the request returns `400` and lists the bad ids.
Empty or omitted → all eligible inventory.

```json
{"mode": "structured", "structured": {"inventory_item_ids": [12, 15], "flavors": ["spicy"]}}
```

### AI response handling

The AI may answer with `{"ideas": [...]}` or a bare list of ideas; both work. Ideas without a
title or with wrong field types are dropped. If nothing usable comes back, the response is `200`
with `ideas: []` and the warning `"Failed to parse AI response."` (never a `500`).

### Expand Idea to Draft

`POST /api/recipes/explore/expand`

Select an explore idea and expand it into a structured recipe draft with estimated ingredients and steps. The draft is **not saved automatically** — the frontend should let users review and optionally save it via the recipe creation API.

### AI Boundary

Currently AI is used **only** for Explore Recipes. Today Recommendations use local scoring (decided in PR #14).

- If AI is disabled or fails, Explore endpoints return descriptive error messages
- `POST /api/recipes/ai/today` is **deprecated** (shown as deprecated in `/docs`). It is kept only for compatibility. Its list is always the rule-based result: when AI is enabled, AI adds only the `summary`, and on any failure it returns `mode="rule_based_fallback"`. New frontend code should call `GET /api/recipes/recommendations`.
- AI configuration uses the following environment variables:

Example:

| Variable | Default | Description |
|---|---|---|
| `AI_RECIPE_ENABLED` | `false` | Enable AI features |
| `AI_BASE_URL` | `https://api.deepseek.com` | AI provider base URL |
| `AI_API_KEY` | — | API key |
| `AI_MODEL` | `deepseek-chat` | Model name |
| `AI_TIMEOUT_SECONDS` | `60` | Request timeout |
| `AI_TEMPERATURE` | `0.2` | Response temperature |

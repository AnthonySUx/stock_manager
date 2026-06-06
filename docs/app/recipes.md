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
- Delete user-created recipes

### Sources

Recipes come from:

- **HowToCook** (imported from [Anduin2017/HowToCook](https://github.com/Anduin2017/HowToCook), The Unlicense)
- **User-created** (created via the API or frontend)
- **AI-saved** (saved from Explore Recipes drafts)

### Favorites

Users can favorite/unfavorite recipes. Favorites are prioritized in search results and recommendations.

---

## Today Recommendations

`GET /api/recipes/recommendations`

Generates a daily list of recipes to cook based on current inventory.

### How It Works

1. Gathers all `active` and `expiring soon` inventory items
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
| Recommended in last 7 days | −10 (diversity) |
| Not recommended in last 7 days | +5 (novelty) |

### Ingredient Matching

To handle cases where inventory names don't exactly match recipe ingredient names (e.g., `西红柿` vs `番茄`, `potato` vs `土豆`, `じゃがいも`), the app uses a local synonym table (`DEFAULT_SYNONYM_MAP`).

This is **deterministic**, not AI-based. It covers common names in Chinese, English, and Japanese while being conservative to avoid over-normalization.

### Recommendation History

When recommendations are generated, the results are recorded in the usage history. Recipes recommended in the last 7 days receive a scoring penalty to ensure diversity. Over time, the same recipes won't dominate daily recommendations.

### Consume Preview and Cook

After choosing a recipe:

- **Consume Preview** (`GET /api/recipes/{id}/consume-preview`): Suggests which inventory items match the recipe's ingredients and could be consumed.
- **Cook** (`POST /api/recipes/{id}/cook`): Marks the recipe as cooked. The user confirms which items to consume, and inventory quantities are updated accordingly.

---

## Explore Recipes

`POST /api/recipes/explore`

Generate creative cooking ideas from your current inventory. Unlike Today Recommendations, Explore is **AI-powered** and designed for open-ended discovery.

### How It Works

1. Sends your current inventory to the AI provider
2. Optionally accepts structured preferences (flavors, cuisine, cooking methods, max time)
3. Optionally accepts natural language prompts (e.g., "I want something light for dinner")
4. Returns a list of creative cooking ideas with reasoning

### Expand Idea to Draft

`POST /api/recipes/explore/expand`

Select an explore idea and expand it into a structured recipe draft with estimated ingredients and steps. The draft is **not saved automatically** — the frontend should let users review and optionally save it via the recipe creation API.

### AI Boundary

Currently AI is used **only** for Explore Recipes. 

- If AI is disabled or fails, Explore endpoints return descriptive error messages
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

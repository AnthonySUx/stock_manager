# Recipes

Recipes are an feature for app only. They provide a browsing, searching, favoriting, editing, creating, and exploring experience integrated with the user's inventory.

---

## Recipe Library

Users can:

- Browse recipes sorted by relevance
- Search recipes by title or description
- View recipe details (categories, difficulty, servings, cook time, ingredients, steps)
- Filter by source type (`howtocook`, `user`). Saved AI drafts are `user` recipes.
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

This is **deterministic**, not AI-based. It covers common names in Chinese, English, and Japanese while being conservative to avoid over-normalization (for example, 人参 is not a carrot: in Chinese it means ginseng). Matching works across languages: stock `tomato` matches recipe `番茄`.

### Recommendation History

History comes from cooking, not from viewing. `POST /api/recipes/{id}/cook` writes a `cooked`
event; recipes cooked in the last 7 days (`RECENT_COOKED_DAYS`) get −10 instead of +5, so a dish
you just made is pushed down for a week. `GET /api/recipes/recommendations` writes nothing.
`is_new_suggestion` is `true` when the recipe was not cooked in that window. Older `recommended`
events (written before this change) are ignored.

Ties in score are ordered by recipe id, so the list order is stable.

### Consume Preview and Cook

After choosing a recipe:

- **Consume Preview** (`GET /api/recipes/{id}/consume-preview`): Suggests which inventory items match the recipe's ingredients and could be consumed. Nothing is changed. Names are matched through the synonym map, like Today Recommendations: stock named 西红柿 matches a recipe that says 番茄 (also 土豆 / 马铃薯, Tomato / 番茄). A name with a qualifier (土鸡蛋 vs 鸡蛋) does not match.
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

`POST /api/recipes/explore` (all ideas at once) · `POST /api/recipes/explore/stream` (one idea
at a time, see [Streamed Explore](#streamed-explore))

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

Both Explore and Expand accept an optional `locale` field (see below).

### Ideas that are local recipes

Each idea title is compared with the titles of all local recipes (HowToCook, user recipes and
forks). When the idea is a dish the library already has, the idea is linked to it:

| Field | Not linked | Linked |
|---|---|---|
| `source_type` | `ai_idea` | `existing_recipe` |
| `recipe_id` | `null` | the local recipe |
| `can_expand_to_recipe` | `true` | `false`: open `GET /api/recipes/{recipe_id}` instead of Expand |

Matching (`TitleMatcher` in `text_search.py`):

1. Both titles are normalized: the HowToCook suffix "的做法", bracketed notes, spaces and
   punctuation are removed, letters are lower-cased, and Chinese ingredient synonyms of two or
   more characters are mapped to one name (西红柿 → 番茄, 包菜 → 卷心菜), plus 鸡蛋 → 蛋.
2. A title matches a recipe when it is
   - the same after normalization: 番茄炒蛋 = 西红柿炒鸡蛋;
   - very similar, character-bigram Dice ≥ 0.8: 番茄鸡蛋面 → 西红柿鸡蛋挂面;
   - contained in it or containing it, the shorter at least 3 Chinese characters and Dice
     ≥ 0.5: 红烧肉 → 简易红烧肉, 黄焖鸡米饭 → 黄焖鸡, 蛋花汤 → 紫菜蛋花汤.
3. The best score wins; on a tie, the older recipe.

The thresholds were tuned on the 373 HowToCook titles. They keep different dishes apart:
青椒炒肉 is not 辣椒炒肉, 黄瓜炒蛋 is not 黄瓜炒肉, 炒饭 (2 characters) is not 蛋炒饭. The
"contains" rule is not used for Latin text.

A second idea for a recipe that is already linked (番茄炒蛋 and 西红柿炒鸡蛋 in one reply) is not
sent, like a repeated title. Linking works the same on `/explore` and `/explore/stream`.

### Language of AI output

AI text is generated in one locale: `zh-CN`, `en` or `ja` (#65). It is chosen in this order:

1. `locale` in the request body;
2. the household setting `default_locale` (`PATCH /api/settings`);
3. the `Accept-Language` header;
4. `zh-CN`.

The setting comes before the header because iOS sends the device language with every request;
otherwise the household setting could never apply. An unsupported `locale` in the body falls
back and adds the warning `locale_fallback`; an unsupported header is ignored silently. The
response carries the locale that was used (`"locale": "zh-CN"`).

Recipe content from HowToCook is Chinese and is not translated; only AI text follows the locale.

### AI output validation

The prompt states the rules, and the backend checks every reply. Nothing from the model reaches
the app unchecked.

**Language.** Titles, descriptions, reasons, steps, ingredient names, flavors, textures and
cuisine must be in the locale. Inventory names are exempt: they are copied verbatim, in any
language.

| Locale | Rule |
|---|---|
| `zh-CN` | Contains Chinese characters; no Japanese kana; Latin words only for units (`g`, `ml`, `°C`) |
| `ja` | Contains Japanese characters; Latin words only for units |
| `en` | No Chinese or Japanese characters |

Text with no letters at all (for example `2`) passes. `zh-CN` and `ja` are not told apart
beyond the kana rule, so a kanji-only Japanese title passes as Chinese.

**Machine fields** are fixed English values; the app translates them for display. An unknown
value becomes `null` and adds `field_value_dropped`. Case and `-` / space are tolerated
(`Stir-Fry` → `stir_fry`).

| Field | Values |
|---|---|
| `cooking_method` (ideas) | `stir_fry`, `steam`, `boil`, `braise`, `stew`, `pan_fry`, `deep_fry`, `roast`, `bake`, `grill`, `cold_mix`, `raw`, `other` |
| `cuisine_group` (ideas) | `chinese`, `japanese`, `korean`, `western`, `southeast_asian`, `other` |
| `difficulty` (drafts) | `easy`, `medium`, `hard` |
| `category` (drafts) | the recipe categories (`meat_dish`, …) |

`source_type` / `recipe_id` from the model are always discarded; only the backend links an
idea to a local recipe (see [Ideas that are local recipes](#ideas-that-are-local-recipes)).

**Ingredient lists in ideas** are recomputed from the inventory that was sent, through the
synonym table. A name the model lists that matches stock goes to `matched_ingredients` under
the stock item's exact name (and to `expiring_ingredients` when that item is expiring soon);
any other name goes to `missing_ingredients`.

**Quantities and units in drafts.** `quantity` is a positive number (`"2"`, `"0.5"`) or a
"to taste" word; ranges and fractions (`2-3`, `1/2`) are rejected. `unit` must be one of the
locale's units, or the unit of the matching stock item. Spelling variants are mapped to the
locale's spelling (`g` → `克`, `大勺` → `汤匙`, `pieces` → `pcs`). There is still no conversion
between units.

| Locale | Units | "To taste" |
|---|---|---|
| `zh-CN` | 克, 千克, 毫升, 升, 个, 只, 颗, 根, 片, 瓣, 块, 把, 汤匙, 茶匙, 杯 | 适量, 少许 |
| `en` | g, kg, ml, l, pcs, tbsp, tsp, cup, clove, slice | to taste |
| `ja` | g, kg, ml, l, 個, 本, 枚, かけ, 大さじ, 小さじ, カップ, 束, パック | 適量, 少々 |

An invalid quantity or unit clears both (the ingredient is kept) and adds `quantity_dropped`.
For a "to taste" quantity the unit is cleared.

The prompt states these rules up front (the same lists and the same language rules the
backend checks), so most replies pass the first time.

**Repair round with feedback.** When a reply fails, the backend does not just ask again: it
sends the model its previous reply plus a list of exactly what is wrong, for example
`steps[2].instruction "Cut the tomatoes" is not in Simplified Chinese.` or
`ingredients[3] "糖": quantity "1/2" with unit "茶匙" is not allowed. Use one number and one
of: 克, 千克, …`. There is at most **one** repair round. Each round has its own time limits (see
[Timing](#timing)).

| Where | When a repair round is sent | Result |
|---|---|---|
| Explore | Fewer than 3 ideas passed and some were dropped | Only the dropped ideas are sent back; repaired ideas are added (duplicate titles skipped) |
| Expand | The draft is unusable (wrong language anywhere, no usable step, not an object) or a quantity / unit had to be cleared | The better draft is used: fewer problems, the repaired one on a tie |

Wrong enum values, servings or a wrong `category` alone do not trigger a repair: they are only
cleared (`null`) with `field_value_dropped`, which costs no extra tokens.

If the repair call fails or runs out of time, the first round's result is used when it is
usable (for Explore: the ideas already validated, including any the repair round finished before
it failed). A first Explore round that fails partway (time limit, cut off at `max_tokens`) keeps
the ideas it completed and is not repaired. Only when nothing is usable: `502 ai_upstream_error`.

| Where | Failure (after the repair round) | Result |
|---|---|---|
| Explore | An idea's title / description / reason is in the wrong language | Idea dropped, `idea_dropped_wrong_language` |
| Explore | An idea has no title or a list field is not a list | Idea dropped, `idea_dropped_malformed` |
| Explore | A flavor, texture, cuisine or missing ingredient is in the wrong language | That value dropped, `field_value_dropped` |
| Explore | No usable idea left | `502 ai_upstream_error` |
| Expand | No usable draft | `502 ai_upstream_error` |
| Expand | An ingredient without a name / a step without text | Dropped, `ingredient_dropped_malformed` / `step_dropped_malformed` |

Warnings describe the result that is returned: problems fixed by the repair round leave no
warning.

### Warnings

`warnings` is a list of `{"code": "...", "params": {...}}`; the app shows its own text for each
code. Identical warnings are merged. Parameter values are strings.

| Code | Params | Meaning |
|---|---|---|
| `locale_fallback` | `requested` | The requested locale is not supported |
| `draft_ai_generated` | — | Always on Expand: review before saving |
| `idea_dropped_malformed` | — | An idea was unusable |
| `idea_dropped_wrong_language` | `title` | An idea was not in the locale |
| `field_value_dropped` | `field`, `value` | A value was invalid and removed |
| `quantity_dropped` | `ingredient` | A quantity / unit was invalid and cleared |
| `ingredient_dropped_malformed` | `index` | Ingredient at this 1-based position in the AI reply was unusable |
| `step_dropped_malformed` | `index` | Step at this 1-based position was unusable |

### Streamed Explore

`POST /api/recipes/explore/stream` takes the same body as `/explore` and returns
`text/event-stream`. Each idea is sent **as soon as the AI has finished writing it and it has
passed validation**; nothing unvalidated is ever sent (no partial idea, no rejected idea, no
reasoning text).

```
event: idea
data: {"idea_id": "3f2a9c1b", "title": "番茄炒蛋", ...}

: ping

event: idea
data: {"idea_id": "8d0e4b77", "title": "红烧豆腐", ...}

event: done
data: {"mode": "ai", "input_mode": "natural_language", "locale": "zh-CN", "warnings": [], "count": 2}
```

| Event | Data | Notes |
|---|---|---|
| `idea` | One idea, exactly as in `ideas[]` of `/explore` | Validated; duplicate titles are not sent again |
| `done` | `mode`, `input_mode`, `locale`, `warnings`, `count` | Last event on success. `warnings` is final only here |
| `error` | `{"code": "ai_upstream_error"}` (or `internal_error`) | Last event when no idea could be produced |
| `: ping` | — | A comment every 10 s while the AI works; ignore it |

- Ideas from the repair round (if any) follow the first round's ideas in the same stream.
- Errors known before the AI is called keep their status codes: `400` (bad
  `inventory_item_ids`), `422` (bad body), `503 ai_unavailable`. After the stream has started,
  the status is `200` and failures arrive as an `error` event.
- If the client disconnects, the backend stops the AI call.
- `POST /api/recipes/explore` returns the same validated ideas, all at once.

Expand is not streamed to the client: a draft can only be validated as a whole (a step in the
wrong language or a missing step makes the whole draft unusable).

### Timing

The backend streams every text reply from the AI provider (`AI_STREAM=true`), so a slow but
progressing reply is not cut off. Limits **per round** (the repair round gets its own):

| Limit | Default | Meaning |
|---|---|---|
| First data | 20 s | Something (text or reasoning) must arrive within this time |
| Idle | 15 s | The stream may not stall longer than this |
| Round | 50 s | One round, retry included |

Worst case for a request with a repair round is about 100 s. A client calling the non-streamed
`/explore` or `/explore/expand` should wait at least **120 s**. On `/explore/stream` the 10 s
ping keeps an idle-based client timeout (such as `URLRequest.timeoutInterval`) from firing.

### AI errors

The AI may answer Explore with `{"ideas": [...]}` or a bare list of ideas; both work. As long
as one idea passes validation the response is `200`.

Errors (Explore and Expand), with a JSON body `{"code": "..."}`:

| Status | `code` | When | What the app should do |
|---|---|---|---|
| `503` | `ai_unavailable` | AI is not configured or is disabled | Hide or disable AI features (see `GET /api/capabilities`); retrying does not help |
| `502` | `ai_upstream_error` | The provider timed out, failed, or returned nothing usable | Offer "retry" |

Never a `500`.

The client only gets the code. The reason is in the backend log: one line per AI call, and one
per failed request:

```
INFO:     stock_manager.api.ai_client: AI explore/first ok model=deepseek-flash stream 12.4s first_data=1.1s reasoning=3.2s chars=1830 tokens=812/1430 finish=stop
WARNING:  stock_manager.api.ai_client: AI explore/repair fail timeout_idle model=deepseek-flash stream 31.0s first_data=1.0s reasoning=- chars=620 tokens=?/? finish=-: AI stream stalled for 15s
WARNING:  stock_manager.api.ai_client: POST /api/recipes/explore -> ai_upstream_error [no_usable_ideas]: AI reply contained no usable ideas: Idea #1 title "Tomato soup" is not in Simplified Chinese. | ...
```

Image calls do not log reply text. Their log line shows the time, `finish`, `tokens` (prompt/completion), `reasoning_chars` and `attempts`.

| Reason | Meaning |
|---|---|
| `timeout_first_token` | Nothing arrived within the first-data limit |
| `timeout_idle` | The stream stalled |
| `timeout_round` | The round took longer than the round limit |
| `timeout` | A non-streamed request timed out |
| `connection` | The provider could not be reached (or the connection broke mid-reply) |
| `http_error` | The provider returned an HTTP error; its message is logged (401 / 403: "check AI_API_KEY") |
| `stream_error` | The stream carried an error or a broken chunk |
| `no_content` | The reply was empty or only whitespace. DeepSeek documents that JSON mode occasionally does this. The call is retried once when another attempt of the same length fits in the round limit; the log then shows `rounds=2` |
| `truncated` | The reply hit `max_tokens` (`finish=length`) and is not complete JSON, or reasoning used the whole budget before any content. Not retried |
| `not_json` | The reply is not JSON (its start is logged) |
| `no_usable_ideas` | Explore: no idea passed validation (the first problems are logged) |
| `draft_unusable` | Expand: no draft passed validation (the first problems are logged) |

`LOG_LEVEL` (default `INFO`) sets the level of the backend's own log lines.

### Expand Idea to Draft

`POST /api/recipes/explore/expand`

Select an explore idea and expand it into a structured recipe draft with estimated ingredients and steps. The draft is **not saved automatically** — the frontend should let users review and optionally save it via the recipe creation API.

Request: `{"idea": <an idea from Explore>, "locale": "zh-CN"}` (`locale` optional).

Response:

```json
{
  "locale": "zh-CN",
  "recipe_draft": {
    "title": "番茄炒蛋", "category": "vegetable_dish", "description": "…",
    "difficulty": "easy", "servings": "2", "cook_time_minutes": 15, "raw_markdown": null,
    "ingredients": [{"ingredient_name": "番茄", "normalized_name": null, "quantity": "2",
                     "unit": "个", "is_optional": false, "is_seasoning": false, "sort_order": 0}],
    "steps": [{"step_number": 1, "instruction": "…"}]
  },
  "warnings": [{"code": "draft_ai_generated", "params": {}}]
}
```

- `recipe_draft` has the fields of `POST /api/recipes`. `category` may be `null`: the user picks
  one before saving. Missing `difficulty`, `servings` and `cook_time_minutes` stay `null`
  (`cook_time_minutes` falls back to the idea's estimate); there are no invented defaults.
- The prompt lists recipe-eligible inventory with units. An ingredient that matches stock
  (synonyms included) uses the stock item's exact name, so cooking the saved recipe finds it.
- Steps are renumbered 1, 2, 3, ….

When the AI fails, Expand returns `502` / `503` like Explore. There is no fallback draft (it used
to return just the title with no ingredients or steps); the user can retry or create the recipe
by hand.

### AI Boundary

Currently AI is used **only** for Explore Recipes. Today Recommendations use local scoring (decided in PR #14).

- `GET /api/capabilities` (needs the API token) tells the app what is available:
  `{"ai": {"text": true, "vision": false, "asr": false}}`. `text` is true when AI is enabled and
  configured; use it to decide whether to show Explore. `vision` and `asr` turn on with intake
  (#63) and speech (#32).
- If AI is disabled or fails, Explore and Expand return `503` / `502` (see above).
- `POST /api/recipes/ai/today` was removed in #66 (deprecated since PR #14). Use
  `GET /api/recipes/recommendations`.
- All AI calls go through one client (`stock_manager/api/ai_client.py`). It asks for JSON output
  (`response_format: json_object`), also accepts JSON in a code fence, streams text replies, and
  logs every call (see [AI errors](#ai-errors)).
- AI configuration uses the following environment variables. They are read once at startup:
  restart the backend after changing them. An invalid value is logged and turns AI off.

| Variable | Default | Description |
|---|---|---|
| `AI_RECIPE_ENABLED` | `false` | Enable AI features |
| `AI_BASE_URL` | `https://api.deepseek.com` | AI provider base URL |
| `AI_API_KEY` | — | API key |
| `AI_MODEL` | `deepseek-flash` | Model name (`deepseek-chat` is retired) |
| `AI_TEMPERATURE` | `0.2` | Response temperature |
| `AI_STREAM` | `true` | Stream text replies from the provider (`false`: one JSON body per request) |
| `AI_MAX_TOKENS` | `8192` | `max_tokens` per request (reasoning counts toward it on thinking models) |
| `AI_FIRST_TOKEN_TIMEOUT_SECONDS` | `20` | Streamed: first data must arrive within this time |
| `AI_IDLE_TIMEOUT_SECONDS` | `15` | Streamed: longest allowed gap between chunks |
| `AI_TIMEOUT_SECONDS` | `30` | Timeout per non-streamed text request (`AI_STREAM=false`) |
| `AI_IMAGE_TIMEOUT_SECONDS` | `60` | Timeout per image request (images are not streamed) |
| `AI_TOTAL_TIMEOUT_SECONDS` | `50` | Upper bound for one text round, retry included; the repair round gets its own |
| `AI_IMAGE_TOTAL_TIMEOUT_SECONDS` | `110` | Upper bound for one image call, including retries and one retry after an empty reply |
| `AI_MAX_RETRIES` | `1` | Retries after a connection error, `429` or `5xx`, before any content arrived. Timeouts are not retried |

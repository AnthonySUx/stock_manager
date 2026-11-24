# Features

See [API errors](errors.md) for the HTTP error format and codes.

Core App features for inventory management.

---

## Stock

### Adding Stock

The app supports recording:

- Name
- Category (required; chosen from the structured category tree, see [Categories](#categories))
- Purchaser or assigned user
- Date of purchase
- Expiration date when unopened / after opening
- Opening date
- Storage location (refrigerator, freezer, storage cabinet, etc.)
- Quantity and unit
- Notes

For items without an expiration date, use `infinite`.
On `POST /api/items`, `current_expiration_date` and `status` are optional legacy inputs.
The server calculates both fields and ignores the supplied values.

The backend also supports [AI-assisted text intake](intake.md) for drafting and reviewing multiple items before saving.

### Stock Overview

Displays current stock with:

- Name, category, owner, quantity, unit
- Storage location
- Current effective expiration date
- Status (`active`, `consumed`, `expiring soon`, `expired`)
- Whether notes exist

### List pagination

`GET /api/items` and `GET /api/restock` accept optional `limit` (1–100) and
`offset` (0 or greater). The response is a JSON array. Omit `limit` to return
all rows starting at `offset`. An offset past the last row returns an empty array.

Stock items are ordered by ID. Restock lists show pending entries before done
entries and order each group by ID.

### Search and Filter

- **Search**: by name, category, owner, location, notes. Case-insensitive, and the keyword
  is matched literally: `%` and `_` are ordinary characters (recipe search works the same way).
- **Filters**: by category, owner, location, status

### Edit

Edit one or more fields: name, category, owner, purchase date, quantity, location, expiration dates, notes.
Current expiration date and status are calculated automatically. A supplied
`current_expiration_date` is accepted as a legacy input and automatically replaced.

On `POST /api/items` and `PATCH /api/items/{id}`, the backend trims `name`, `owner`
and `location`. Blank values return `422`. Stock write quantities, including
`quantity_value` and `POST /api/items/{id}/consume`'s `quantity`, must be positive
and finite. NaN and Infinity return `422`.
Stored quantities use up to nine integer digits and three fractional digits. Write
amounts round to the nearest thousandth, with midpoint values rounded up. Values
that round to zero or exceed the storage range return `422`. Response quantities
remain JSON numbers.

Validation (returns `422`):

- Including a `status` key in `PATCH /api/items/{id}` returns `item_status_readonly`,
  including when the value is `null`.
- Dates must be real calendar dates in `YYYY-MM-DD` form (`2026-02-30` is rejected).
  Expiration dates may also be `infinite`; `purchase_date` and `opened_date` may not.
- An unopened expiration date before the purchase date returns `expiration_before_purchase`.
  The check applies when create or restock completion supplies a purchase date, or when an
  item edit supplies either the purchase date or unopened expiration date. If create or
  restock completion defaults the purchase date to today, an already expired item is accepted.
- An opened expiration date before the opening date returns `opened_expiration_before_opened`.
- On edit, leave a field out to keep it. Sending `null` is only allowed for
  `opened_date`, `opened_expiration_date` and `notes`. Setting `opened_date` to
  `null` also clears `opened_expiration_date`.

### Consume and Delete

- **Consume** with `POST /api/items/{id}/consume`. Each request deducts the full
  requested quantity or returns an error. A request above the available stock
  returns `422 consume_exceeds_stock` with `params.available`. An already
  consumed item returns `409 item_already_consumed`. Stock and restock quantities
  stay unchanged on either error.
- Set `add_to_restock: true` in the consume body to queue the amount deducted
  for either a partial or full consume. The operation saves the stock change
  and restock entry together. The response retains the stock fields at the top
  level and includes `restock_item` with the created entry or `null`.
- **Delete** with `DELETE /api/items/{id}`. Add `?add_to_restock=true` to queue
  a pending entry for the stock item's remaining quantity when it is above
  zero. The entry has `source_item_id: null`, and the delete and restock insert
  commit together.

---

## Categories

Inventory categories are stored in a `categories` table. Stock items reference one by
`category_id` (required). Restock items can leave it empty (`category_id` nullable), but
a category is required when a restock item is marked done and moved into stock.
A restock item that points to a category or source item that does not exist is rejected with `400`.

- Two levels at most: top-level category → subcategory.
- Default system categories are seeded on backend startup. Examples: 食品, 药品/健康, 家居清洁,
  个人护理, 宠物, 母婴, 电子/工具, 其他, plus subcategories such as 蔬菜, 肉类, 饮品.
- Users can add their own top-level categories or subcategories. System categories cannot be deleted.
  A category cannot be deleted while it has subcategories or while stock or restock items still use it.
- Moving: `PATCH /api/categories/{id}` with `"parent_id": <top-level id>` moves a user
  subcategory under another parent; `"parent_id": null` moves it to top level. Leaving
  `parent_id` out keeps the current parent. System categories keep their name and parent,
  and a name must be unique under its (new) parent.
- Seeding is idempotent: a missing default subcategory is recreated under its existing parent.
- API: `GET /api/categories` (tree), `GET /api/categories/flat`, `GET /api/categories/{id}`,
  `POST`, `PATCH /api/categories/{id}`, `DELETE /api/categories/{id}`.

### Recipe eligibility (`recipe_usage`)

Each category has a `recipe_usage` value. It controls whether its stock is used by recipe
features: rule-based recommendations, AI today recommendations, Explore, consume preview, and cook.

| Value | Behavior | Default examples |
|---|---|---|
| `always` | Used normally | 蔬菜, 水果, 肉类 |
| `conditional` | Used with reduced weight (match +6 instead of +10; expiring +20 instead of +40) | 饮品, 零食, 冷冻食品, 罐头/包装食品, 即食/熟食, 其他食品, top-level 食品 |
| `never` | Never used, never deducted by cooking | 药品, 宠物, 家居清洁, 个人护理, 未分类 |

A new subcategory inherits its parent's `recipe_usage` unless one is given.

---

## Restock List

A separate management area for tracking items to restock.

Features:

- View pending and done restock items
- Add manual restock items
- Mark items as done (with partial purchase support). Marking an item that is
  already done returns `409 Conflict` and adds nothing to stock; the stock item
  and the restock update are saved together or not at all.
- Add purchased items to the main stock list
- Edit and delete restock items

`POST /api/restock` and `PATCH /api/restock/{id}` trim `name` and reject blank
names with `422`. When supplied, numeric `quantity_value` and
`POST /api/restock/{id}/done`'s `purchased_quantity` must be positive and finite.
NaN and Infinity return `422`.

On `PATCH /api/restock/{id}`, send `null` to clear `notes`, `category_id`,
`quantity_value` or `quantity_unit`. Omit a field to keep its value. A null
`name` returns `422`; an empty object returns `400`.
Responses use `pending` and `done`. Use `/done` to complete a purchase.
Any `status` key in a PATCH request returns `422 restock_status_readonly`.

On `POST /api/restock/{id}/done`, the backend resolves `owner` and `location`
independently. It trims the request value and uses it if nonempty. Otherwise it
uses the corresponding value from the source stock item, if available. If
neither provides a value, the request returns `422 restock_item_invalid` with
`params.field` set to the missing field. The backend derives the stock item's
effective expiration date and status using the same rules as item creation.

### Duplicate check

`GET /api/restock/duplicates?name=<name>` lists pending restock items that look
like the same thing, so the app can offer to edit an existing entry instead of
adding a second one. It is read-only and `POST /api/restock` does not enforce it.

- Two names match when they are equal after trimming and case folding
  (`match_reason: same_name`) or belong to the same ingredient synonym group,
  for example `egg` and `鸡蛋` (`match_reason: synonym`). This is the same rule
  "missing ingredients to restock" uses to skip pending entries.
- There is no substring matching: `egg` does not match `eggplant`, and `鸡蛋`
  does not match `鸭蛋`.
- Done items are ignored.
- `name` is required, 1–255 characters, and not blank; otherwise `422`.

The response has `query` (trimmed), `normalized_name` (the synonym group's
canonical name, or the trimmed name) and `candidates`: restock items in ID
order, each with the usual restock fields plus `match_reason`.

---

## Expiration Reminder

Items are shown as `expiring soon` when within a configurable number of days (default: 2) of their effective expiration date.

- Opened items use the opened expiration date
- Unopened items use the unopened expiration date
- Items with `infinite` expiration are excluded
- Consumed and deleted items are excluded

The backend refreshes stored statuses before listing, searching, or cleaning up stock,
reading reminders, recommending recipes, previewing consumption, and loading Explore
inventory. Changing the reminder window or household timezone also refreshes statuses.
The refresh updates only rows whose status has changed. `GET /api/items/reminders` returns
`expiring soon` items first, then `expired` items, each in id order.

---

## Settings

Manage global app-level settings (`GET` / `PATCH /api/settings`), stored in the database:

- `expiration_reminder_days`: number of days before expiration to trigger `expiring soon` status.
  A whole number from 0 to 365, sent as a number or a numeric string and returned as a string.
  Other values are rejected with `422`.
- `default_locale` (#65): the language of AI-generated text for the whole household: `zh-CN`,
  `en` or `ja`. Tags such as `zh-Hans` or `en-US` are normalized; other values are a `422`.
  `null` (the default) means "follow the device" (`Accept-Language`). See
  [Language of AI output](recipes.md#language-of-ai-output).
- `default_timezone` (#65): an IANA name such as `Asia/Tokyo`, used wherever "today" matters:
  expiring-soon / expired status, the default purchase date, and stock status after cooking.
  `null` (the default) uses the server's local date. An unknown name is a `422`.

Send `""` to clear `default_locale` or `default_timezone` (back to `null`).

`default_database` was removed from the API (the app always uses MySQL); a client that still
sends it is not rejected, the field is ignored. The legacy CLI keeps its own `settings.json`
with `default_database` (see `docs/cli.md`).

---

## Cleanup

Batch removal of records that are no longer needed in daily views:

- Remove done restock items
- Remove consumed stock items (default)
- Remove expired stock items (explicitly requested only)
- Confirmation before deleting

Expired items are not automatically deleted by default because an expired item may still physically exist and require user action.

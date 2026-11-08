# Features

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

### Stock Overview

Displays current stock with:

- Name, category, owner, quantity, unit
- Storage location
- Current effective expiration date
- Status (`active`, `consumed`, `expiring soon`, `expired`)
- Whether notes exist

### Search and Filter

- **Search**: by name, category, owner, location, notes
- **Filters**: by category, owner, location, status

### Edit

Edit one or more fields: name, category, owner, purchase date, quantity, location, expiration dates, notes.
Current expiration date and status are calculated automatically.

Validation (returns `422`):

- Dates must be real calendar dates in `YYYY-MM-DD` form (`2026-02-30` is rejected).
  Expiration dates may also be `infinite`; `purchase_date` and `opened_date` may not.
- On edit, leave a field out to keep it. Sending `null` is only allowed for
  `opened_date`, `opened_expiration_date` and `notes`.

### Consume and Delete

- **Consume**: Partial or full consumption. Status set to `consumed` when quantity reaches zero. Optionally add to restock list.
- **Delete**: Remove stock items. Optionally add to restock list.

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

---

## Expiration Reminder

Items are shown as `expiring soon` when within a configurable number of days (default: 2) of their effective expiration date.

- Opened items use the opened expiration date
- Unopened items use the unopened expiration date
- Items with `infinite` expiration are excluded
- Consumed and deleted items are excluded

---

## Settings

Manage global app-level settings:

- `default_database`: default SQLite database path (CLI only)
- `expiration_reminder_days`: number of days before expiration to trigger `expiring soon` status

Settings are stored in a user-level `settings.json` file.

---

## Cleanup

Batch removal of records that are no longer needed in daily views:

- Remove done restock items
- Remove consumed stock items (default)
- Remove expired stock items (explicitly requested only)
- Confirmation before deleting

Expired items are not automatically deleted by default because an expired item may still physically exist and require user action.

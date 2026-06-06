# Features

Core App features for inventory management.

---

## Stock

### Adding Stock

The app supports recording:

- Name
- Category (vegetable, meat, fruit, medicine, frozen food, pet food, etc.)
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

### Consume and Delete

- **Consume**: Partial or full consumption. Status set to `consumed` when quantity reaches zero. Optionally add to restock list.
- **Delete**: Remove stock items. Optionally add to restock list.

---

## Restock List

A separate management area for tracking items to restock.

Features:

- View pending and done restock items
- Add manual restock items
- Mark items as done (with partial purchase support)
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

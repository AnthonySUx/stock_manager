# Stock Manager

**Stock Manager** is a local Python CLI application for family stock management. It records purchase dates, expiration dates, storage locations, quantities, reminder information, and restocking lists.

The current supported run style is:

```bash
python3 -m stock_manager <command>
```

*Direct `stock` shell command installation is planed but unimplemented yet.*


## Main Features

### 1. Adding stock

The application supports the recording of the following information:

- Name
- Category (e.g., vegetable, meat, fruit, medicine, frozen food, pet food, etc.)
- Purchaser or assigned user
- Date of purchase
- Expiration date when unopened
- Opening date
- Expiration date after opening
- Storage location (e.g., refrigerator, freezer, storage cabinet, etc.)
- Quantity
- Unit (e.g., pieces, blocks, grams, bags, bottles, etc.)
- Notes

For products without an expiration date, enter `infinite`.

### 2. Stock Overview

The application supports viewing current stock and displays:

- Name
- Category
- Purchaser or assigned user
- Quantity and unit
- Storage location
- Current effective expiration date
- Status
- Whether notes exist

Stock status includes:

- `active`
- `consumed`
- `expiring soon`
- `expired`

### 3. Search and Filter

`search`:
- Name
- Category
- Purchaser or assigned user
- Storage location
- Notes
`filters`:
- Category
- Purchaser or assigned user
- Storage location
- Status

### 4. Edit Stock

The stock edit command lets the user select one item, review details, then choose one or more fields to edit.

Editable stock fields are:

- Name
- Category
- Purchaser or assigned user
- Date of purchase
- Quantity
- Storage location
- Expiration dates
- Notes

Current expiration date and status are calculated by the application and are not edited directly.

### 5. Consume and Delete

The application supports partial and full consumption, and completely delete:

`consume`
- Decrease the stock quantity when a portion is consumed.
- Set the status to `consumed` when quantity reaches zero.
- Ask whether to add fully consumed items to the restocking list.
`delete`
- Confirm before deleting stock items.
- After an item is deleted, ask whether to add it to the restocking list.

### 6. Restocking List

Restocking is a separate management area, providing an independent list.`restock`supports:

- View pending and done restock items
- Add manual restock items
- Mark restock items as done
- Track partial purchases and keep remaining quantity pending
- Add purchased restock items to the stock list

### 7. Expiration Reminder

By default, reminders for food nearing expiration are shown 2 days in advance:

- For opened food items, the expiration date after opening applies.
- For unopened food items, the unopened expiration date applies.
- Items with an infinite expiration period are not included in expiration reminders.
- Deleted and consumed food items are not included in expiration reminders.
- Currently the reminder command is manual. It does not run in the background or send notifications automatically.

### 8. Settings

`settings` manages global user-level settings. Currently, it supports editing:

- `default_database`
- `expiration_reminder_days`

Settings are stored in a user-level `settings.json` file, not inside a stock database file.

### 9. Cleanup

The application supports batch removal of records that are no longer useful in daily views:

- Removing done restock items
- Removing consumed stock items by default
- Removing expired stock items only when explicitly requested
- Confirmation before deleting records

`clean stock` defaults to consumed items only. Expired items require `--expired` or `--all` because an expired item may still physically exist at home and require user action.

## Planned Features

The following features are planned but not implemented yet:

- Background expiration reminder checks
- macOS system notifications from inside Stock Manager
- Email alerts
- Weekly shopping-day reminder
- Automatically sending the restock list by email on the configured shopping day
- Automatically cleaning old done restock items after a configured retention period
- Automatically cleaning old consumed inventory items after a configured retention period

Expired items should not be automatically deleted by default.

*Current automatic behavior is limited to command-triggered status refreshes. `list`, `search`, and `remind` refresh item statuses when they run, but Stock Manager does not run by itself in the background yet.*


## Current Usable Commands

During the current development stage, use:

```bash
python3 -m stock_manager <command>
```

Available commands:

```bash
python3 -m stock_manager --help
python3 -m stock_manager --version
python3 -m stock_manager init
python3 -m stock_manager settings
python3 -m stock_manager add
python3 -m stock_manager list
python3 -m stock_manager edit
python3 -m stock_manager consume
python3 -m stock_manager delete
python3 -m stock_manager search
python3 -m stock_manager remind
python3 -m stock_manager clean restock
python3 -m stock_manager clean stock
python3 -m stock_manager restock list
python3 -m stock_manager restock add
python3 -m stock_manager restock done
python3 -m stock_manager restock edit
python3 -m stock_manager restock delete
```

### Command Options

`init` initializes a SQLite database file. By default it creates or updates `stock.db` in the current working directory, unless a default database has been configured with `settings`. The `--database` / `-d` option can be used to create or initialize a different database file.

```bash
python3 -m stock_manager init
python3 -m stock_manager init --database stock.db
python3 -m stock_manager init -d stock.db
python3 -m stock_manager init -d home_stock.db
```

`settings` shows the current global options and lets the user edit one or more settings by number. The settings are stored in a user-level config file `settings.json`.

```bash
python3 -m stock_manager settings
```

Current settings:

- `default_database`: change the default SQLite database path.
- `expiration_reminder_days`: change the number of days before expiration that counts as `expiring soon`. This affects status refreshes and `remind`.

Settings are stored in a user-level config file, not inside a stock database file.

`add` adds one stock item through interactive prompts. Purchase date can be left empty to use today's date.

```bash
python3 -m stock_manager add
python3 -m stock_manager add --database stock.db
python3 -m stock_manager add -d stock.db
```

`list` shows stock items, refreshes item statuses automatically, and supports filters. The table shows whether each item has notes with `Yes` or `-`. After the table, the command can optionally show full details for selected item IDs.

```bash
python3 -m stock_manager list
python3 -m stock_manager list --category fruit
python3 -m stock_manager list --owner Anthony
python3 -m stock_manager list --location fridge
python3 -m stock_manager list --status active
python3 -m stock_manager list --database stock.db
python3 -m stock_manager list -d stock.db
```

`edit` is interactive. The user selects one stock item, reviews its details, then selects one or more field numbers to edit. Pressing Enter keeps the current value. Optional fields can be cleared by typing `none`.

Editable stock fields are name, category, owner, purchase date, quantity, location, expiration, and notes. Quantity edits update quantity value and quantity unit together. Expiration edits update unopened expiration date, opened expiration date, and opened date together. Current expiration date and status are calculated by the application and are not edited directly.

```bash
python3 -m stock_manager edit
python3 -m stock_manager edit --database stock.db
python3 -m stock_manager edit -d stock.db
```

`consume` is interactive. The user selects one or more stock items, enters the consumed quantity, and the command updates the remaining quantity. If an item reaches zero quantity, it is marked as `consumed` and the user is asked whether to add it to the restocking list.

When adding a consumed item to the restocking list, the command reuses the original stock item as defaults. The user can adjust the restock quantity directly, or choose to edit name, category, quantity unit, and notes before saving.

```bash
python3 -m stock_manager consume
python3 -m stock_manager consume --database stock.db
python3 -m stock_manager consume -d stock.db
```

`delete` is interactive. The user selects one or more stock items from the list, then confirms deletion. 

After deleting a stock item, the command asks whether to add it to the restocking list. The command reuses the deleted stock item's details as defaults. The user can adjust the restock quantity directly, or choose to edit name, category, quantity unit, and notes before saving.

```bash
python3 -m stock_manager delete
python3 -m stock_manager delete --database stock.db
python3 -m stock_manager delete -d stock.db
```

`search` refreshes item statuses automatically, then searches stock items by keyword and supports filters.

```bash
python3 -m stock_manager search milk
python3 -m stock_manager search milk --category dairy
python3 -m stock_manager search milk --owner Anthony
python3 -m stock_manager search milk --location fridge
python3 -m stock_manager search milk --status active
python3 -m stock_manager search milk --database stock.db
python3 -m stock_manager search milk -d stock.db
```

`remind` refreshes item statuses automatically and shows expiration reminder information only. This command is manual. It does not run in the background or send notifications automatically yet.

```bash
python3 -m stock_manager remind
python3 -m stock_manager remind --database stock.db
python3 -m stock_manager remind -d stock.db
```

`clean restock` removes old restock history. It only cleans restock items with `done` status. The command shows the items that will be deleted and asks for confirmation.

```bash
python3 -m stock_manager clean restock
python3 -m stock_manager clean restock --database stock.db
python3 -m stock_manager clean restock -d stock.db
```

`clean stock` removes old stock history. By default it only cleans `consumed` stock items. To clean `expired` stock items, explicitly use `--expired`. To clean all (including `consumed` and `expired` stock items), explicitly use `--all`. The command shows the items that will be deleted and asks for confirmation.

```bash
python3 -m stock_manager clean stock
python3 -m stock_manager clean stock --expired
python3 -m stock_manager clean stock --all
python3 -m stock_manager clean stock --database stock.db
python3 -m stock_manager clean stock -d stock.db
```

`restock list` shows restock-list items as a separate management view. The table shows whether each restock item has notes with `Yes` or `-`. After the table, the command can optionally show full details for selected restock item IDs.

```bash
python3 -m stock_manager restock list
python3 -m stock_manager restock list --status pending
python3 -m stock_manager restock list --status done
python3 -m stock_manager restock list --database stock.db
python3 -m stock_manager restock list -d stock.db
```

`restock add` adds one restock-list item through interactive prompts. Name, category, quantity value, and quantity unit are required. Notes are optional.

```bash
python3 -m stock_manager restock add
python3 -m stock_manager restock add --database stock.db
python3 -m stock_manager restock add -d stock.db
```

`restock done` is interactive. The user selects one or more pending restock items and enters the actually purchased quantity. The default purchased quantity is the quantity currently shown in the restock list.

If the purchased quantity is lower than the planned quantity, the command asks whether to keep the unpurchased remainder. If the user keeps the remainder, the current restock item is updated to the remaining quantity and stay `pending`. If the user does not keep the remainder, the item is marked as `done`.

If the purchased quantity is greater than zero, `restock done` asks whether to add the purchased quantity to the normal stock list. When adding it to stock, the command reuses the restock item's name, category, quantity unit, quantity value, and notes as defaults. If the restock item came from an original stock item, owner and location should also default to the original stock item values. If the original stock item cannot be found, owner and location are entered manually.

```bash
python3 -m stock_manager restock done
python3 -m stock_manager restock done --database stock.db
python3 -m stock_manager restock done -d stock.db
```

`restock edit` is interactive. The user selects one restock item, reviews its details, then selects one or more field numbers to edit. Pressing Enter keeps the current value. Optional fields can be cleared by typing `none`.

Editable restock fields are name, category, quantity, and notes. Quantity edits update quantity value and quantity unit together. Restock status is not edited directly; use `restock done` to mark pending items as done.

```bash
python3 -m stock_manager restock edit
python3 -m stock_manager restock edit --database stock.db
python3 -m stock_manager restock edit -d stock.db
```

`restock delete` is interactive. The user selects one or more restock-list items from the list, then confirms deletion.

```bash
python3 -m stock_manager restock delete
python3 -m stock_manager restock delete --database stock.db
python3 -m stock_manager restock delete -d stock.db
```

# Stock Manager

**Stock Manager** is a local Python application for family stock management. The objective of this project is to record purchase date, expiration date, storage location, quantity, and send notifications and restocking-list reminders accordingly.

*Version 1* only provides a CLI interface.

## Core objective

- Record family stock
- Supports searching by user, category, location, and keyword.
- Supports different expiration periods for unopened and opened products.
- Supports food with no expiration date by saving the expiration period as infinite.
- Supports consumption, deletion, and restocking.
- Supports macOS system notifications.
- Supports email notifications, making it easy to receive alerts in your mobile email app.
- Supports sending shopping list on fixed weekly shopping days.

## Main Features

### 1. Adding stock

The application supports the recording of the following information:

- Name
- Category (e.g., vegetable, meat, fruit, medicine, frozen food, pet food, etc.)
- Purchaser or assigned user
- Date of purchase
- Expiration date when unopened
- Opened or unopened
- Opening date
- Expiration date after opening
- Storage location (e.g., refrigerator, freezer, storage cabinet, etc.)
- Quantity
- Unit (e.g., pieces, blocks, grams, bags, bottles, etc.)
- Notes

For products without an expiration date, the user should still enter an expiration value, but the value should be saved as infinite.

### 2. Stock Overview

The application must support viewing current available stock and display:

- Name
- Category
- Purchaser or assigned user
- Quantity and unit
- Storage location
- Current effective expiration date
- Status
- Note

Stock status includes:

- `active`
- `consumed`
- `expiring soon`
- `expired`

### 3. Consume and Delete

The application supports opening, partial consumption, and full consumption.

Rule:

* After opening, ask for the date of opening and the expiration date after opening.
* Decrease the stock quantity when a portion is consumed.
* Set the status to `consumed` when the quantity reaches zero.
* When an item is deleted, confirm the command and remove the item from the stock records.
* After an item is fully consumed or deleted, ask whether to add it to the restocking list.

### 4. Validation of Required Information

When adding or editing inventory, the following fields must be filled in:

* Opened or unopened

If opened: 

- Name
- Category (e.g., vegetable, meat, fruit, medicine, frozen food, pet food, etc.)
- Purchaser or assigned user
- Date of purchase
- Opening date
- Expiration date after opening
- Storage location (e.g., refrigerator, freezer, storage cabinet, etc.)
- Quantity
- Unit (e.g., pieces, blocks, grams, bags, bottles, etc.)

If unopened:

- Name
- Category
- Purchaser or assigned user
- Date of purchase
- Expiration date when unopened
- Storage location
- Quantity
- Unit (e.g., pieces, blocks, grams, bags, bottles, etc.)

If a product has no expiration date, the expiration value should be entered as infinite.

If required information is missing, the CLI should immediately prompt the user to provide it, rather than saving incomplete data.

### 5. Search and Filter

The search scope includes:

- Name
- Category
- Purchaser or assigned user
- Storage location
- Note

Support filtering based on the following criteria:

- Category
- Purchaser or assigned user
- Storage location
- Expiring soon
- Expired

### 6. Restocking List

In the following scenarios, ask whether to add the item to the restocking list:

- The food has expired
- The food has been consumed
- The food has been manually deleted

Restocking is a separate management area, not just a one-time reminder output.

The restock module should provide detailed restock-list management:

- View pending and completed restock items
- Add a manual restock item
- Mark a restock item as done
- Delete a restock item
- Show notes for each restock item

The restock list should not be cleared automatically. Items should only be marked as done manually.

### 7. Expiration Reminder

By default, reminders for food nearing its expiration date are sent 2 days in advance.

Rule:

- For opened food items, the expiration date after opening applies.
- For unopened food items, the expiration date on the package applies.
- Items with an infinite expiration period are not included in expiration reminders.
- Deleted and consumed food items are not included in expiration reminders.
- The reminder module should focus on reminder information only. It should not be the detailed restock-list management view.
- The current reminder command is manual. It does not run in the background or send notifications automatically yet.

### 8. Weekly Shopping Day Reminder

The application supports setting a fixed weekly shopping day.

When the reminder command is executed on a shopping day, it may show a short shopping-day notice and point the user to the restock command for details. Detailed restock-list output belongs to the restock module.

### 9. Cleanup

The application provides a separate cleanup command for batch removal of old records that are no longer useful in daily views.

Cleanup should support:

- Removing old done restock items
- Removing consumed stock items by default
- Removing expired stock items only when explicitly requested
- Retention rules such as older-than N days
- Confirmation before deleting records

*`clean stock` default to consumed items only. Expired items should require an explicit option because an expired item may still physically exist at home and require user action.*

### 10. Notification Method

The first version supports two notification methods:

- macOS system notifications
- Email alerts

macOS notifications are enabled by default.

*Email alerts are an optional feature. If no email address is configured, the application should not stop running; it should simply display a message in the CLI indicating that email alerts are not configured.*


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
python3 -m stock_manager add
python3 -m stock_manager list
python3 -m stock_manager search
python3 -m stock_manager remind
python3 -m stock_manager restock list
python3 -m stock_manager restock add
python3 -m stock_manager restock done
python3 -m stock_manager restock delete
```

### Command Options

`init` initializes the local SQLite database.

```bash
python3 -m stock_manager init
python3 -m stock_manager init --database stock.db
python3 -m stock_manager init -d stock.db
```

`add` adds one stock item through interactive prompts. Purchase date can be left empty to use today's date.

```bash
python3 -m stock_manager add
python3 -m stock_manager add --database stock.db
python3 -m stock_manager add -d stock.db
```

`list` shows stock items, refreshes item statuses automatically, and supports filters.

```bash
python3 -m stock_manager list
python3 -m stock_manager list --category fruit
python3 -m stock_manager list --owner Anthony
python3 -m stock_manager list --location fridge
python3 -m stock_manager list --status active
python3 -m stock_manager list --database stock.db
python3 -m stock_manager list -d stock.db
```

`search` refreshes item statuses automatically, then searches stock items by keyword and supports filters.

```bash
python3 -m stock_manager search milk
python3 -m stock_manager search milk --owner Anthony
python3 -m stock_manager search milk --location fridge
python3 -m stock_manager search milk --database stock.db
python3 -m stock_manager search milk -d stock.db
```

`remind` refreshes item statuses automatically and shows expiration reminder information only. This command is manual. It does not run in the background or send notifications automatically yet.

```bash
python3 -m stock_manager remind
python3 -m stock_manager remind --database stock.db
python3 -m stock_manager remind -d stock.db
```

`restock list` shows restock-list items as a separate management view.

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

```bash
python3 -m stock_manager restock done
python3 -m stock_manager restock done --database stock.db
python3 -m stock_manager restock done -d stock.db
```

`restock delete` is interactive. The user selects one or more restock-list items from the list, then confirms deletion.

```bash
python3 -m stock_manager restock delete
python3 -m stock_manager restock delete --database stock.db
python3 -m stock_manager restock delete -d stock.db
```

### Planned Command Design

The following commands are planned but not implemented yet.

The clean command group should later support removing old records that are no longer useful in daily views.

```bash
python3 -m stock_manager clean restock
python3 -m stock_manager clean stock
python3 -m stock_manager clean stock --expired
python3 -m stock_manager clean stock --all
```

Cleanup commands are planned because old `done`, `consumed`, and historical records can make the useful list harder to scan.

`clean restock` should support manually deleting old done restock items, with confirmation by default.

`clean stock` should support manually cleaning consumed stock history by default. Expired stock items should only be removed when the user explicitly passes `--expired` or `--all`. All cleanup commands should require confirmation by default.

Single stock item deletion should belong to the normal stock delete command, not to cleanup.

Reminder and restock are intentionally separate:

- `remind` is a short reminder view for expired and expiring-soon stock.
- `restock` is the detailed restock-list management area.
- `remind` may point users to `restock`, but it should not replace the restock management commands.

### Planned Automation

The following automation features are planned but not implemented yet:

- Background expiration reminder checks. The current `remind` command is manual.
- macOS system notifications from inside Stock Manager.
- Email alerts for expiration reminders.
- A settings command for reminder days, shopping day, and notification preferences.
- Weekly shopping-day reminder logic.
- Automatically sending the restock list by email on the configured shopping day.
- Automatically cleaning old done restock items after a configured retention period.
- Automatically cleaning old consumed inventory items after a configured retention period.
- Expired items should not be automatically deleted by default.
- A macOS LaunchAgent or equivalent scheduler for running reminders automatically.

Current automatic behavior is limited to command-triggered status refreshes. `list`, `search`, and `remind` refresh item statuses when they run, but Stock Manager does not run by itself in the background yet.

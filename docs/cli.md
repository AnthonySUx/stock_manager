# Stock Manager CLI

**Status**: Legacy / local-only workflow

The original command-line interface is still available for local stock management. It uses **SQLite** (not MySQL) and does not require Docker or a running API server.

> **Note**: The CLI and the App/API use **different databases**. The CLI uses local SQLite files; the App uses MySQL via the API. They are not automatically synced.

---

## Quick Start

```bash
python3 -m stock_manager --help
python3 -m stock_manager init
python3 -m stock_manager add
python3 -m stock_manager list
```

### Available Commands

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

---

## Features

### 1. Adding Stock

Records:

- Name
- Category (vegetable, meat, fruit, medicine, frozen food, pet food, etc.)
- Purchaser or assigned user
- Date of purchase
- Expiration date when unopened
- Opening date
- Expiration date after opening
- Storage location (refrigerator, freezer, storage cabinet, etc.)
- Quantity
- Unit (pieces, blocks, grams, bags, bottles, etc.)
- Notes

For products without an expiration date, enter `infinite`.

### 2. Stock Overview

Shows current stock with:

- Name, category, owner, quantity, unit
- Storage location
- Current effective expiration date
- Status (active / consumed / expiring soon / expired)
- Whether notes exist

### 3. Search and Filter

`search` by: name, category, owner, location, notes.
`filters`: category, owner, location, status.

### 4. Edit Stock

Interactive selection, then edit one or more fields.
Editable: name, category, owner, purchase date, quantity, location, expiration dates, notes.
Current expiration date and status are calculated automatically.

### 5. Consume and Delete

- `consume`: Partial or full consumption. Status set to `consumed` when quantity reaches zero. Optionally add to restock list.
- `delete`: Remove stock items. Optionally add to restock list.

### 6. Restocking List

```bash
python3 -m stock_manager restock list
python3 -m stock_manager restock add
python3 -m stock_manager restock done
python3 -m stock_manager restock edit
python3 -m stock_manager restock delete
```

- View pending and done restock items
- Add manual restock items
- Mark restock items as done
- Track partial purchases and keep remaining quantity pending
- Add purchased restock items to the stock list

### 7. Expiration Reminder

```bash
python3 -m stock_manager remind
```

Shows items expiring within a configurable number of days (default: 2).
Manual command — does not run in the background.

### 8. Settings

```bash
python3 -m stock_manager settings
```

Settings are stored in a user-level `settings.json` file:

- `default_database`: default SQLite database path
- `expiration_reminder_days`: days before expiration to show as "expiring soon"

### 9. Cleanup

```bash
python3 -m stock_manager clean restock    # Remove done restock items
python3 -m stock_manager clean stock      # Remove consumed stock items
python3 -m stock_manager clean stock --expired  # Also remove expired items
python3 -m stock_manager clean stock --all      # Remove both consumed and expired
```

---

## Command Options

Most commands accept `--database` / `-d` to specify a SQLite database file:

```bash
python3 -m stock_manager init
python3 -m stock_manager init --database stock.db
python3 -m stock_manager init -d stock.db
```

---

## Database

The CLI uses **SQLite** files. By default, it creates `stock.db` in the current working directory, unless a default database has been configured with `settings`.

The App/API uses **MySQL**. See [App Docs](app.md) for details.

---

## Project Context

```
stock_manager/
  api/             # FastAPI backend (App)
  cli.py           # Original CLI entry point
  database.py      # SQLite database layer
  config.py        # Configuration
scripts/           # Helper scripts
frontend/          # Expo + React Native app
docker-compose.yml # MySQL 8 (for App/API only)
```

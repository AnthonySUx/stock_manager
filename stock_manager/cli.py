"""Command-line interface for Stock Manager."""

from datetime import date
from pathlib import Path
from typing import Any, Optional

import typer
import typer.rich_utils
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from stock_manager.database import (
    DEFAULT_DATABASE_PATH,
    add_item,
    add_restock_item,
    delete_restock_item,
    get_item,
    initialize_database,
    list_items as fetch_items,
    list_restock_items as fetch_restock_items,
    mark_restock_item_done,
    search_items as fetch_search_items,
    update_restock_item_quantity,
)

PURPLE = "#8b5cf6"

typer.rich_utils.STYLE_OPTION = f"bold {PURPLE}"
typer.rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = f"bold {PURPLE}"
typer.rich_utils.STYLE_SWITCH = f"bold {PURPLE}"
typer.rich_utils.STYLE_NEGATIVE_OPTION = f"bold {PURPLE}"

APP_HELP = """\b
[bold #8b5cf6]  ____  _             _[/bold #8b5cf6]
[bold #8b5cf6] / ___|| |_ ___   ___| | __[/bold #8b5cf6]
[bold #8b5cf6] \\___ \\| __/ _ \\ / __| |/ /[/bold #8b5cf6]
[bold #8b5cf6]  ___) | || (_) | (__|   <[/bold #8b5cf6]
[bold #8b5cf6] |____/ \\__\\___/ \\___|_|\\_\\ [/bold #8b5cf6]
Stock Manager

Manage family stock, expiration reminders, and restocking lists.
"""

app = typer.Typer(
    help=APP_HELP,
    invoke_without_command=True,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
restock_app = typer.Typer(
    help="Manage restock list items.",
    invoke_without_command=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(restock_app, name="restock")
console = Console(width=100)


def _not_implemented(command_name: str) -> None:
    """Show a consistent placeholder message for planned commands."""
    console.print(f"[yellow]{command_name} is not implemented yet.[/yellow]")


def _prompt_required(label: str) -> str:
    """Prompt until the user enters a non-empty value."""
    while True:
        value = Prompt.ask(f"[bold red][Required][/bold red] [bold {PURPLE}]{label}[/bold {PURPLE}]").strip()
        if value:
            return value
        console.print("[red]This field is required.[/red]")


def _prompt_required_with_default(label: str, default: Optional[str]) -> str:
    """Prompt for a required value, defaulting on empty input when provided."""
    if not default:
        return _prompt_required(label)

    prompt = f"[bold red][Required][/bold red] [bold {PURPLE}]{label}[/bold {PURPLE}] [dim][{default}][/dim]"
    while True:
        value = Prompt.ask(prompt, default=default, show_default=False).strip()
        if value:
            return value
        console.print("[red]This field is required.[/red]")


def _prompt_optional(label: str, guidance: str | None = None) -> Optional[str]:
    """Prompt for an optional value and normalize empty input to None."""
    prompt = f"[bold green][Optional][/bold green] [bold {PURPLE}]{label}[/bold {PURPLE}]"
    if guidance is not None:
        prompt = f"{prompt} [dim]{guidance}[/dim]"
    value = Prompt.ask(
        prompt,
        default="",
        show_default=False,
    ).strip()
    return value or None


def _prompt_optional_with_default(label: str, default: Optional[str]) -> Optional[str]:
    """Prompt for an optional value with a visible default."""
    if not default:
        return _prompt_optional(label)

    value = Prompt.ask(
        f"[bold green][Optional][/bold green] [bold {PURPLE}]{label}[/bold {PURPLE}] [dim][{default}][/dim]",
        default=default,
        show_default=False,
    ).strip()
    return value or None


def _prompt_date_or_infinite(label: str, required: bool) -> Optional[str]:
    """Prompt for an ISO date or infinite."""
    while True:
        if required:
            prompt_label = f"{label} | [dim]YYYY-MM-DD or infinite[/dim]"
            value = _prompt_required(prompt_label)
        else:
            value = _prompt_optional(label, "YYYY-MM-DD or infinite")
            if value is None:
                return None

        normalized = value.strip().lower()
        if normalized == "infinite":
            return "infinite"

        try:
            date.fromisoformat(normalized)
        except ValueError:
            console.print("[red]Use YYYY-MM-DD or infinite.[/red]")
            continue

        return normalized


def _prompt_required_date(label: str) -> str:
    """Prompt for a required ISO date."""
    prompt_label = f"{label} | [dim]YYYY-MM-DD[/dim]"
    while True:
        value = _prompt_required(prompt_label)
        try:
            date.fromisoformat(value)
        except ValueError:
            console.print("[red]Use YYYY-MM-DD.[/red]")
            continue
        return value


def _prompt_purchase_date() -> str:
    """Prompt for purchase date, defaulting to today's date on empty input."""
    today = date.today().isoformat()
    prompt = (
        f"[bold red][Required][/bold red] "
        f"[bold {PURPLE}]Purchase date[/bold {PURPLE}] "
        f"[dim]YYYY-MM-DD [{today}][/dim]"
    )
    while True:
        value = Prompt.ask(prompt, default="", show_default=False).strip()
        if not value:
            return today

        try:
            date.fromisoformat(value)
        except ValueError:
            console.print("[red]Use YYYY-MM-DD or press Enter for today.[/red]")
            continue

        return value


def _prompt_optional_date(label: str) -> Optional[str]:
    """Prompt for an optional ISO date."""
    while True:
        value = _prompt_optional(label, "YYYY-MM-DD")
        if value is None:
            return None

        try:
            date.fromisoformat(value)
        except ValueError:
            console.print("[red]Use YYYY-MM-DD.[/red]")
            continue

        return value


def _prompt_quantity_value() -> float:
    """Prompt until the user enters a positive quantity number."""
    while True:
        value = _prompt_required("Quantity value")
        try:
            quantity = float(value)
        except ValueError:
            console.print("[red]Quantity value must be a number.[/red]")
            continue

        if quantity <= 0:
            console.print("[red]Quantity value must be greater than 0.[/red]")
            continue

        return quantity


def _prompt_nonnegative_quantity(label: str, default: float) -> float:
    """Prompt until the user enters a non-negative quantity number."""
    default_text = f"{default:g}"
    while True:
        value = Prompt.ask(
            f"[bold red][Required][/bold red] [bold {PURPLE}]{label}[/bold {PURPLE}] "
            f"[dim][{default_text}][/dim]",
            default=default_text,
            show_default=False,
        ).strip()
        try:
            quantity = float(value)
        except ValueError:
            console.print("[red]Quantity value must be a number.[/red]")
            continue

        if quantity < 0:
            console.print("[red]Quantity value cannot be negative.[/red]")
            continue

        return quantity


def _format_quantity(quantity_value: float, quantity_unit: str) -> str:
    """Format quantity without a trailing .0 for whole numbers."""
    if quantity_value.is_integer():
        return f"{int(quantity_value)} {quantity_unit}"
    return f"{quantity_value:g} {quantity_unit}"


def _format_status(status: str) -> str:
    """Apply a visual color to a stock status value."""
    status_styles = {
        "active": "green",
        "expiring soon": "yellow",
        "expired": "red",
        "consumed": "dim",
        "pending": "yellow",
        "done": "green",
    }
    style = status_styles.get(status, "white")
    return f"[{style}]{status}[/{style}]"


def _format_optional(value: Any) -> str:
    """Format nullable values for table output."""
    if value is None or value == "":
        return "-"
    return str(value)


def _show_items_table(rows: list[Any], title: str) -> None:
    """Render stock items with the standard Stock Manager table style."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        border_style=PURPLE,
        header_style=f"bold {PURPLE}",
        title_style="bold",
    )
    table.add_column("ID", justify="right", overflow="fold")
    table.add_column("Name", overflow="fold")
    table.add_column("Category", overflow="fold")
    table.add_column("Owner", overflow="fold")
    table.add_column("Quantity", overflow="fold")
    table.add_column("Location", overflow="fold")
    table.add_column("Expiration", overflow="fold")
    table.add_column("Status", overflow="fold")

    for row in rows:
        table.add_row(
            str(row["id"]),
            row["name"],
            row["category"],
            row["owner"],
            _format_quantity(row["quantity_value"], row["quantity_unit"]),
            row["location"],
            row["current_expiration_date"],
            _format_status(row["status"]),
        )

    console.print(table)


def _show_restock_table(rows: list[Any], title: str) -> None:
    """Render restock items with detailed restock-list fields."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        border_style=PURPLE,
        header_style=f"bold {PURPLE}",
        title_style="bold",
    )
    table.add_column("ID", justify="right", overflow="fold")
    table.add_column("Name", overflow="fold")
    table.add_column("Category", overflow="fold")
    table.add_column("Quantity", overflow="fold")
    table.add_column("Status", overflow="fold")
    table.add_column("Created", overflow="fold")
    table.add_column("Notes", overflow="fold")

    for row in rows:
        quantity = "-"
        if row["quantity_value"] is not None and row["quantity_unit"]:
            quantity = _format_quantity(row["quantity_value"], row["quantity_unit"])

        table.add_row(
            str(row["id"]),
            row["name"],
            _format_optional(row["category"]),
            quantity,
            _format_status(row["status"]),
            row["created_at"],
            _format_optional(row["notes"]),
        )

    console.print(table)


def _parse_restock_ids(value: str, valid_ids: set[int], missing_message: str) -> list[int] | None:
    """Parse a comma-separated restock id selection."""
    selected_ids: list[int] = []
    for raw_id in value.split(","):
        raw_id = raw_id.strip()
        if not raw_id:
            continue

        try:
            item_id = int(raw_id)
        except ValueError:
            console.print(f"[red]Invalid restock item id:[/red] {raw_id}")
            return None

        if item_id not in valid_ids:
            console.print(f"[red]{missing_message.format(item_id=item_id)}[/red]")
            return None

        if item_id not in selected_ids:
            selected_ids.append(item_id)

    if not selected_ids:
        console.print("[red]Select at least one restock item id.[/red]")
        return None

    return selected_ids


def _add_purchased_restock_to_stock(row: Any, purchased_quantity: float, database: Path) -> None:
    """Prompt for stock-specific fields and add a purchased restock item to stock."""
    quantity_unit = row["quantity_unit"]
    if purchased_quantity <= 0 or not quantity_unit:
        return

    if not Confirm.ask(
        f"Add purchased {_format_quantity(purchased_quantity, quantity_unit)} {row['name']} to stock list?",
        default=True,
    ):
        return

    console.print(
        Panel.fit(
            f"[bold]Add purchased {row['name']} to stock[/bold]",
            border_style=PURPLE,
        )
    )

    source_item = None
    if row["source_item_id"] is not None:
        source_item = get_item(int(row["source_item_id"]), database)

    category = row["category"] or _prompt_required("Category")
    owner_default = source_item["owner"] if source_item is not None else None
    location_default = source_item["location"] if source_item is not None else None

    owner = _prompt_required_with_default("Owner", owner_default)
    purchase_date = _prompt_purchase_date()
    location = _prompt_required_with_default("Location", location_default)
    unopened_expiration_date = _prompt_date_or_infinite("Unopened expiration date", required=True)
    opened_expiration_date = _prompt_date_or_infinite("Opened expiration date", required=False)
    opened_date = _prompt_optional_date("Opened date")
    current_expiration_date = (
        opened_expiration_date
        if opened_date is not None and opened_expiration_date is not None
        else unopened_expiration_date
    )
    notes = _prompt_optional_with_default("Notes", row["notes"])

    item_id = add_item(
        {
            "name": row["name"],
            "category": category,
            "owner": owner,
            "purchase_date": purchase_date,
            "quantity_value": purchased_quantity,
            "quantity_unit": quantity_unit,
            "location": location,
            "unopened_expiration_date": unopened_expiration_date,
            "opened_expiration_date": opened_expiration_date,
            "opened_date": opened_date,
            "current_expiration_date": current_expiration_date,
            "status": "active",
            "notes": notes,
        },
        database,
    )
    console.print(f"[green]Added stock item #{item_id} from restock:[/green] {row['name']}")


@app.command()
def init(
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Initialize the local Stock Manager database."""
    database_path = initialize_database(Path(database))
    console.print(f"[green]Initialized database:[/green] {database_path}")


@app.command()
def add(
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Add a new stock item."""
    console.print(
        Panel.fit(
            "[bold]Add a stock item[/bold]",
            border_style=PURPLE,
        )
    )

    name = _prompt_required("Name")
    category = _prompt_required("Category")
    owner = _prompt_required("Owner")
    purchase_date = _prompt_purchase_date()
    quantity_value = _prompt_quantity_value()
    quantity_unit = _prompt_required("Quantity unit")
    location = _prompt_required("Location")
    unopened_expiration_date = _prompt_date_or_infinite("Unopened expiration date", required=True)
    opened_expiration_date = _prompt_date_or_infinite("Opened expiration date", required=False)
    opened_date = _prompt_optional_date("Opened date")

    current_expiration_date = (
        opened_expiration_date
        if opened_date is not None and opened_expiration_date is not None
        else unopened_expiration_date
    )
    notes = _prompt_optional("Notes")

    item_id = add_item(
        {
            "name": name,
            "category": category,
            "owner": owner,
            "purchase_date": purchase_date,
            "quantity_value": quantity_value,
            "quantity_unit": quantity_unit,
            "location": location,
            "unopened_expiration_date": unopened_expiration_date,
            "opened_expiration_date": opened_expiration_date,
            "opened_date": opened_date,
            "current_expiration_date": current_expiration_date,
            "status": "active",
            "notes": notes,
        },
        Path(database),
    )

    console.print(f"[green]Added item #{item_id}:[/green] {name}")


@app.command(name="list")
def list_items(
    category: Optional[str] = typer.Option(None, help="Filter by category."),
    owner: Optional[str] = typer.Option(None, help="Filter by purchaser or assigned user."),
    location: Optional[str] = typer.Option(None, help="Filter by storage location."),
    status: Optional[str] = typer.Option(None, help="Filter by stock status."),
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Show current stock items."""
    rows = fetch_items(
        category=category,
        owner=owner,
        location=location,
        status=status,
        database_path=Path(database),
    )

    if not rows:
        console.print("[yellow]No stock items found.[/yellow]")
        return

    _show_items_table(rows, "Stock Items")


@app.command()
def search(
    keyword: str = typer.Argument(..., help="Keyword to search in stock items."),
    category: Optional[str] = typer.Option(None, help="Filter by category."),
    owner: Optional[str] = typer.Option(None, help="Filter by purchaser or assigned user."),
    location: Optional[str] = typer.Option(None, help="Filter by storage location."),
    status: Optional[str] = typer.Option(None, help="Filter by stock status."),
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Search stock items by keyword."""
    rows = fetch_search_items(
        keyword,
        category=category,
        owner=owner,
        location=location,
        status=status,
        database_path=Path(database),
    )

    if not rows:
        console.print("[yellow]No matching stock items found.[/yellow]")
        return

    _show_items_table(rows, f'Search Results for "{keyword}"')


@app.command()
def remind(
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Show expiration reminder information."""
    expired_rows = fetch_items(status="expired", database_path=Path(database))
    expiring_soon_rows = fetch_items(status="expiring soon", database_path=Path(database))

    if not expired_rows and not expiring_soon_rows:
        console.print("[green]No expiration reminders for now.[/green]")
        return

    console.print(Panel.fit("[bold]Expiration Reminders[/bold]", border_style=PURPLE))

    if expired_rows:
        _show_items_table(expired_rows, "Expired Items")

    if expiring_soon_rows:
        _show_items_table(expiring_soon_rows, "Expiring Soon")


@restock_app.command(name="list")
def list_restock(
    status: Optional[str] = typer.Option(None, help="Filter by restock status: pending or done."),
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Show restock list items."""
    rows = fetch_restock_items(status=status, database_path=Path(database))

    if not rows:
        console.print("[yellow]No restock items found.[/yellow]")
        return

    _show_restock_table(rows, "Restock Items")


@restock_app.command(name="add")
def add_restock(
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Add a new restock list item."""
    console.print(
        Panel.fit(
            "[bold]Add a restock item[/bold]",
            border_style=PURPLE,
        )
    )

    name = _prompt_required("Name")
    category = _prompt_required("Category")
    quantity_value = _prompt_quantity_value()
    quantity_unit = _prompt_required("Quantity unit")
    notes = _prompt_optional("Notes")

    item_id = add_restock_item(
        {
            "name": name,
            "category": category,
            "quantity_value": quantity_value,
            "quantity_unit": quantity_unit,
            "status": "pending",
            "notes": notes,
        },
        Path(database),
    )

    console.print(f"[green]Added restock item #{item_id}:[/green] {name}")


@restock_app.command(name="done")
def done_restock(
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Interactively mark pending restock items as done."""
    pending_rows = fetch_restock_items(status="pending", database_path=Path(database))

    if not pending_rows:
        console.print("[yellow]No pending restock items found.[/yellow]")
        return

    _show_restock_table(pending_rows, "Pending Restock Items")
    pending_by_id = {int(row["id"]): row for row in pending_rows}

    while True:
        selected = Prompt.ask(
            f"[bold red][Required][/bold red] [bold {PURPLE}]Restock item IDs[/bold {PURPLE}] "
            "[dim]comma-separated[/dim]"
        )
        selected_ids = _parse_restock_ids(
            selected,
            set(pending_by_id),
            "Restock item #{item_id} is not pending or does not exist.",
        )
        if selected_ids is not None:
            break

    for item_id in selected_ids:
        row = pending_by_id[item_id]
        planned_quantity = row["quantity_value"]
        quantity_unit = row["quantity_unit"]

        if planned_quantity is None or not quantity_unit:
            if Confirm.ask(f"Mark restock item #{item_id} {row['name']} as done?", default=True):
                mark_restock_item_done(item_id, Path(database))
                console.print(f"[green]Marked restock item #{item_id} as done.[/green]")
            continue

        planned_quantity = float(planned_quantity)
        purchased_quantity = _prompt_nonnegative_quantity(
            f"Purchased quantity for {row['name']} [{_format_quantity(planned_quantity, quantity_unit)}]",
            planned_quantity,
        )

        if purchased_quantity >= planned_quantity:
            mark_restock_item_done(item_id, Path(database))
            console.print(f"[green]Marked restock item #{item_id} as done.[/green]")
            _add_purchased_restock_to_stock(row, purchased_quantity, Path(database))
            continue

        remaining_quantity = planned_quantity - purchased_quantity
        keep_remaining = Confirm.ask(
            (
                f"Only {_format_quantity(purchased_quantity, quantity_unit)} of "
                f"{_format_quantity(planned_quantity, quantity_unit)} was bought. "
                f"Keep remaining {_format_quantity(remaining_quantity, quantity_unit)} in restock list?"
            ),
            default=True,
        )

        if keep_remaining:
            update_restock_item_quantity(item_id, remaining_quantity, Path(database))
            console.print(
                f"[yellow]Kept restock item #{item_id} pending with "
                f"{_format_quantity(remaining_quantity, quantity_unit)} remaining.[/yellow]"
            )
            _add_purchased_restock_to_stock(row, purchased_quantity, Path(database))
        else:
            mark_restock_item_done(item_id, Path(database))
            console.print(f"[green]Marked restock item #{item_id} as done.[/green]")
            _add_purchased_restock_to_stock(row, purchased_quantity, Path(database))


@restock_app.command(name="delete")
def delete_restock(
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Interactively delete restock list items."""
    rows = fetch_restock_items(database_path=Path(database))

    if not rows:
        console.print("[yellow]No restock items found.[/yellow]")
        return

    _show_restock_table(rows, "Restock Items")
    rows_by_id = {int(row["id"]): row for row in rows}

    while True:
        selected = Prompt.ask(
            f"[bold red][Required][/bold red] [bold {PURPLE}]Restock item IDs[/bold {PURPLE}] "
            "[dim]comma-separated[/dim]"
        )
        selected_ids = _parse_restock_ids(
            selected,
            set(rows_by_id),
            "Restock item #{item_id} does not exist.",
        )
        if selected_ids is not None:
            break

    names = ", ".join(f"#{item_id} {rows_by_id[item_id]['name']}" for item_id in selected_ids)
    if not Confirm.ask(f"Delete restock item(s): {names}?", default=False):
        console.print("[yellow]Delete cancelled.[/yellow]")
        return

    for item_id in selected_ids:
        row = rows_by_id[item_id]
        delete_restock_item(item_id, Path(database))
        console.print(f"[green]Deleted restock item #{item_id}:[/green] {row['name']}")


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the application version and exit.",
        is_eager=True,
    ),
) -> None:
    """Stock Manager CLI."""
    if version:
        from stock_manager import __version__

        console.print(f"stock-manager {__version__}")
        raise typer.Exit()

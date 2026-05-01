"""Command-line interface for Stock Manager."""

from datetime import date
from pathlib import Path
from typing import Any, Optional

import typer
import typer.rich_utils
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from stock_manager.database import (
    DEFAULT_DATABASE_PATH,
    add_item,
    initialize_database,
    list_items as fetch_items,
    search_items as fetch_search_items,
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


def _format_quantity(quantity_value: float, quantity_unit: str) -> str:
    """Format quantity without a trailing .0 for whole numbers."""
    if quantity_value.is_integer():
        return f"{int(quantity_value)} {quantity_unit}"
    return f"{quantity_value:g} {quantity_unit}"


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
            row["status"],
        )

    console.print(table)


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
    purchase_date = _prompt_required_date("Purchase date")
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
    owner: Optional[str] = typer.Option(None, help="Filter by purchaser or assigned user."),
    location: Optional[str] = typer.Option(None, help="Filter by storage location."),
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
        owner=owner,
        location=location,
        database_path=Path(database),
    )

    if not rows:
        console.print("[yellow]No matching stock items found.[/yellow]")
        return

    _show_items_table(rows, f'Search Results for "{keyword}"')


@app.command()
def remind() -> None:
    """Show expiration and restocking reminders."""
    _not_implemented("stock remind")


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

"""Command-line interface for Stock Manager."""

from datetime import date
from pathlib import Path
from typing import Any, Optional

import typer
import typer.rich_utils
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from stock_manager.database import (
    DEFAULT_DATABASE_PATH,
    add_item,
    add_restock_item,
    calculate_item_status,
    delete_item,
    delete_restock_item,
    get_item,
    get_restock_item,
    initialize_database,
    list_items as fetch_items,
    list_restock_items as fetch_restock_items,
    mark_restock_item_done,
    search_items as fetch_search_items,
    update_item,
    update_item_quantity,
    update_restock_item,
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

    prompt = (
        f"[bold red][Required][/bold red] [bold {PURPLE}]{label}[/bold {PURPLE}] "
        f"[dim]{escape(f'[{default}]')}[/dim]"
    )
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
        f"[bold green][Optional][/bold green] [bold {PURPLE}]{label}[/bold {PURPLE}] "
        f"[dim]{escape(f'[{default}]')}[/dim]",
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


def _prompt_edit_required(label: str, current: Any) -> str:
    """Prompt for an editable required value, keeping current on empty input."""
    return _prompt_required_with_default(label, str(current))


def _prompt_edit_optional(label: str, current: Any) -> Optional[str]:
    """Prompt for an editable optional value, keeping current on empty input."""
    current_text = "" if current is None else str(current)
    value = Prompt.ask(
        f"[bold green][Optional][/bold green] [bold {PURPLE}]{label}[/bold {PURPLE}] "
        f"[dim]{escape(f'[{_format_optional(current_text)} | type none to clear]')}[/dim]",
        default=current_text,
        show_default=False,
    ).strip()
    if value.lower() == "none":
        return None
    return value or None


def _prompt_edit_date(label: str, current: str, *, allow_infinite: bool) -> str:
    """Prompt for an editable required date value."""
    guidance = "YYYY-MM-DD or infinite" if allow_infinite else "YYYY-MM-DD"
    while True:
        value = _prompt_required_with_default(f"{label} | [dim]{guidance}[/dim]", current)
        normalized = value.strip().lower()
        if allow_infinite and normalized == "infinite":
            return "infinite"

        try:
            date.fromisoformat(normalized)
        except ValueError:
            console.print(f"[red]Use {guidance}.[/red]")
            continue

        return normalized


def _prompt_edit_optional_date(label: str, current: Any) -> Optional[str]:
    """Prompt for an editable optional date value."""
    while True:
        value = _prompt_edit_optional(f"{label} | [dim]YYYY-MM-DD[/dim]", current)
        if value is None:
            return None

        try:
            date.fromisoformat(value)
        except ValueError:
            console.print("[red]Use YYYY-MM-DD or none.[/red]")
            continue

        return value


def _prompt_edit_nonnegative_quantity(label: str, current: float) -> float:
    """Prompt for an editable non-negative quantity."""
    return _prompt_nonnegative_quantity(label, current)


def _prompt_edit_positive_quantity(label: str, current: float) -> float:
    """Prompt for an editable positive quantity."""
    while True:
        quantity = _prompt_nonnegative_quantity(label, current)
        if quantity > 0:
            return quantity
        console.print("[red]Quantity value must be greater than 0.[/red]")


def _prompt_choice_with_default(label: str, current: str, allowed_values: set[str]) -> str:
    """Prompt for a value that must be one of a fixed set."""
    allowed_text = " / ".join(sorted(allowed_values))
    while True:
        value = _prompt_required_with_default(f"{label} | [dim]{allowed_text}[/dim]", current)
        normalized = value.strip().lower()
        if normalized in allowed_values:
            return normalized
        console.print(f"[red]Use one of: {allowed_text}.[/red]")


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


def _format_notes_marker(value: Any) -> str:
    """Format whether a row has notes without showing note contents."""
    return "Yes" if value not in (None, "") else "-"


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
    table.add_column("Notes", overflow="fold")

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
            _format_notes_marker(row["notes"]),
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
            _format_notes_marker(row["notes"]),
        )

    console.print(table)


def _show_stock_detail(row: Any) -> None:
    """Render one stock item with full detail fields."""
    lines = [
        f"ID: {row['id']}",
        f"Name: {escape(row['name'])}",
        f"Category: {escape(row['category'])}",
        f"Owner: {escape(row['owner'])}",
        f"Purchase date: {row['purchase_date']}",
        f"Quantity: {_format_quantity(row['quantity_value'], row['quantity_unit'])}",
        f"Location: {escape(row['location'])}",
        f"Unopened expiration date: {row['unopened_expiration_date']}",
        f"Opened expiration date: {_format_optional(row['opened_expiration_date'])}",
        f"Opened date: {_format_optional(row['opened_date'])}",
        f"Current expiration date: {row['current_expiration_date']}",
        f"Status: {_format_status(row['status'])}",
        f"Notes: {escape(_format_optional(row['notes']))}",
    ]
    if "created_at" in row.keys():
        lines.append(f"Created: {row['created_at']}")
    if "updated_at" in row.keys():
        lines.append(f"Updated: {row['updated_at']}")

    console.print(Panel("\n".join(lines), title=f"Stock Item #{row['id']}", border_style=PURPLE))


def _show_restock_detail(row: Any) -> None:
    """Render one restock item with full detail fields."""
    quantity = "-"
    if row["quantity_value"] is not None and row["quantity_unit"]:
        quantity = _format_quantity(row["quantity_value"], row["quantity_unit"])

    lines = [
        f"ID: {row['id']}",
        f"Name: {escape(row['name'])}",
        f"Category: {escape(_format_optional(row['category']))}",
        f"Quantity: {quantity}",
        f"Source item ID: {_format_optional(row['source_item_id'])}",
        f"Status: {_format_status(row['status'])}",
        f"Notes: {escape(_format_optional(row['notes']))}",
        f"Created: {row['created_at']}",
        f"Done: {_format_optional(row['done_at'])}",
    ]
    console.print(Panel("\n".join(lines), title=f"Restock Item #{row['id']}", border_style=PURPLE))


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


def _parse_stock_ids(value: str, valid_ids: set[int], missing_message: str) -> list[int] | None:
    """Parse a comma-separated stock id selection."""
    selected_ids: list[int] = []
    for raw_id in value.split(","):
        raw_id = raw_id.strip()
        if not raw_id:
            continue

        try:
            item_id = int(raw_id)
        except ValueError:
            console.print(f"[red]Invalid stock item id:[/red] {raw_id}")
            return None

        if item_id not in valid_ids:
            console.print(f"[red]{missing_message.format(item_id=item_id)}[/red]")
            return None

        if item_id not in selected_ids:
            selected_ids.append(item_id)

    if not selected_ids:
        console.print("[red]Select at least one stock item id.[/red]")
        return None

    return selected_ids


def _parse_field_numbers(value: str, valid_fields: dict[int, str]) -> list[int] | None:
    """Parse a comma-separated editable field selection."""
    selected_fields: list[int] = []
    for raw_number in value.split(","):
        raw_number = raw_number.strip()
        if not raw_number:
            continue

        try:
            field_number = int(raw_number)
        except ValueError:
            console.print(f"[red]Invalid field number:[/red] {raw_number}")
            return None

        if field_number not in valid_fields:
            console.print(f"[red]Field #{field_number} does not exist.[/red]")
            return None

        if field_number not in selected_fields:
            selected_fields.append(field_number)

    if not selected_fields:
        console.print("[red]Select at least one field.[/red]")
        return None

    return selected_fields


def _prompt_field_numbers(fields: dict[int, str]) -> list[int]:
    """Prompt for one or more editable fields."""
    console.print("[bold]Editable fields[/bold]")
    for field_number, field_name in fields.items():
        console.print(f"{field_number}. {field_name}")

    while True:
        selected = Prompt.ask(
            f"[bold red][Required][/bold red] [bold {PURPLE}]Fields to edit[/bold {PURPLE}] "
            "[dim]comma-separated[/dim]"
        )
        selected_fields = _parse_field_numbers(selected, fields)
        if selected_fields is not None:
            return selected_fields


def _calculate_current_expiration_date(
    unopened_expiration_date: str,
    opened_expiration_date: Optional[str],
    opened_date: Optional[str],
) -> str:
    """Return the expiration date currently used by status and reminders."""
    if opened_date is not None and opened_expiration_date is not None:
        return opened_expiration_date
    return unopened_expiration_date


def _maybe_show_stock_details(rows: list[Any], database: Path) -> None:
    """Optionally show full stock item details after a list view."""
    try:
        show_details = Confirm.ask("View item details?", default=False)
    except (EOFError, KeyboardInterrupt):
        return
    if not show_details:
        return

    rows_by_id = {int(row["id"]): row for row in rows}
    while True:
        selected = Prompt.ask(
            f"[bold red][Required][/bold red] [bold {PURPLE}]Stock item IDs[/bold {PURPLE}] "
            "[dim]comma-separated[/dim]"
        )
        selected_ids = _parse_stock_ids(
            selected,
            set(rows_by_id),
            "Stock item #{item_id} does not exist.",
        )
        if selected_ids is not None:
            break

    for item_id in selected_ids:
        row = get_item(item_id, database)
        if row is not None:
            _show_stock_detail(row)


def _maybe_show_restock_details(rows: list[Any], database: Path) -> None:
    """Optionally show full restock item details after a list view."""
    try:
        show_details = Confirm.ask("View restock item details?", default=False)
    except (EOFError, KeyboardInterrupt):
        return
    if not show_details:
        return

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

    for item_id in selected_ids:
        row = get_restock_item(item_id, database)
        if row is not None:
            _show_restock_detail(row)


def _add_stock_item_to_restock(
    row: Any,
    default_quantity: float,
    database: Path,
    *,
    include_source: bool = True,
) -> None:
    """Prompt for restock details and create a restock item from a stock item."""
    if default_quantity <= 0:
        default_quantity = 1

    if not Confirm.ask(f"Add {row['name']} to restock list?", default=True):
        return

    restock_quantity = _prompt_nonnegative_quantity(
        f"Restock quantity for {row['name']} [{_format_quantity(default_quantity, row['quantity_unit'])}]",
        default_quantity,
    )
    if restock_quantity <= 0:
        console.print("[yellow]Restock item was not added because quantity is 0.[/yellow]")
        return

    name = row["name"]
    category = row["category"]
    quantity_unit = row["quantity_unit"]
    notes = row["notes"]

    if Confirm.ask("Edit restock details?", default=False):
        name = _prompt_required_with_default("Name", name)
        category = _prompt_required_with_default("Category", category)
        quantity_unit = _prompt_required_with_default("Quantity unit", quantity_unit)
        notes = _prompt_optional_with_default("Notes", notes)

    restock_id = add_restock_item(
        {
            "name": name,
            "category": category,
            "quantity_value": restock_quantity,
            "quantity_unit": quantity_unit,
            "source_item_id": int(row["id"]) if include_source else None,
            "status": "pending",
            "notes": notes,
        },
        database,
    )
    console.print(f"[green]Added restock item #{restock_id}:[/green] {name}")


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
    _maybe_show_stock_details(rows, Path(database))


@app.command()
def edit(
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Interactively edit one stock item."""
    rows = fetch_items(database_path=Path(database))

    if not rows:
        console.print("[yellow]No stock items found.[/yellow]")
        return

    _show_items_table(rows, "Stock Items")
    rows_by_id = {int(row["id"]): row for row in rows}

    while True:
        selected = Prompt.ask(
            f"[bold red][Required][/bold red] [bold {PURPLE}]Stock item ID[/bold {PURPLE}]"
        )
        selected_ids = _parse_stock_ids(
            selected,
            set(rows_by_id),
            "Stock item #{item_id} does not exist.",
        )
        if selected_ids is None:
            continue
        if len(selected_ids) > 1:
            console.print("[red]Select exactly one stock item id.[/red]")
            continue
        break

    item_id = selected_ids[0]
    row = get_item(item_id, Path(database))
    if row is None:
        console.print(f"[red]Stock item #{item_id} does not exist.[/red]")
        return

    console.print(Panel.fit(f"[bold]Edit stock item #{item_id}[/bold]", border_style=PURPLE))
    _show_stock_detail(row)

    stock_fields = {
        1: "name",
        2: "category",
        3: "owner",
        4: "purchase date",
        5: "quantity",
        6: "location",
        7: "expiration",
        8: "notes",
    }
    selected_fields = _prompt_field_numbers(stock_fields)

    name = row["name"]
    category = row["category"]
    owner = row["owner"]
    purchase_date = row["purchase_date"]
    quantity_value = float(row["quantity_value"])
    quantity_unit = row["quantity_unit"]
    location = row["location"]
    unopened_expiration_date = row["unopened_expiration_date"]
    opened_expiration_date = row["opened_expiration_date"]
    opened_date = row["opened_date"]
    current_expiration_date = row["current_expiration_date"]
    notes = row["notes"]

    for field_number in selected_fields:
        if field_number == 1:
            name = _prompt_edit_required("Name", name)
        elif field_number == 2:
            category = _prompt_edit_required("Category", category)
        elif field_number == 3:
            owner = _prompt_edit_required("Owner", owner)
        elif field_number == 4:
            purchase_date = _prompt_edit_date("Purchase date", purchase_date, allow_infinite=False)
        elif field_number == 5:
            quantity_value = _prompt_edit_nonnegative_quantity("Quantity value", quantity_value)
            quantity_unit = _prompt_edit_required("Quantity unit", quantity_unit)
        elif field_number == 6:
            location = _prompt_edit_required("Location", location)
        elif field_number == 7:
            unopened_expiration_date = _prompt_edit_date(
                "Unopened expiration date",
                unopened_expiration_date,
                allow_infinite=True,
            )
            opened_expiration_date = _prompt_edit_optional_date(
                "Opened expiration date",
                opened_expiration_date,
            )
            opened_date = _prompt_edit_optional_date("Opened date", opened_date)
            current_expiration_date = _calculate_current_expiration_date(
                unopened_expiration_date,
                opened_expiration_date,
                opened_date,
            )
        elif field_number == 8:
            notes = _prompt_edit_optional("Notes", notes)

    status = calculate_item_status(
        quantity_value,
        current_expiration_date,
        Path(database),
    )

    if not Confirm.ask(f"Save changes to stock item #{item_id} {name}?", default=True):
        console.print("[yellow]Edit cancelled.[/yellow]")
        return

    updated = update_item(
        item_id,
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
            "status": status,
            "notes": notes,
        },
        Path(database),
    )

    if updated:
        console.print(f"[green]Updated stock item #{item_id}:[/green] {name}")
    else:
        console.print(f"[red]Stock item #{item_id} could not be updated.[/red]")


@app.command()
def consume(
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Interactively consume stock items."""
    rows = fetch_items(database_path=Path(database))
    consumable_rows = [
        row
        for row in rows
        if row["status"] != "consumed" and float(row["quantity_value"]) > 0
    ]

    if not consumable_rows:
        console.print("[yellow]No consumable stock items found.[/yellow]")
        return

    _show_items_table(consumable_rows, "Consumable Stock Items")
    rows_by_id = {int(row["id"]): row for row in consumable_rows}

    while True:
        selected = Prompt.ask(
            f"[bold red][Required][/bold red] [bold {PURPLE}]Stock item IDs[/bold {PURPLE}] "
            "[dim]comma-separated[/dim]"
        )
        selected_ids = _parse_stock_ids(
            selected,
            set(rows_by_id),
            "Stock item #{item_id} is not consumable or does not exist.",
        )
        if selected_ids is not None:
            break

    for item_id in selected_ids:
        row = rows_by_id[item_id]
        current_quantity = float(row["quantity_value"])
        quantity_unit = row["quantity_unit"]
        consumed_quantity = _prompt_nonnegative_quantity(
            f"Consumed quantity for {row['name']} [{_format_quantity(current_quantity, quantity_unit)}]",
            current_quantity,
        )

        if consumed_quantity <= 0:
            console.print(f"[yellow]Skipped stock item #{item_id}: quantity is 0.[/yellow]")
            continue

        if consumed_quantity >= current_quantity:
            update_item_quantity(item_id, 0, Path(database))
            console.print(f"[green]Marked stock item #{item_id} as consumed:[/green] {row['name']}")
            _add_stock_item_to_restock(row, current_quantity, Path(database))
            continue

        remaining_quantity = current_quantity - consumed_quantity
        update_item_quantity(item_id, remaining_quantity, Path(database))
        console.print(
            f"[green]Updated stock item #{item_id}:[/green] "
            f"{_format_quantity(remaining_quantity, quantity_unit)} remaining"
        )


@app.command(name="delete")
def delete_stock(
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Interactively delete stock items."""
    rows = fetch_items(database_path=Path(database))

    if not rows:
        console.print("[yellow]No stock items found.[/yellow]")
        return

    _show_items_table(rows, "Stock Items")
    rows_by_id = {int(row["id"]): row for row in rows}

    while True:
        selected = Prompt.ask(
            f"[bold red][Required][/bold red] [bold {PURPLE}]Stock item IDs[/bold {PURPLE}] "
            "[dim]comma-separated[/dim]"
        )
        selected_ids = _parse_stock_ids(
            selected,
            set(rows_by_id),
            "Stock item #{item_id} does not exist.",
        )
        if selected_ids is not None:
            break

    names = ", ".join(f"#{item_id} {rows_by_id[item_id]['name']}" for item_id in selected_ids)
    if not Confirm.ask(f"Delete stock item(s): {names}?", default=False):
        console.print("[yellow]Delete cancelled.[/yellow]")
        return

    for item_id in selected_ids:
        row = rows_by_id[item_id]
        if delete_item(item_id, Path(database)):
            console.print(f"[green]Deleted stock item #{item_id}:[/green] {row['name']}")
            _add_stock_item_to_restock(
                row,
                float(row["quantity_value"]),
                Path(database),
                include_source=False,
            )
        else:
            console.print(f"[red]Stock item #{item_id} could not be deleted.[/red]")


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
    _maybe_show_restock_details(rows, Path(database))


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


@restock_app.command(name="edit")
def edit_restock(
    database: str = typer.Option(
        str(DEFAULT_DATABASE_PATH),
        "--database",
        "-d",
        help="Path to the SQLite database file.",
    ),
) -> None:
    """Interactively edit one restock list item."""
    rows = fetch_restock_items(database_path=Path(database))

    if not rows:
        console.print("[yellow]No restock items found.[/yellow]")
        return

    _show_restock_table(rows, "Restock Items")
    rows_by_id = {int(row["id"]): row for row in rows}

    while True:
        selected = Prompt.ask(
            f"[bold red][Required][/bold red] [bold {PURPLE}]Restock item ID[/bold {PURPLE}]"
        )
        selected_ids = _parse_restock_ids(
            selected,
            set(rows_by_id),
            "Restock item #{item_id} does not exist.",
        )
        if selected_ids is None:
            continue
        if len(selected_ids) > 1:
            console.print("[red]Select exactly one restock item id.[/red]")
            continue
        break

    item_id = selected_ids[0]
    row = get_restock_item(item_id, Path(database))
    if row is None:
        console.print(f"[red]Restock item #{item_id} does not exist.[/red]")
        return

    console.print(Panel.fit(f"[bold]Edit restock item #{item_id}[/bold]", border_style=PURPLE))
    _show_restock_detail(row)

    restock_fields = {
        1: "name",
        2: "category",
        3: "quantity",
        4: "notes",
    }
    selected_fields = _prompt_field_numbers(restock_fields)

    name = row["name"]
    category = row["category"] or ""
    quantity_value = float(row["quantity_value"]) if row["quantity_value"] is not None else 1
    quantity_unit = row["quantity_unit"] or ""
    status = row["status"]
    notes = row["notes"]

    for field_number in selected_fields:
        if field_number == 1:
            name = _prompt_edit_required("Name", name)
        elif field_number == 2:
            category = _prompt_edit_required("Category", category)
        elif field_number == 3:
            quantity_value = _prompt_edit_positive_quantity("Quantity value", quantity_value)
            quantity_unit = _prompt_edit_required("Quantity unit", quantity_unit)
        elif field_number == 4:
            notes = _prompt_edit_optional("Notes", notes)

    if not Confirm.ask(f"Save changes to restock item #{item_id} {name}?", default=True):
        console.print("[yellow]Edit cancelled.[/yellow]")
        return

    updated = update_restock_item(
        item_id,
        {
            "name": name,
            "category": category,
            "quantity_value": quantity_value,
            "quantity_unit": quantity_unit,
            "status": status,
            "notes": notes,
        },
        Path(database),
    )

    if updated:
        console.print(f"[green]Updated restock item #{item_id}:[/green] {name}")
    else:
        console.print(f"[red]Restock item #{item_id} could not be updated.[/red]")


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

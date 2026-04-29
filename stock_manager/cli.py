"""Command-line interface for Stock Manager."""

from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    help="Manage family stock, expiration reminders, and restocking lists.",
    invoke_without_command=True,
    no_args_is_help=True,
)
console = Console()


def _not_implemented(command_name: str) -> None:
    """Show a consistent placeholder message for planned commands."""
    console.print(f"[yellow]{command_name} is not implemented yet.[/yellow]")


@app.command()
def init() -> None:
    """Initialize the local Stock Manager database."""
    _not_implemented("stock init")


@app.command()
def add() -> None:
    """Add a new stock item."""
    _not_implemented("stock add")


@app.command(name="list")
def list_items(
    category: Optional[str] = typer.Option(None, help="Filter by category."),
    owner: Optional[str] = typer.Option(None, help="Filter by purchaser or assigned user."),
    location: Optional[str] = typer.Option(None, help="Filter by storage location."),
    status: Optional[str] = typer.Option(None, help="Filter by stock status."),
) -> None:
    """Show current stock items."""
    _not_implemented("stock list")


@app.command()
def search(
    keyword: str = typer.Argument(..., help="Keyword to search in stock items."),
    owner: Optional[str] = typer.Option(None, help="Filter by purchaser or assigned user."),
    location: Optional[str] = typer.Option(None, help="Filter by storage location."),
) -> None:
    """Search stock items by keyword."""
    _not_implemented("stock search")


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

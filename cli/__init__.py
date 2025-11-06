"""
PasarGuard CLI Package

A modern, type-safe CLI built with Typer for managing PasarGuard instances.
"""

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from app.models.admin import AdminDetails
from app.operation import OperatorType
from app.operation.admin import AdminOperation
from app.operation.system import SystemOperation

# Initialize console for rich output
console = Console()

# system admin for CLI operations
SYSTEM_ADMIN = AdminDetails(username="cli", is_sudo=True, telegram_id=None, discord_webhook=None, notification_enable=None)


def get_admin_operation() -> AdminOperation:
    """Get admin operation instance."""
    return AdminOperation(OperatorType.CLI)


def get_system_operation() -> SystemOperation:
    """Get node operation instance."""
    return SystemOperation(OperatorType.CLI)


class BaseCLI:
    """Base class for CLI operations."""

    def __init__(self):
        self.console = console

    def create_table(self, title: str, columns: list) -> Table:
        """Create a rich table with given columns."""
        table = Table(title=title)
        for column in columns:
            table.add_column(column["name"], style=column.get("style", "white"))
        return table

    def format_cli_validation_error(self, errors: ValidationError):
        for error in errors.errors():
            for err in error["msg"].split(";"):
                self.console.print(f"[red]Error: {err}[/red]")

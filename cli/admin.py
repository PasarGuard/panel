"""
Admin CLI Module

Handles admin account management through the command line interface.
"""

import typer
from pydantic import ValidationError

from app.db.base import GetDB
from app.models.admin import AdminCreate, AdminModify
from app.utils.system import readable_size
from cli import SYSTEM_ADMIN, BaseCLI, console, get_admin_operation


class AdminCLI(BaseCLI):
    """Admin CLI operations."""

    async def list_admins(self, db):
        """List all admin accounts."""
        admin_op = get_admin_operation()
        admins = await admin_op.get_admins(db)

        if not admins:
            self.console.print("[yellow]No admins found[/yellow]")
            return

        table = self.create_table(
            "Admin Accounts",
            [
                {"name": "Username", "style": "cyan"},
                {"name": "Is Sudo", "style": "green"},
                {"name": "Used Traffic", "style": "blue"},
                {"name": "Is Disabled", "style": "red"},
            ],
        )

        for admin in admins:
            table.add_row(
                admin.username,
                "✓" if admin.is_sudo else "✗",
                readable_size(admin.used_traffic),
                "✓" if admin.is_disabled else "✗",
            )

        self.console.print(table)

    async def create_admin(self, db, username: str):
        """Create a new admin account."""
        admin_op = get_admin_operation()

        # Check if admin already exists
        admins = await admin_op.get_admins(db)
        if any(admin.username == username for admin in admins):
            self.console.print(f"[red]Admin '{username}' already exists[/red]")
            return

        while True:
            # Get password
            password = typer.prompt("Password", hide_input=True)
            if not password:
                self.console.print("[red]Password is required[/red]")
                continue

            confirm_password = typer.prompt("Confirm Password", hide_input=True)
            if password != confirm_password:
                self.console.print("[red]Passwords do not match[/red]")
                continue

            try:
                # Create admin
                new_admin = AdminCreate(username=username, password=password, is_sudo=False)
                await admin_op.create_admin(db, new_admin, SYSTEM_ADMIN)
                self.console.print(f"[green]Admin '{username}' created successfully[/green]")
                break
            except ValidationError as e:
                self.format_cli_validation_error(e)
                continue
            except Exception as e:
                self.console.print(f"[red]Error creating admin: {e}[/red]")
                break

    async def delete_admin(self, db, username: str):
        """Delete an admin account."""
        admin_op = get_admin_operation()

        # Check if admin exists
        admins = await admin_op.get_admins(db)
        if not any(admin.username == username for admin in admins):
            self.console.print(f"[red]Admin '{username}' not found[/red]")
            return

        if typer.confirm(f"Are you sure you want to delete admin '{username}'?"):
            try:
                await admin_op.remove_admin(db, username, SYSTEM_ADMIN)
                self.console.print(f"[green]Admin '{username}' deleted successfully[/green]")
            except Exception as e:
                self.console.print(f"[red]Error deleting admin: {e}[/red]")

    async def modify_admin(self, db, username: str):
        """Modify an admin account."""
        admin_op = get_admin_operation()

        # Check if admin exists
        admins = await admin_op.get_admins(db)
        if not any(admin.username == username for admin in admins):
            self.console.print(f"[red]Admin '{username}' not found[/red]")
            return

        # Get the current admin details
        current_admin = next(admin for admin in admins if admin.username == username)

        self.console.print(f"[yellow]Modifying admin '{username}'[/yellow]")
        self.console.print("[cyan]Current settings:[/cyan]")
        self.console.print(f"  Username: {current_admin.username}")
        self.console.print(f"  Is Sudo: {'✓' if current_admin.is_sudo else '✗'}")

        new_password = None
        is_sudo = current_admin.is_sudo
        # Password modification
        if typer.confirm("Do you want to change the password?"):
            new_password = typer.prompt("New password", hide_input=True)
            confirm_password = typer.prompt("Confirm Password", hide_input=True)
            if new_password != confirm_password:
                self.console.print("[red]Passwords do not match[/red]")
                return

        # Sudo status modification
        if typer.confirm(f"Do you want to change sudo status? (Current: {'✓' if current_admin.is_sudo else '✗'})"):
            is_sudo = typer.confirm("Make this admin a sudo admin?")

        # Confirm changes
        self.console.print("\n[cyan]Summary of changes:[/cyan]")
        if new_password:
            self.console.print("  Password: [yellow]Will be updated[/yellow]")
        if is_sudo != current_admin.is_sudo:
            self.console.print(f"  Is Sudo: {'✓' if is_sudo else '✗'} [yellow](changed)[/yellow]")

        if typer.confirm("Do you want to apply these changes?"):
            try:
                # Interactive modification
                modified_admin = AdminModify(is_sudo=is_sudo, password=new_password)
                await admin_op.modify_admin(db, username, modified_admin, SYSTEM_ADMIN)
                self.console.print(f"[green]Admin '{username}' modified successfully[/green]")
            except Exception as e:
                self.console.print(f"[red]Error modifying admin: {e}[/red]")
        else:
            self.console.print("[yellow]Modification cancelled[/yellow]")

    async def reset_admin_usage(self, db, username: str):
        """Reset admin usage statistics."""
        admin_op = get_admin_operation()

        # Check if admin exists
        admins = await admin_op.get_admins(db)
        if not any(admin.username == username for admin in admins):
            self.console.print(f"[red]Admin '{username}' not found[/red]")
            return

        if typer.confirm(f"Are you sure you want to reset usage for admin '{username}'?"):
            try:
                await admin_op.reset_admin_usage(db, username, SYSTEM_ADMIN)
                self.console.print(f"[green]Usage reset for admin '{username}'[/green]")
            except Exception as e:
                self.console.print(f"[red]Error resetting usage: {e}[/red]")


# CLI commands
async def list_admins():
    """List all admin accounts."""
    admin_cli = AdminCLI()
    async with GetDB() as db:
        try:
            await admin_cli.list_admins(db)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def create_admin(username: str):
    """Create a new admin account."""
    admin_cli = AdminCLI()
    async with GetDB() as db:
        try:
            await admin_cli.create_admin(db, username)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def delete_admin(username: str):
    """Delete an admin account."""
    admin_cli = AdminCLI()
    async with GetDB() as db:
        try:
            await admin_cli.delete_admin(db, username)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def modify_admin(username: str):
    """Modify an admin account."""
    admin_cli = AdminCLI()
    async with GetDB() as db:
        try:
            await admin_cli.modify_admin(db, username)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def reset_admin_usage(username: str):
    """Reset admin usage statistics."""
    admin_cli = AdminCLI()
    async with GetDB() as db:
        try:
            await admin_cli.reset_admin_usage(db, username)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

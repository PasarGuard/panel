"""
Admin CLI Module

Handles admin account management through the command line interface.
"""

import typer
from pydantic import ValidationError
from typing_extensions import Annotated

from app.db.base import GetDB
from app.models.admin import AdminCreate, AdminModify
from app.models.notification_enable import UserNotificationEnable
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

    async def create_admin(self, db, username: str, is_sudo: bool):
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
                # Notification preferences setup
                self.console.print("\n[cyan]Notification Preferences:[/cyan]")
                enable_notifications = typer.confirm("Enable user notifications for this admin?", default=False)

                if enable_notifications:
                    self.console.print("[yellow]Select which notification types to enable:[/yellow]")
                    notif_create = typer.confirm("  User Create?", default=False)
                    notif_modify = typer.confirm("  User Modify?", default=False)
                    notif_delete = typer.confirm("  User Delete?", default=False)
                    notif_status_change = typer.confirm("  Status Change?", default=False)
                    notif_reset_data = typer.confirm("  Reset Data Usage?", default=False)
                    notif_data_reset_by_next = typer.confirm("  Data Reset By Next?", default=False)
                    notif_sub_revoked = typer.confirm("  Subscription Revoked?", default=False)
                else:
                    notif_create = notif_modify = notif_delete = notif_status_change = False
                    notif_reset_data = notif_data_reset_by_next = notif_sub_revoked = False

                notification_enable = UserNotificationEnable(
                    create=notif_create,
                    modify=notif_modify,
                    delete=notif_delete,
                    status_change=notif_status_change,
                    reset_data_usage=notif_reset_data,
                    data_reset_by_next=notif_data_reset_by_next,
                    subscription_revoked=notif_sub_revoked,
                )

                # Create admin
                new_admin = AdminCreate(
                    username=username, password=password, is_sudo=is_sudo, notification_enable=notification_enable
                )
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
        target_admin = next((admin for admin in admins if admin.username == username), None)
        if not target_admin:
            self.console.print(f"[red]Admin '{username}' not found[/red]")
            return

        user_count = len(target_admin.users or [])

        if typer.confirm(f"Are you sure you want to delete admin '{username}'?"):
            if user_count > 0:
                message = (
                    f"Admin '{username}' owns {user_count} users. Delete all of their users before removing the admin?"
                )
                delete_users = typer.confirm(message, default=False)
                if delete_users:
                    try:
                        await admin_op.remove_all_users(db, username, SYSTEM_ADMIN)
                        self.console.print(f"[green]Deleted {user_count} users belonging to admin '{username}'[/green]")
                    except Exception as e:
                        self.console.print(f"[red]Error deleting users: {e}[/red]")
                        return

            try:
                await admin_op.remove_admin(db, username, SYSTEM_ADMIN)
                self.console.print(f"[green]Admin '{username}' deleted successfully[/green]")
            except Exception as e:
                self.console.print(f"[red]Error deleting admin: {e}[/red]")

    async def delete_admin_users(self, db, username: str):
        """Delete all users belonging to an admin."""
        admin_op = get_admin_operation()

        admins = await admin_op.get_admins(db)
        target_admin = next((admin for admin in admins if admin.username == username), None)
        if not target_admin:
            self.console.print(f"[red]Admin '{username}' not found[/red]")
            return

        if not typer.confirm(
            f"Delete all users belonging to admin '{username}'? This action cannot be undone.", default=False
        ):
            self.console.print("[yellow]Operation cancelled[/yellow]")
            return

        try:
            deleted = await admin_op.remove_all_users(db, username, SYSTEM_ADMIN)
            if deleted == 0:
                self.console.print(f"[yellow]Admin '{username}' has no users to delete[/yellow]")
            else:
                self.console.print(f"[green]Deleted {deleted} users belonging to admin '{username}'[/green]")
        except Exception as e:
            self.console.print(f"[red]Error deleting users: {e}[/red]")

    async def modify_admin(self, db, username: str, disable: bool):
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
        self.console.print(f"  Is Disabled: {'✓' if current_admin.is_disabled else '✗'}")

        # Display current notification settings
        if current_admin.notification_enable is None:
            self.console.print("  Notifications: [yellow]Legacy (Receiving ALL)[/yellow]")
        else:
            notif = current_admin.notification_enable
            self.console.print("  Notifications:")
            self.console.print(f"    User Create: {'✓' if notif['create'] else '✗'}")
            self.console.print(f"    User Modify: {'✓' if notif['modify'] else '✗'}")
            self.console.print(f"    User Delete: {'✓' if notif['delete'] else '✗'}")
            self.console.print(f"    Status Change: {'✓' if notif['status_change'] else '✗'}")
            self.console.print(f"    Reset Data Usage: {'✓' if notif['reset_data_usage'] else '✗'}")
            self.console.print(f"    Data Reset By Next: {'✓' if notif['data_reset_by_next'] else '✗'}")
            self.console.print(f"    Subscription Revoked: {'✓' if notif['subscription_revoked'] else '✗'}")

        new_password = None
        is_sudo = current_admin.is_sudo
        is_disabled = current_admin.is_disabled
        notification_enable = current_admin.notification_enable

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

        # Disabled status modification
        if disable is not None:
            is_disabled = disable
        elif typer.confirm(
            f"Do you want to change disabled status? (Current: {'✓' if current_admin.is_disabled else '✗'})"
        ):
            is_disabled = typer.confirm("Disable this admin account?")

        # Notification preferences modification (skip for legacy admins with None)
        if current_admin.notification_enable is not None and typer.confirm(
            "Do you want to modify notification preferences?"
        ):
            self.console.print("\n[cyan]Notification Preferences:[/cyan]")
            enable_notifications = typer.confirm(
                "Enable user notifications for this admin?",
                default=any(
                    [
                        current_admin.notification_enable["create"],
                        current_admin.notification_enable["modify"],
                        current_admin.notification_enable["delete"],
                        current_admin.notification_enable["status_change"],
                        current_admin.notification_enable["reset_data_usage"],
                        current_admin.notification_enable["data_reset_by_next"],
                        current_admin.notification_enable["subscription_revoked"],
                    ]
                ),
            )

            if enable_notifications:
                self.console.print("[yellow]Select which notification types to enable:[/yellow]")
                notif_create = typer.confirm("  User Create?", default=current_admin.notification_enable["create"])
                notif_modify = typer.confirm("  User Modify?", default=current_admin.notification_enable["modify"])
                notif_delete = typer.confirm("  User Delete?", default=current_admin.notification_enable["delete"])
                notif_status_change = typer.confirm(
                    "  Status Change?", default=current_admin.notification_enable["status_change"]
                )
                notif_reset_data = typer.confirm(
                    "  Reset Data Usage?", default=current_admin.notification_enable["reset_data_usage"]
                )
                notif_data_reset_by_next = typer.confirm(
                    "  Data Reset By Next?", default=current_admin.notification_enable["data_reset_by_next"]
                )
                notif_sub_revoked = typer.confirm(
                    "  Subscription Revoked?", default=current_admin.notification_enable["subscription_revoked"]
                )
            else:
                notif_create = notif_modify = notif_delete = notif_status_change = False
                notif_reset_data = notif_data_reset_by_next = notif_sub_revoked = False

            notification_enable = UserNotificationEnable(
                create=notif_create,
                modify=notif_modify,
                delete=notif_delete,
                status_change=notif_status_change,
                reset_data_usage=notif_reset_data,
                data_reset_by_next=notif_data_reset_by_next,
                subscription_revoked=notif_sub_revoked,
            )

        # Confirm changes
        self.console.print("\n[cyan]Summary of changes:[/cyan]")
        if new_password:
            self.console.print("  Password: [yellow]Will be updated[/yellow]")
        if is_sudo != current_admin.is_sudo:
            self.console.print(f"  Is Sudo: {'✓' if is_sudo else '✗'} [yellow](changed)[/yellow]")
        if is_disabled != current_admin.is_disabled:
            self.console.print(f"  Is Disabled: {'✓' if is_disabled else '✗'} [yellow](changed)[/yellow]")
        if notification_enable != current_admin.notification_enable:
            self.console.print("  Notifications: [yellow](changed)[/yellow]")

        if typer.confirm("Do you want to apply these changes?"):
            try:
                # Interactive modification
                modified_admin = AdminModify(
                    is_sudo=is_sudo,
                    password=new_password,
                    is_disabled=is_disabled,
                    notification_enable=notification_enable,
                )
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


admin_cli = AdminCLI()


# CLI commands
async def list_admins():
    """List all admin accounts."""
    async with GetDB() as db:
        try:
            await admin_cli.list_admins(db)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def create_admin(
    username: str,
    sudo: Annotated[bool, typer.Option(False, "--sudo", "-s", help="Create a sudo admin.")] = False,
):
    """Create a new admin account."""
    async with GetDB() as db:
        try:
            if not sudo:
                sudo = typer.confirm("Make this admin a sudo admin?")
            await admin_cli.create_admin(db, username, sudo)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def delete_admin(username: str):
    """Delete an admin account."""
    async with GetDB() as db:
        try:
            await admin_cli.delete_admin(db, username)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def delete_admin_users(username: str):
    """Delete all users belonging to an admin."""
    async with GetDB() as db:
        try:
            await admin_cli.delete_admin_users(db, username)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def modify_admin(
    username: str,
    disable: Annotated[bool, typer.Option(..., "--disable", help="Disable or enable the admin account.")] = None,
):
    """Modify an admin account."""
    async with GetDB() as db:
        try:
            if disable is None:
                disable = typer.confirm("Do you want to disable this admin?")
            await admin_cli.modify_admin(db, username, disable)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def reset_admin_usage(username: str):
    """Reset admin usage statistics."""
    async with GetDB() as db:
        try:
            await admin_cli.reset_admin_usage(db, username)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

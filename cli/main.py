#!/usr/bin/env python3
"""
PasarGuard CLI - Command Line Interface for PasarGuard Management

A modern, type-safe CLI built with Typer for managing PasarGuard instances.
"""

import asyncio
from typing import Optional

import typer

from cli import console
from cli.admin import create_admin, delete_admin, list_admins, modify_admin, reset_admin_usage, disable_admin_otp
from cli.system import show_status

# Initialize Typer app
app = typer.Typer(
    name="PasarGuard",
    help="PasarGuard CLI - Command Line Interface for PasarGuard Management",
    add_completion=False,
    rich_markup_mode="rich",
)


@app.command()
def version():
    """Show PasarGuard version."""
    from app import __version__

    console.print(f"[bold blue]PasarGuard[/bold blue] version [bold green]{__version__}[/bold green]")


@app.command()
def admins(
    list: bool = typer.Option(False, "--list", "-l", help="List all admins"),
    create: Optional[str] = typer.Option(None, "--create", "-c", help="Create new admin"),
    sudo: bool = typer.Option(False, "--sudo", "-s", help="Create a sudo admin."),
    delete: Optional[str] = typer.Option(None, "--delete", "-d", help="Delete admin"),
    modify: Optional[str] = typer.Option(None, "--modify", "-m", help="Modify admin"),
    disable: Optional[bool] = typer.Option(None, "--disable", help="Disable or enable the admin account."),
    reset_usage: Optional[str] = typer.Option(None, "--reset-usage", "-r", help="Reset admin usage"),
    disable_otp: Optional[str] = typer.Option(None, "--disable-otp", help="Disable OTP (2FA) for an admin"),
):
    """List & manage admin accounts."""

    if list or not any([create, delete, modify, reset_usage]):
        asyncio.run(list_admins())
    elif create:
        asyncio.run(create_admin(create, sudo))
    elif delete:
        asyncio.run(delete_admin(delete))
    elif modify:
        asyncio.run(modify_admin(modify, disable))
    elif reset_usage:
        asyncio.run(reset_admin_usage(reset_usage))
    elif disable_otp:
        asyncio.run(disable_admin_otp(disable_otp))


@app.command()
def system():
    """Show system status."""
    asyncio.run(show_status())


if __name__ == "__main__":
    app()

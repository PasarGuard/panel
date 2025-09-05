#!/usr/bin/env python3
"""
PasarGuard CLI - Command Line Interface for PasarGuard Management

A modern, type-safe CLI built with Typer for managing PasarGuard instances.
"""

import asyncio
from typing import Optional

import typer

from cli import console
from cli.admin import create_admin, delete_admin, list_admins, modify_admin, reset_admin_usage
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
    delete: Optional[str] = typer.Option(None, "--delete", "-d", help="Delete admin"),
    modify: Optional[str] = typer.Option(None, "--modify", "-m", help="Modify admin"),
    reset_usage: Optional[str] = typer.Option(None, "--reset-usage", "-r", help="Reset admin usage"),
):
    """List & manage admin accounts."""

    if list or not any([create, delete, modify, reset_usage]):
        asyncio.run(list_admins())
    elif create:
        asyncio.run(create_admin(create))
    elif delete:
        asyncio.run(delete_admin(delete))
    elif modify:
        asyncio.run(modify_admin(modify))
    elif reset_usage:
        asyncio.run(reset_admin_usage(reset_usage))


@app.command()
def system():
    """Show system status."""
    asyncio.run(show_status())


if __name__ == "__main__":
    app()

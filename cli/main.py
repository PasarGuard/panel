#!/usr/bin/env python3
"""PasarGuard CLI"""

from typing import Annotated

import typer

from cli import console
from cli.admin import TempKeyAction, generate_temp_key

app = typer.Typer(
    name="PasarGuard",
    help="PasarGuard CLI",
    add_completion=False,
    rich_markup_mode="rich",
)


@app.command("generate-temp-key")
def cmd_generate_temp_key(
    action: Annotated[
        TempKeyAction | None,
        typer.Option(
            "--action",
            "-a",
            help="Bind the key to one owner setup action; omit it for a key usable for any action.",
        ),
    ] = None,
):
    """Generate a one-time temp key for owner setup (create/reset/delete/upgrade)."""
    generate_temp_key(action)


@app.command()
def version():
    """Show PasarGuard version."""
    from app import __version__

    console.print(f"[bold blue]PasarGuard[/bold blue] version [bold green]{__version__}[/bold green]")


if __name__ == "__main__":
    app()

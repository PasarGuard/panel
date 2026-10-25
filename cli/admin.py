"""
Admin CLI Module — generate-temp-key only
"""

import asyncio
from enum import Enum

from app.db.base import GetDB
from app.db.crud.temp_key import create_temp_key
from cli import console


class TempKeyAction(str, Enum):
    """Owner setup actions a temp key can be bound to."""

    create_owner = "create_owner"
    reset_owner = "reset_owner"
    delete_owner = "delete_owner"
    upgrade_owner = "upgrade_owner"


async def _generate_temp_key(action: TempKeyAction | None = None):
    async with GetDB() as db:
        key = await create_temp_key(db, action=action.value if action is not None else None)
        console.print(f"[bold green]Temp key:[/bold green] {key.key}")
        console.print(f"[yellow]Expires at:[/yellow] {key.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if action is not None:
            console.print(f"[cyan]Bound action:[/cyan] {action.value}")
        console.print("[dim]This key is valid for 5 minutes and can only be used once.[/dim]")


def generate_temp_key(action: TempKeyAction | None = None):
    """Generate a one-time temp key for owner setup operations."""
    asyncio.run(_generate_temp_key(action))

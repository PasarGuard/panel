"""
Admin CLI Module — generate-temp-key only
"""

import asyncio

from app.db.base import GetDB
from app.db.crud.temp_key import create_temp_key
from cli import console


async def _generate_temp_key():
    async with GetDB() as db:
        key = await create_temp_key(db)
        console.print(f"[bold green]Temp key:[/bold green] {key.key}")
        console.print(f"[yellow]Expires at:[/yellow] {key.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        console.print("[dim]This key is valid for 5 minutes and can only be used once.[/dim]")


def generate_temp_key():
    """Generate a one-time temp key for owner setup operations."""
    asyncio.run(_generate_temp_key())

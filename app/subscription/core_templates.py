from aiocache import cached

from app.db import GetDB
from app.db.crud.core_template import get_core_template_values


@cached()
async def subscription_core_templates() -> dict[str, str]:
    async with GetDB() as db:
        return await get_core_template_values(db)


async def refresh_core_templates_cache() -> None:
    await subscription_core_templates.cache.clear()


async def handle_core_template_message(_: dict) -> None:
    """Handle core template update messages from NATS router."""
    await refresh_core_templates_cache()

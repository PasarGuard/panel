from aiocache import cached

from app.db import GetDB
from app.db.crud.client_template import get_client_template_values


@cached()
async def subscription_client_templates() -> dict[str, str]:
    async with GetDB() as db:
        return await get_client_template_values(db)


async def refresh_client_templates_cache() -> None:
    await subscription_client_templates.cache.clear()


async def handle_client_template_message(_: dict) -> None:
    """Handle client template update messages from NATS router."""
    await refresh_client_templates_cache()

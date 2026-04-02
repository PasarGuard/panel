from aiocache import cached

from app.db import GetDB
from app.db.crud.client_template import get_client_template_catalog


@cached()
async def subscription_client_templates() -> dict[str, dict]:
    async with GetDB() as db:
        return await get_client_template_catalog(db)


async def refresh_client_templates_cache() -> None:
    await subscription_client_templates.cache.clear()


async def handle_client_template_message(_: dict) -> None:
    """Handle client template update messages from NATS router."""
    await refresh_client_templates_cache()

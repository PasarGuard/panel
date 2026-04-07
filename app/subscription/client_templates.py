from aiocache import cached

from app.db import GetDB
from app.db.crud.client_template import get_client_template_contents_by_type, get_client_template_values
from app.models.client_template import ClientTemplateType


@cached()
async def subscription_client_templates() -> dict[str, str]:
    async with GetDB() as db:
        return await get_client_template_values(db)


@cached()
async def subscription_xray_templates() -> dict[int, str]:
    async with GetDB() as db:
        return await get_client_template_contents_by_type(db, ClientTemplateType.xray_subscription)


async def refresh_client_templates_cache() -> None:
    await subscription_client_templates.cache.clear()
    await subscription_xray_templates.cache.clear()


async def handle_client_template_message(_: dict) -> None:
    """Handle client template update messages from NATS router."""
    await refresh_client_templates_cache()

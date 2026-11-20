from app.db import GetDB
from app.db.crud.client_template import get_client_template_contents_by_type, get_client_template_values
from app.models.client_template import ClientTemplateType
from app.subscription.config_cache import clear_sub_config_cache
from app.utils.single_flight_cache import single_flight_cached


@single_flight_cached
async def subscription_client_templates() -> dict[str, str]:
    async with GetDB() as db:
        return await get_client_template_values(db)


@single_flight_cached
async def subscription_xray_templates() -> dict[int, str]:
    async with GetDB() as db:
        return await get_client_template_contents_by_type(db, ClientTemplateType.xray_subscription)


@single_flight_cached
async def subscription_happ_routing_templates() -> dict[int, str]:
    async with GetDB() as db:
        return await get_client_template_contents_by_type(db, ClientTemplateType.happ_routing)


async def refresh_client_templates_cache() -> None:
    await subscription_client_templates.refresh()
    await subscription_xray_templates.refresh()
    await subscription_happ_routing_templates.refresh()
    clear_sub_config_cache()


async def handle_client_template_message(_: dict) -> None:
    """Handle client template update messages from NATS router."""
    await refresh_client_templates_cache()

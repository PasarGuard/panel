from aiocache import cached

from app.db import GetDB
from app.db.crud.settings import get_settings
from app.models import settings
from config import TESTING


@cached()
async def telegram_settings() -> settings.Telegram:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.Telegram.model_validate(db_settings.telegram)
    return validated_settings


@cached()
async def discord_settings() -> settings.Discord:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.Discord.model_validate(db_settings.discord)
    return validated_settings


@cached()
async def webhook_settings() -> settings.Webhook:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.Webhook.model_validate(db_settings.webhook)
    return validated_settings


@cached()
async def notification_settings() -> settings.NotificationSettings:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.NotificationSettings.model_validate(db_settings.notification_settings)
    return validated_settings


@cached()
async def notification_enable() -> settings.NotificationEnable:
    if TESTING:
        return settings.NotificationEnable(
            admin={"create": False, "modify": False, "delete": False, "reset_usage": False, "login": False},
            core={"create": False, "modify": False, "delete": False},
            group={"create": False, "modify": False, "delete": False},
            host={"create": False, "modify": False, "delete": False, "modify_hosts": False},
            node={"create": False, "modify": False, "delete": False, "connect": False, "error": False, "limited": False, "reset_usage": False},
            user={"create": False, "modify": False, "delete": False, "status_change": False, "reset_data_usage": False, "data_reset_by_next": False, "subscription_revoked": False},
            user_template={"create": False, "modify": False, "delete": False},
            days_left=False,
            percentage_reached=False,
        )

    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.NotificationEnable.model_validate(db_settings.notification_enable)
    return validated_settings


@cached()
async def subscription_settings() -> settings.Subscription:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.Subscription.model_validate(db_settings.subscription)
    return validated_settings


async def refresh_caches() -> None:
    await telegram_settings.cache.clear()
    await discord_settings.cache.clear()
    await webhook_settings.cache.clear()
    await notification_settings.cache.clear()
    await notification_enable.cache.clear()
    await subscription_settings.cache.clear()


async def handle_settings_message(_: dict):
    """Handle settings update message from NATS router."""
    await refresh_caches()
    try:
        from app.telegram import telegram_bot_manager
    except Exception:
        return
    await telegram_bot_manager.sync_from_settings()

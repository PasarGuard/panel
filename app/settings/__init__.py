from aiocache import cached

from app.db import GetDB
from app.db.crud.settings import get_settings
from app.models import settings
from app.subscription.config_cache import clear_sub_config_cache
from app.utils.logger import get_logger

logger = get_logger("settings")

# Read by the sync uvicorn access log filter, so it is kept outside the async cache.
_do_not_log_telegram_bot: bool = settings.Telegram.model_fields["do_not_log_bot"].default


def do_not_log_telegram_bot() -> bool:
    return _do_not_log_telegram_bot


@cached()
async def telegram_settings() -> settings.Telegram:
    global _do_not_log_telegram_bot
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.Telegram.model_validate(db_settings.telegram)
    _do_not_log_telegram_bot = validated_settings.do_not_log_bot
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


@cached()
async def hwid_settings() -> settings.HWIDSettings:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.HWIDSettings.model_validate(db_settings.hwid)
    return validated_settings


@cached()
async def general_settings() -> settings.General:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.General.model_validate(db_settings.general)
    return validated_settings


async def refresh_caches() -> None:
    await telegram_settings.cache.clear()
    await webhook_settings.cache.clear()
    await notification_settings.cache.clear()
    await notification_enable.cache.clear()
    await subscription_settings.cache.clear()
    await hwid_settings.cache.clear()
    await general_settings.cache.clear()
    clear_sub_config_cache()
    try:
        # Reload at once: the access log filter only sees the last loaded value.
        await telegram_settings()
    except Exception as exc:
        logger.warning(f"Failed to reload telegram settings: {exc}")


async def handle_settings_message(_: dict):
    """Handle settings update message from NATS router."""
    await refresh_caches()
    try:
        from app.telegram import telegram_bot_manager
    except Exception:
        return
    await telegram_bot_manager.sync_from_settings()

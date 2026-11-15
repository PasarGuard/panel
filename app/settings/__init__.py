from app.db import GetDB
from app.db.crud.settings import get_settings
from app.models import settings
from app.subscription.config_cache import clear_sub_config_cache
from app.utils.single_flight_cache import run_shielded, single_flight_cached


@single_flight_cached
async def telegram_settings() -> settings.Telegram:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.Telegram.model_validate(db_settings.telegram)
    return validated_settings


@single_flight_cached
async def webhook_settings() -> settings.Webhook:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.Webhook.model_validate(db_settings.webhook)
    return validated_settings


@single_flight_cached
async def notification_settings() -> settings.NotificationSettings:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.NotificationSettings.model_validate(db_settings.notification_settings)
    return validated_settings


@single_flight_cached
async def notification_enable() -> settings.NotificationEnable:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.NotificationEnable.model_validate(db_settings.notification_enable)
    return validated_settings


@single_flight_cached
async def subscription_settings() -> settings.Subscription:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.Subscription.model_validate(db_settings.subscription)
    return validated_settings


@single_flight_cached
async def hwid_settings() -> settings.HWIDSettings:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.HWIDSettings.model_validate(db_settings.hwid)
    return validated_settings


@single_flight_cached
async def general_settings() -> settings.General:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.General.model_validate(db_settings.general)
    return validated_settings


@single_flight_cached
async def cleanup_settings() -> settings.CleanupSettings:
    """Return the validated cleanup settings from persistent storage."""
    async with GetDB() as db:
        db_settings = await get_settings(db)

    validated_settings = settings.CleanupSettings.model_validate(db_settings.cleanup or {})
    return validated_settings


async def refresh_caches() -> None:
    # Shielded: a caller cancelled half-way must not leave some settings reloaded and others stale.
    await run_shielded(_refresh_caches())


async def _refresh_caches() -> None:
    # Reload in place instead of clearing: requests already holding a pooled
    # connection keep reading the previous value for the few ms of the reload,
    # rather than all missing at once and each asking the pool for another one.
    await telegram_settings.refresh()
    await webhook_settings.refresh()
    await notification_settings.refresh()
    await notification_enable.refresh()
    await subscription_settings.refresh()
    await hwid_settings.refresh()
    await general_settings.refresh()
    await cleanup_settings.refresh()
    clear_sub_config_cache()


async def handle_settings_message(_: dict):
    """Handle settings update message from NATS router."""
    await refresh_caches()
    try:
        from app.telegram import telegram_bot_manager
    except Exception:
        return
    await telegram_bot_manager.sync_from_settings()

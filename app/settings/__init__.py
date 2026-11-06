from aiocache import cached

from app.db import GetDB
from app.db.crud.settings import get_settings
from app.db.models import Settings
from app.models import settings
from app.subscription.config_cache import clear_sub_config_cache


class SettingsRowMissing(RuntimeError):
    pass


async def stored_settings() -> Settings:
    async with GetDB() as db:
        db_settings = await get_settings(db)

    if db_settings is None:
        raise SettingsRowMissing(
            "The settings row is missing from this database. It is created by migration 9af04c077ede, "
            "so a database whose schema was created without running the migrations does not have it. "
            "Run `alembic upgrade head` against this database, then start the panel again."
        )

    return db_settings


@cached()
async def telegram_settings() -> settings.Telegram:
    db_settings = await stored_settings()
    validated_settings = settings.Telegram.model_validate(db_settings.telegram)
    return validated_settings


@cached()
async def webhook_settings() -> settings.Webhook:
    db_settings = await stored_settings()
    validated_settings = settings.Webhook.model_validate(db_settings.webhook)
    return validated_settings


@cached()
async def notification_settings() -> settings.NotificationSettings:
    db_settings = await stored_settings()
    validated_settings = settings.NotificationSettings.model_validate(db_settings.notification_settings)
    return validated_settings


@cached()
async def notification_enable() -> settings.NotificationEnable:
    db_settings = await stored_settings()
    validated_settings = settings.NotificationEnable.model_validate(db_settings.notification_enable)
    return validated_settings


@cached()
async def subscription_settings() -> settings.Subscription:
    db_settings = await stored_settings()
    validated_settings = settings.Subscription.model_validate(db_settings.subscription)
    return validated_settings


@cached()
async def hwid_settings() -> settings.HWIDSettings:
    db_settings = await stored_settings()
    validated_settings = settings.HWIDSettings.model_validate(db_settings.hwid)
    return validated_settings


@cached()
async def general_settings() -> settings.General:
    db_settings = await stored_settings()
    validated_settings = settings.General.model_validate(db_settings.general)
    return validated_settings


@cached()
async def cleanup_settings() -> settings.CleanupSettings:
    """Return the validated cleanup settings from persistent storage."""
    db_settings = await stored_settings()
    validated_settings = settings.CleanupSettings.model_validate(db_settings.cleanup or {})
    return validated_settings


async def refresh_caches() -> None:
    await telegram_settings.cache.clear()
    await webhook_settings.cache.clear()
    await notification_settings.cache.clear()
    await notification_enable.cache.clear()
    await subscription_settings.cache.clear()
    await hwid_settings.cache.clear()
    await general_settings.cache.clear()
    await cleanup_settings.cache.clear()
    clear_sub_config_cache()


async def handle_settings_message(_: dict):
    """Handle settings update message from NATS router."""
    await refresh_caches()
    try:
        from app.telegram import telegram_bot_manager
    except Exception:
        return
    await telegram_bot_manager.sync_from_settings()

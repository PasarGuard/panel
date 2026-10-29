import asyncio

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.settings import get_settings, modify_settings
from app.db.models import Settings
from app.models.settings import General, SettingsSchema, Subscription
from app.nats.message import MessageTopic
from app.nats.router import router
from app.notification.client import define_client
from app.settings import refresh_caches
from app.telegram import startup_telegram_bot

from . import BaseOperation


def _bot_settings(settings: SettingsSchema) -> dict | None:
    if settings.telegram is None:
        return None
    return settings.telegram.model_dump(exclude={"do_not_log_bot"})


class SettingsOperation(BaseOperation):
    @staticmethod
    async def reset_services(old_settings: SettingsSchema, new_settings: SettingsSchema):
        # do_not_log_bot only changes the access log filter, the bot keeps running
        if _bot_settings(new_settings) != _bot_settings(old_settings):
            await startup_telegram_bot()
        # When webhooks are disabled, send_notifications() already returns early
        # Pending webhook notifications will be processed when webhooks are re-enabled
        if old_settings.notification_settings.proxy_url != new_settings.notification_settings.proxy_url:
            await define_client()

    async def get_settings(self, db: AsyncSession) -> Settings:
        return await get_settings(db)

    async def modify_settings(self, db: AsyncSession, modify: SettingsSchema) -> SettingsSchema:
        db_settings = await get_settings(db)
        old_settings = SettingsSchema.model_validate(db_settings)

        if modify.general and modify.general.custom_variables is not None:
            subscription = modify.subscription or Subscription.model_validate(db_settings.subscription)
            modify.subscription = subscription.model_copy(update={"custom_variables": modify.general.custom_variables})
            # Rebuilt from the sent fields only, so the stored general section keeps the rest
            modify.general = General.model_validate(
                modify.general.model_dump(exclude_unset=True, exclude={"custom_variables"})
            )

        try:
            db_settings = await modify_settings(db, db_settings, modify)
        except ValidationError as exc:
            await self.raise_error(message=str(exc), code=400, db=db)
        new_settings = SettingsSchema.model_validate(db_settings)
        if new_settings.general and new_settings.subscription:
            new_settings.general.custom_variables = new_settings.subscription.custom_variables

        await refresh_caches()
        # Publish settings update via NATS (all workers will refresh their caches)
        await router.publish(MessageTopic.SETTING, {"action": "refresh"})
        asyncio.create_task(self.reset_services(old_settings, new_settings))

        return new_settings

    async def get_general_settings(self, db: AsyncSession):
        settings = await self.get_settings(db)
        general = General.model_validate(settings.general)
        subscription = Subscription.model_validate(settings.subscription)
        return general.model_copy(update={"custom_variables": subscription.custom_variables})

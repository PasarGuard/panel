import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.client_template import get_client_template_by_id
from app.db.models import Settings
from app.db.crud.settings import get_settings, modify_settings
from app.models.settings import SettingsSchema, client_template_type_for_sub_rule_target
from app.nats.message import MessageTopic
from app.nats.router import router
from app.settings import refresh_caches
from app.notification.client import define_client
from app.telegram import startup_telegram_bot
from . import BaseOperation


class SettingsOperation(BaseOperation):
    @staticmethod
    async def reset_services(old_settings: SettingsSchema, new_settings: SettingsSchema):
        if new_settings.telegram != old_settings.telegram:
            await startup_telegram_bot()
        if new_settings.discord != old_settings.discord:
            pass
        # When webhooks are disabled, send_notifications() already returns early
        # Pending webhook notifications will be processed when webhooks are re-enabled
        if old_settings.notification_settings.proxy_url != new_settings.notification_settings.proxy_url:
            await define_client()

    async def get_settings(self, db: AsyncSession) -> Settings:
        return await get_settings(db)

    async def modify_settings(self, db: AsyncSession, modify: SettingsSchema) -> SettingsSchema:
        db_settings = await get_settings(db)
        old_settings = SettingsSchema.model_validate(db_settings)

        if modify.subscription is not None:
            for rule in modify.subscription.rules:
                if rule.client_template_id is None:
                    continue
                expected = client_template_type_for_sub_rule_target(rule.target)
                if expected is None:
                    await self.raise_error(
                        message=f'Subscription rule target "{rule.target.value}" does not support client_template_id',
                        code=400,
                        db=db,
                    )
                tpl = await get_client_template_by_id(db, rule.client_template_id)
                if tpl is None:
                    await self.raise_error(message="Client template not found", code=404, db=db)
                if tpl.template_type != expected.value:
                    await self.raise_error(
                        message=(
                            f'Client template must be of type "{expected.value}" '
                            f'for rule target "{rule.target.value}"'
                        ),
                        code=400,
                        db=db,
                    )

        db_settings = await modify_settings(db, db_settings, modify)
        new_settings = SettingsSchema.model_validate(db_settings)

        await refresh_caches()
        # Publish settings update via NATS (all workers will refresh their caches)
        await router.publish(MessageTopic.SETTING, {"action": "refresh"})
        asyncio.create_task(self.reset_services(old_settings, new_settings))

        return new_settings

    async def get_general_settings(self, db: AsyncSession):
        settings = await self.get_settings(db)
        return settings.general

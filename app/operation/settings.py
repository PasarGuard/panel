import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.client_template import get_client_template_by_id
from app.db.crud.settings import get_settings, modify_settings
from app.db.models import Settings
from app.models.settings import RULE_TEMPLATE_TYPES, General, SettingsSchema, Subscription
from app.nats.message import MessageTopic
from app.nats.router import router
from app.notification.client import define_client
from app.settings import refresh_caches
from app.telegram import startup_telegram_bot

from . import BaseOperation


class SettingsOperation(BaseOperation):
    @staticmethod
    async def reset_services(old_settings: SettingsSchema, new_settings: SettingsSchema):
        if new_settings.telegram != old_settings.telegram:
            await startup_telegram_bot()
        # When webhooks are disabled, send_notifications() already returns early
        # Pending webhook notifications will be processed when webhooks are re-enabled
        if old_settings.notification_settings.proxy_url != new_settings.notification_settings.proxy_url:
            await define_client()

    async def get_settings(self, db: AsyncSession) -> Settings:
        return await get_settings(db)

    async def validate_rule_templates(self, db: AsyncSession, subscription: Subscription) -> None:
        """Each rule template must exist and be of the type its target format uses."""
        for index, rule in enumerate(subscription.rules, start=1):
            if rule.template_id is None:
                continue
            db_template = await get_client_template_by_id(db, rule.template_id)
            if db_template is None:
                await self.raise_error(
                    message=f"Subscription rule {index} uses client template {rule.template_id}, which does not exist",
                    code=400,
                )
            expected_type = RULE_TEMPLATE_TYPES[rule.target]
            if db_template.template_type != expected_type.value:
                await self.raise_error(
                    message=(
                        f"Subscription rule {index} targets {rule.target.value} and needs a {expected_type.value}"
                        f' template, but "{db_template.name}" is {db_template.template_type}'
                    ),
                    code=400,
                )

    async def modify_settings(self, db: AsyncSession, modify: SettingsSchema) -> SettingsSchema:
        db_settings = await get_settings(db)
        old_settings = SettingsSchema.model_validate(db_settings)
        if modify.subscription is not None:
            await self.validate_rule_templates(db, modify.subscription)

        if modify.general and modify.general.custom_variables is not None:
            subscription = modify.subscription or Subscription.model_validate(db_settings.subscription)
            modify.subscription = subscription.model_copy(update={"custom_variables": modify.general.custom_variables})
            modify.general = modify.general.model_copy(update={"custom_variables": None})

        db_settings = await modify_settings(db, db_settings, modify)
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

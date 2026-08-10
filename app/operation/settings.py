import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.settings import get_settings, lock_settings_row, modify_settings
from app.db.models import ClientTemplate, Settings
from app.models.client_template import ClientTemplateType
from app.models.settings import ConfigFormat, General, SettingsSchema, Subscription
from app.nats.message import MessageTopic
from app.nats.router import router
from app.notification.client import define_client
from app.settings import refresh_caches
from app.telegram import startup_telegram_bot

from . import BaseOperation


class SettingsOperation(BaseOperation):
    async def _validate_subscription_profile_rules(self, db: AsyncSession, subscription: Subscription) -> None:
        referenced_rules = [rule for rule in subscription.rules if rule.profile_id is not None]
        if not referenced_rules:
            return

        profile_ids = {rule.profile_id for rule in referenced_rules}
        rows = (
            await db.execute(
                select(ClientTemplate.id, ClientTemplate.template_type).where(ClientTemplate.id.in_(profile_ids))
            )
        ).all()
        template_types = {row.id: row.template_type for row in rows}
        expected_types = {
            ConfigFormat.xray: ClientTemplateType.xray_profile.value,
            ConfigFormat.sing_box: ClientTemplateType.singbox_profile.value,
        }
        for rule in referenced_rules:
            template_type = template_types.get(rule.profile_id)
            if template_type is None:
                await self.raise_error(message=f"Subscription profile {rule.profile_id} not found", code=400)
            expected_type = expected_types[rule.target]
            if template_type != expected_type:
                await self.raise_error(
                    message=(
                        f"Subscription profile {rule.profile_id} must use template type {expected_type} "
                        f"for target {rule.target.value}"
                    ),
                    code=400,
                )

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

    async def modify_settings(self, db: AsyncSession, modify: SettingsSchema) -> SettingsSchema:
        modifies_profile_references = modify.subscription is not None or bool(
            modify.general and modify.general.custom_variables is not None
        )
        db_settings = await lock_settings_row(db) if modifies_profile_references else await get_settings(db)
        old_settings = SettingsSchema.model_validate(db_settings)

        if modify.general and modify.general.custom_variables is not None:
            subscription = modify.subscription or Subscription.model_validate(db_settings.subscription)
            modify.subscription = subscription.model_copy(update={"custom_variables": modify.general.custom_variables})
            modify.general = modify.general.model_copy(update={"custom_variables": None})

        if modify.subscription is not None:
            await self._validate_subscription_profile_rules(db, modify.subscription)

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

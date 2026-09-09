import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.settings import get_settings, lock_settings_row, modify_settings
from app.db.models import ClientTemplate, Settings
from app.models.client_template import ClientTemplateType
from app.models.settings import NATIVE_TEMPLATE_BY_TARGET, General, SettingsSchema, Subscription, SubscriptionModify
from app.nats.message import MessageTopic
from app.nats.router import router
from app.notification.client import define_client
from app.settings import refresh_caches
from app.subscription.happ import happ_deeplink
from app.telegram import startup_telegram_bot

from . import BaseOperation


class SettingsOperation(BaseOperation):
    async def _validate_subscription_template_rules(self, db: AsyncSession, subscription: Subscription) -> None:
        referenced = [rule for rule in subscription.rules if rule.template_id is not None or rule.happ_routing]
        ids = {
            rule.template_id if rule.template_id is not None else rule.happ_routing.template_id
            for rule in referenced
        }
        if not ids:
            return
        templates = (
            await db.execute(
                select(ClientTemplate)
                .where(ClientTemplate.id.in_(ids))
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalars().all()
        by_id = {template.id: template for template in templates}
        for rule in referenced:
            template_id = rule.template_id if rule.template_id is not None else rule.happ_routing.template_id
            template = by_id.get(template_id)
            expected = NATIVE_TEMPLATE_BY_TARGET.get(rule.target) if rule.template_id else ClientTemplateType.happ_routing
            if template is None or ClientTemplateType(template.template_type) != expected:
                await self.raise_error(
                    message=f"Client template {template_id} must exist and use type {expected.value}", code=400, db=db
                )
            if rule.happ_routing:
                try:
                    happ_deeplink(template.content, rule.happ_routing.action, rule.happ_routing.transport)
                except ValueError as exc:
                    await self.raise_error(message=str(exc), code=400, db=db)

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
        db_settings = await lock_settings_row(db)
        old_settings = SettingsSchema.model_validate(db_settings)

        if isinstance(modify.subscription, SubscriptionModify):
            changes = modify.subscription.model_dump(exclude_unset=True)
            if changes.get("rules") is None:
                changes.pop("rules", None)
            modify.subscription = Subscription.model_validate({**db_settings.subscription, **changes})

        if modify.subscription is not None:
            await self._validate_subscription_template_rules(db, modify.subscription)

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

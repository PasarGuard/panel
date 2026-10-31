import asyncio

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.client_template import get_client_templates
from app.db.crud.settings import get_settings, modify_settings
from app.db.models import Settings
from app.models.client_template import ClientTemplateListQuery, ClientTemplateType
from app.models.settings import General, SettingsSchema, Subscription
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

    async def validate_happ_routing_templates(self, db: AsyncSession, subscription: Subscription) -> None:
        rule_template_ids = [
            (rule.pattern, rule.happ_routing_template_id)
            for rule in subscription.rules
            if rule.happ_routing_template_id is not None
        ]
        if not rule_template_ids:
            return

        if any(str(name).strip().lower() == "routing" for name in subscription.response_headers):
            await self.raise_error(
                message=(
                    'Subscription response headers have a manual "routing" header, but subscription rules use '
                    "Happ routing templates. Remove one of them."
                ),
                code=400,
            )

        ids = sorted({template_id for _, template_id in rule_template_ids})
        db_templates, _ = await get_client_templates(db, ClientTemplateListQuery(ids=ids, limit=len(ids)))
        template_types = {t.id: t.template_type for t in db_templates}
        for pattern, template_id in rule_template_ids:
            if template_id not in template_types:
                await self.raise_error(
                    message=f'Subscription rule "{pattern}": Happ routing template {template_id} not found', code=400
                )
            if template_types[template_id] != ClientTemplateType.happ_routing.value:
                await self.raise_error(
                    message=f'Subscription rule "{pattern}": template {template_id} is not a Happ routing template',
                    code=400,
                )

    async def modify_settings(self, db: AsyncSession, modify: SettingsSchema) -> SettingsSchema:
        db_settings = await get_settings(db)
        old_settings = SettingsSchema.model_validate(db_settings)

        if modify.subscription:
            await self.validate_happ_routing_templates(db, modify.subscription)

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

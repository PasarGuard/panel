import json

import yaml
from sqlalchemy.exc import IntegrityError

from app.db import AsyncSession
from app.db.crud.client_template import (
    clear_host_subscription_template_overrides,
    count_client_templates_by_type,
    create_client_template,
    get_client_template_by_id,
    get_client_templates,
    get_client_templates_simple,
    get_first_template_by_type,
    modify_client_template,
    remove_client_template,
    remove_client_templates,
    set_default_template,
)
from app.db.crud.settings import get_settings, lock_settings_row
from app.models.admin import AdminDetails
from app.models.client_template import (
    BulkClientTemplateSelection,
    ClientTemplateCreate,
    ClientTemplateListQuery,
    ClientTemplateModify,
    ClientTemplateResponse,
    ClientTemplateResponseList,
    ClientTemplateSimple,
    ClientTemplateSimpleListQuery,
    ClientTemplatesSimpleResponse,
    ClientTemplateType,
    RemoveClientTemplatesResponse,
)
from app.models.settings import Subscription
from app.models.subscription_profile import SubscriptionProfile
from app.nats.message import MessageTopic
from app.nats.router import router
from app.subscription.client_templates import refresh_client_templates_cache
from app.subscription.happ import happ_deeplink, load_happ_document
from app.subscription.profiles import validate_profile_routing_rules
from app.templates import render_template_string
from app.utils.logger import get_logger

from . import BaseOperation

logger = get_logger("client-template-operation")
LEGACY_REQUIRED_TEMPLATE_TYPES = {
    ClientTemplateType.clash_subscription,
    ClientTemplateType.xray_subscription,
    ClientTemplateType.singbox_subscription,
    ClientTemplateType.user_agent,
    ClientTemplateType.grpc_user_agent,
}
EXPLICIT_PROFILE_TEMPLATE_TYPES = {
    ClientTemplateType.xray_profile,
    ClientTemplateType.singbox_profile,
}
EXPLICIT_TEMPLATE_TYPES = EXPLICIT_PROFILE_TEMPLATE_TYPES | {ClientTemplateType.happ_routing}


class ClientTemplateOperation(BaseOperation):
    async def _get_locked_client_template(self, db: AsyncSession, template_id: int):
        template = await get_client_template_by_id(db, template_id, for_update=True)
        if template is None:
            await self.raise_error(message="Client template not found", code=404, db=db)
        return template

    @staticmethod
    async def _sync_client_template_cache() -> None:
        await refresh_client_templates_cache()
        await router.publish(MessageTopic.CLIENT_TEMPLATE, {"action": "refresh"})

    async def _validate_template_content(self, template_type: ClientTemplateType, content: str) -> None:
        try:
            if template_type == ClientTemplateType.happ_routing:
                load_happ_document(content)
                return
            if template_type == ClientTemplateType.clash_subscription:
                rendered = render_template_string(
                    content,
                    {
                        "conf": {"proxies": [], "proxy-groups": [], "rules": []},
                        "proxy_remarks": [],
                    },
                )
                yaml.safe_load(rendered)
                return

            if template_type in (ClientTemplateType.xray_profile, ClientTemplateType.singbox_profile):
                parsed = json.loads(content)
            else:
                rendered = render_template_string(content)
                parsed = json.loads(rendered)
            if template_type in (ClientTemplateType.user_agent, ClientTemplateType.grpc_user_agent):
                if not isinstance(parsed, dict):
                    raise ValueError("User-Agent template content must render to a JSON object")
                if (_list := parsed.get("list")) is None or not isinstance(_list, list):
                    raise ValueError("User-Agent template content must contain a 'list' field with an array of strings")
                if not _list:
                    raise ValueError("User-Agent template content must contain at least one User-Agent string")
            if template_type in (ClientTemplateType.xray_subscription, ClientTemplateType.singbox_subscription):
                if not isinstance(parsed, dict):
                    raise ValueError("Subscription template content must render to a JSON object")
                if (inb := parsed.get("inbounds")) is None or not isinstance(inb, list):
                    raise ValueError(
                        "Subscription template content must contain a 'inbounds' field with an array of proxy objects"
                    )
                if not inb:
                    raise ValueError("Subscription template content must contain at least one inbound proxy")
                if (out := parsed.get("outbounds")) is None or not isinstance(out, list):
                    raise ValueError(
                        "Subscription template content must contain a 'outbounds' field with an array of proxy objects"
                    )
                if not out:
                    raise ValueError("Subscription template content must contain at least one outbound proxy")
            if template_type in (ClientTemplateType.xray_profile, ClientTemplateType.singbox_profile):
                profile = SubscriptionProfile.model_validate(parsed)
                validate_profile_routing_rules(
                    profile,
                    "xray" if template_type == ClientTemplateType.xray_profile else "sing_box",
                )
        except Exception as exc:
            await self.raise_error(message=f"Invalid template content: {exc!s}", code=400)

    async def create_client_template(
        self,
        db: AsyncSession,
        new_template: ClientTemplateCreate,
        admin: AdminDetails,
    ) -> ClientTemplateResponse:
        await self._validate_template_content(new_template.template_type, new_template.content)
        if new_template.template_type in EXPLICIT_PROFILE_TEMPLATE_TYPES and new_template.is_default:
            await self.raise_error(
                message="Subscription profiles are selected explicitly and cannot be set as default",
                code=400,
            )
        if new_template.template_type == ClientTemplateType.happ_routing and new_template.is_default:
            await self.raise_error("Explicit templates cannot be set as default", 400)

        await lock_settings_row(db)
        try:
            db_template = await create_client_template(db, new_template)
        except IntegrityError:
            await self.raise_error("Template with this name already exists for this type", 409, db=db)

        logger.info(
            f'Client template "{db_template.name}" ({db_template.template_type}) created by admin "{admin.username}"'
        )
        await self._sync_client_template_cache()
        return ClientTemplateResponse.model_validate(db_template)

    async def get_client_templates(
        self,
        db: AsyncSession,
        query: ClientTemplateListQuery,
    ) -> ClientTemplateResponseList:
        templates, count = await get_client_templates(db, query=query)
        return ClientTemplateResponseList(templates=templates, count=count)

    async def get_client_templates_simple(
        self, db: AsyncSession, query: ClientTemplateSimpleListQuery
    ) -> ClientTemplatesSimpleResponse:
        rows, total = await get_client_templates_simple(db=db, query=query)

        templates = [
            ClientTemplateSimple(id=row[0], name=row[1], template_type=row[2], is_default=row[3]) for row in rows
        ]
        return ClientTemplatesSimpleResponse(templates=templates, total=total)

    async def modify_client_template(
        self,
        db: AsyncSession,
        template_id: int,
        modified_template: ClientTemplateModify,
        admin: AdminDetails,
    ) -> ClientTemplateResponse:
        await lock_settings_row(db)
        db_template = await self._get_locked_client_template(db, template_id)
        template_type = ClientTemplateType(db_template.template_type)

        if modified_template.content is not None:
            await self._validate_template_content(template_type, modified_template.content)

        if template_type in EXPLICIT_PROFILE_TEMPLATE_TYPES and modified_template.is_default is True:
            await self.raise_error(
                message="Subscription profiles are selected explicitly and cannot be set as default",
                code=400,
            )
        if modified_template.content is not None and template_type == ClientTemplateType.happ_routing:
            settings = await get_settings(db, for_update=True)
            subscription = Subscription.model_validate(settings.subscription)
            for rule in subscription.rules:
                if rule.happ_routing and rule.happ_routing.template_id == template_id:
                    try:
                        happ_deeplink(
                            modified_template.content,
                            rule.happ_routing.action,
                            rule.happ_routing.transport,
                        )
                    except ValueError as exc:
                        await self.raise_error(message=str(exc), code=400, db=db)

        if template_type == ClientTemplateType.happ_routing and modified_template.is_default:
            await self.raise_error("Explicit templates cannot be set as default", 400)

        if (
            template_type not in EXPLICIT_TEMPLATE_TYPES
            and modified_template.is_default is False
            and db_template.is_default
        ):
            await self.raise_error(
                message="Cannot unset default template directly. Set another template as default instead.",
                code=400,
            )

        try:
            db_template = await modify_client_template(db, db_template, modified_template)
        except IntegrityError:
            await self.raise_error("Template with this name already exists for this type", 409, db=db)

        logger.info(
            f'Client template "{db_template.name}" ({db_template.template_type}) modified by admin "{admin.username}"'
        )
        await self._sync_client_template_cache()
        return ClientTemplateResponse.model_validate(db_template)

    async def remove_client_template(self, db: AsyncSession, template_id: int, admin: AdminDetails) -> None:
        await lock_settings_row(db)
        db_template = await self._get_locked_client_template(db, template_id)
        template_type = ClientTemplateType(db_template.template_type)

        if db_template.is_system:
            await self.raise_error(message="Cannot delete system template", code=403)

        await self._validate_unreferenced(db, {template_id})

        template_count = await count_client_templates_by_type(db, template_type, for_update=True)
        if template_type in LEGACY_REQUIRED_TEMPLATE_TYPES and template_count <= 1:
            await self.raise_error(message="Cannot delete the last template for this type", code=403)

        replacement = None
        if db_template.is_default:
            replacement = await get_first_template_by_type(
                db, template_type, exclude_id=db_template.id, for_update=True
            )

        if replacement is not None:
            await set_default_template(db, replacement, commit=False)

        cleared_hosts = await clear_host_subscription_template_overrides(db, {db_template.id}, commit=False)
        await remove_client_template(db, db_template, commit=False)
        await db.commit()

        logger.info(
            f'Client template "{db_template.name}" ({template_type.value}) deleted by admin "{admin.username}"'
            f" and cleared from {cleared_hosts} host(s)"
        )
        await self._sync_client_template_cache()

    async def bulk_remove_client_templates(
        self, db: AsyncSession, bulk_templates: BulkClientTemplateSelection, admin: AdminDetails
    ) -> RemoveClientTemplatesResponse:
        """Remove multiple client templates by ID - fast batch delete"""
        await lock_settings_row(db)
        ids_list = list(bulk_templates.ids)
        db_templates_list, _ = await get_client_templates(
            db, ClientTemplateListQuery(ids=ids_list, limit=len(ids_list)), for_update=True
        )

        found_ids = {t.id for t in db_templates_list}
        missing = set(ids_list) - found_ids
        if missing:
            await self.raise_error(message="Client template not found", code=404)

        db_templates = list(db_templates_list)
        await self._validate_unreferenced(db, set(ids_list))
        templates_by_type = {}

        # Validate all templates can be deleted
        for db_template in db_templates:
            template_type = ClientTemplateType(db_template.template_type)

            if db_template.is_system:
                await self.raise_error(message=f"Cannot delete system template {db_template.name}", code=403)

            # Group templates by type for efficient counting
            if template_type not in templates_by_type:
                templates_by_type[template_type] = []
            templates_by_type[template_type].append(db_template)

        # Validate we won't leave any type without templates
        for template_type, templates_of_type in templates_by_type.items():
            total_count = await count_client_templates_by_type(db, template_type, for_update=True)
            if template_type in LEGACY_REQUIRED_TEMPLATE_TYPES and total_count <= len(templates_of_type):
                await self.raise_error(
                    message=f"Cannot delete the last template for type {template_type.value}", code=403
                )

        # Resolve default replacements without mutating state yet.
        replacements = []
        for template_type, templates_of_type in templates_by_type.items():
            defaults_to_replace = [t for t in templates_of_type if t.is_default]
            if defaults_to_replace:
                exclude_ids = {t.id for t in templates_of_type}
                replacement = await get_first_template_by_type(
                    db, template_type, exclude_ids=exclude_ids, for_update=True
                )
                if replacement:
                    replacements.append(replacement)

        # Batch delete using CRUD function (single query)
        template_ids = [t.id for t in db_templates]
        template_names = [t.name for t in db_templates]

        for replacement in replacements:
            await set_default_template(db, replacement, commit=False)
        cleared_hosts = await clear_host_subscription_template_overrides(db, template_ids, commit=False)
        await remove_client_templates(db, template_ids, commit=False)
        await db.commit()

        # Sync cache and log
        await self._sync_client_template_cache()
        for db_template in db_templates:
            template_type = ClientTemplateType(db_template.template_type)
            logger.info(
                f'Client template "{db_template.name}" ({template_type.value}) deleted by admin "{admin.username}"'
            )
        if cleared_hosts:
            logger.info(f"Cleared deleted client template overrides from {cleared_hosts} host(s)")

        return RemoveClientTemplatesResponse(templates=template_names, count=len(db_templates))

    async def _validate_unreferenced(self, db: AsyncSession, template_ids: set[int]) -> None:
        settings = await get_settings(db, for_update=True)
        subscription = Subscription.model_validate(settings.subscription)
        referenced_profile_ids = {
            rule.profile_id
            for rule in subscription.rules
            if rule.profile_id is not None and rule.profile_id in template_ids
        }
        referenced_ids = {
            reference
            for rule in subscription.rules
            for reference in (
                rule.profile_id,
                rule.template_id,
                rule.happ_routing.template_id if rule.happ_routing else None,
            )
            if reference is not None and reference in template_ids
        }
        if referenced_ids:
            formatted_ids = ", ".join(str(template_id) for template_id in sorted(referenced_ids))
            kind = "subscription profile(s)" if referenced_ids <= referenced_profile_ids else "client template(s)"
            await self.raise_error(
                message=f"Cannot delete {kind} referenced by settings rules: {formatted_ids}",
                code=409,
                db=db,
            )

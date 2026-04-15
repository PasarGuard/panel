import json

import yaml
from sqlalchemy.exc import IntegrityError

from app.db import AsyncSession
from app.db.crud.client_template import (
    ClientTemplateSortingOptionsSimple,
    count_client_templates_by_type,
    create_client_template,
    get_client_templates,
    get_client_templates_simple,
    get_first_template_by_type,
    modify_client_template,
    remove_client_template,
    remove_client_templates,
    set_default_template,
)
from app.models.admin import AdminDetails
from app.models.client_template import (
    BulkClientTemplateSelection,
    ClientTemplateCreate,
    ClientTemplateModify,
    ClientTemplateResponse,
    ClientTemplateResponseList,
    ClientTemplateSimple,
    ClientTemplatesSimpleResponse,
    ClientTemplateType,
    RemoveClientTemplatesResponse,
)
from app.nats.message import MessageTopic
from app.nats.router import router
from app.subscription.client_templates import refresh_client_templates_cache
from app.templates import render_template_string
from app.utils.logger import get_logger

from . import BaseOperation

logger = get_logger("client-template-operation")


class ClientTemplateOperation(BaseOperation):
    @staticmethod
    async def _sync_client_template_cache() -> None:
        await refresh_client_templates_cache()
        await router.publish(MessageTopic.CLIENT_TEMPLATE, {"action": "refresh"})

    async def _validate_template_content(self, template_type: ClientTemplateType, content: str) -> None:
        try:
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
        except Exception as exc:
            await self.raise_error(message=f"Invalid template content: {str(exc)}", code=400)

    async def create_client_template(
        self,
        db: AsyncSession,
        new_template: ClientTemplateCreate,
        admin: AdminDetails,
    ) -> ClientTemplateResponse:
        await self._validate_template_content(new_template.template_type, new_template.content)

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
        template_type: ClientTemplateType | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> ClientTemplateResponseList:
        templates, count = await get_client_templates(db, template_type=template_type, offset=offset, limit=limit)
        return ClientTemplateResponseList(templates=templates, count=count)

    async def get_client_templates_simple(
        self,
        db: AsyncSession,
        offset: int | None = None,
        limit: int | None = None,
        search: str | None = None,
        template_type: ClientTemplateType | None = None,
        sort: str | None = None,
        all: bool = False,
    ) -> ClientTemplatesSimpleResponse:
        sort_list = []
        if sort is not None:
            opts = sort.strip(",").split(",")
            for opt in opts:
                try:
                    enum_member = ClientTemplateSortingOptionsSimple[opt]
                    sort_list.append(enum_member)
                except KeyError:
                    await self.raise_error(message=f'"{opt}" is not a valid sort option', code=400)

        rows, total = await get_client_templates_simple(
            db=db,
            offset=offset,
            limit=limit,
            search=search,
            template_type=template_type,
            sort=sort_list if sort_list else None,
            skip_pagination=all,
        )

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
        db_template = await self.get_validated_client_template(db, template_id)

        if modified_template.content is not None:
            await self._validate_template_content(
                ClientTemplateType(db_template.template_type), modified_template.content
            )

        if modified_template.is_default is False and db_template.is_default:
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
        db_template = await self.get_validated_client_template(db, template_id)
        template_type = ClientTemplateType(db_template.template_type)

        if db_template.is_system:
            await self.raise_error(message="Cannot delete system template", code=403)

        template_count = await count_client_templates_by_type(db, template_type)
        if template_count <= 1:
            await self.raise_error(message="Cannot delete the last template for this type", code=403)

        replacement = None
        if db_template.is_default:
            replacement = await get_first_template_by_type(db, template_type, exclude_id=db_template.id)

        await remove_client_template(db, db_template)

        if replacement is not None:
            await set_default_template(db, replacement)

        logger.info(f'Client template "{db_template.name}" ({template_type.value}) deleted by admin "{admin.username}"')
        await self._sync_client_template_cache()

    async def bulk_remove_client_templates(
        self, db: AsyncSession, bulk_templates: BulkClientTemplateSelection, admin: AdminDetails
    ) -> RemoveClientTemplatesResponse:
        """Remove multiple client templates by ID - fast batch delete"""
        db_templates = []
        templates_by_type = {}

        # Validate all templates exist and can be deleted
        for template_id in bulk_templates.ids:
            db_template = await self.get_validated_client_template(db, template_id)
            template_type = ClientTemplateType(db_template.template_type)

            if db_template.is_system:
                await self.raise_error(message=f"Cannot delete system template {db_template.name}", code=403)

            # Group templates by type for efficient counting
            if template_type not in templates_by_type:
                templates_by_type[template_type] = []
            templates_by_type[template_type].append(db_template)
            db_templates.append(db_template)

        # Validate we won't leave any type without templates
        for template_type, templates_of_type in templates_by_type.items():
            total_count = await count_client_templates_by_type(db, template_type)
            if total_count <= len(templates_of_type):
                await self.raise_error(
                    message=f"Cannot delete the last template for type {template_type.value}", code=403
                )

        # Handle default template replacements
        for template_type, templates_of_type in templates_by_type.items():
            defaults_to_replace = [t for t in templates_of_type if t.is_default]
            if defaults_to_replace:
                exclude_ids = {t.id for t in templates_of_type}
                replacement = await get_first_template_by_type(db, template_type, exclude_ids=exclude_ids)
                if replacement:
                    await set_default_template(db, replacement)

        # Batch delete using CRUD function (single query)
        template_ids = [t.id for t in db_templates]
        template_names = [t.name for t in db_templates]

        await remove_client_templates(db, template_ids)

        # Sync cache and log
        await self._sync_client_template_cache()
        for db_template in db_templates:
            template_type = ClientTemplateType(db_template.template_type)
            logger.info(
                f'Client template "{db_template.name}" ({template_type.value}) deleted by admin "{admin.username}"'
            )

        return RemoveClientTemplatesResponse(templates=template_names, count=len(db_templates))

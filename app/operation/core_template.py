import json

import yaml
from sqlalchemy.exc import IntegrityError

from app.db import AsyncSession
from app.db.crud.core_template import (
    CoreTemplateSortingOptionsSimple,
    count_core_templates_by_type,
    create_core_template,
    get_core_templates,
    get_core_templates_simple,
    get_first_template_by_type,
    modify_core_template,
    remove_core_template,
    set_default_template,
)
from app.models.admin import AdminDetails
from app.models.core_template import (
    CoreTemplateCreate,
    CoreTemplateModify,
    CoreTemplateResponse,
    CoreTemplateResponseList,
    CoreTemplateSimple,
    CoreTemplatesSimpleResponse,
    CoreTemplateType,
)
from app.templates import render_template_string
from app.utils.logger import get_logger

from . import BaseOperation


logger = get_logger("core-template-operation")


class CoreTemplateOperation(BaseOperation):
    async def _validate_template_content(self, template_type: CoreTemplateType, content: str) -> None:
        try:
            if template_type == CoreTemplateType.clash_subscription:
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
            if template_type in (CoreTemplateType.user_agent, CoreTemplateType.grpc_user_agent) and not isinstance(
                parsed, dict
            ):
                raise ValueError("User-Agent template content must render to a JSON object")
        except Exception as exc:
            await self.raise_error(message=f"Invalid template content: {str(exc)}", code=400)

    async def create_core_template(
        self,
        db: AsyncSession,
        new_template: CoreTemplateCreate,
        admin: AdminDetails,
    ) -> CoreTemplateResponse:
        await self._validate_template_content(new_template.template_type, new_template.content)

        try:
            db_template = await create_core_template(db, new_template)
        except IntegrityError:
            await self.raise_error("Template with this name already exists for this type", 409, db=db)

        logger.info(
            f'Core template "{db_template.name}" ({db_template.template_type}) created by admin "{admin.username}"'
        )
        return CoreTemplateResponse.model_validate(db_template)

    async def get_core_templates(
        self,
        db: AsyncSession,
        template_type: CoreTemplateType | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> CoreTemplateResponseList:
        templates, count = await get_core_templates(db, template_type=template_type, offset=offset, limit=limit)
        return CoreTemplateResponseList(templates=templates, count=count)

    async def get_core_templates_simple(
        self,
        db: AsyncSession,
        offset: int | None = None,
        limit: int | None = None,
        search: str | None = None,
        template_type: CoreTemplateType | None = None,
        sort: str | None = None,
        all: bool = False,
    ) -> CoreTemplatesSimpleResponse:
        sort_list = []
        if sort is not None:
            opts = sort.strip(",").split(",")
            for opt in opts:
                try:
                    enum_member = CoreTemplateSortingOptionsSimple[opt]
                    sort_list.append(enum_member)
                except KeyError:
                    await self.raise_error(message=f'"{opt}" is not a valid sort option', code=400)

        rows, total = await get_core_templates_simple(
            db=db,
            offset=offset,
            limit=limit,
            search=search,
            template_type=template_type,
            sort=sort_list if sort_list else None,
            skip_pagination=all,
        )

        templates = [
            CoreTemplateSimple(id=row[0], name=row[1], template_type=row[2], is_default=row[3]) for row in rows
        ]
        return CoreTemplatesSimpleResponse(templates=templates, total=total)

    async def modify_core_template(
        self,
        db: AsyncSession,
        template_id: int,
        modified_template: CoreTemplateModify,
        admin: AdminDetails,
    ) -> CoreTemplateResponse:
        db_template = await self.get_validated_core_template(db, template_id)

        if modified_template.content is not None:
            await self._validate_template_content(CoreTemplateType(db_template.template_type), modified_template.content)

        if modified_template.is_default is False and db_template.is_default:
            await self.raise_error(
                message="Cannot unset default template directly. Set another template as default instead.",
                code=400,
            )

        try:
            db_template = await modify_core_template(db, db_template, modified_template)
        except IntegrityError:
            await self.raise_error("Template with this name already exists for this type", 409, db=db)

        logger.info(
            f'Core template "{db_template.name}" ({db_template.template_type}) modified by admin "{admin.username}"'
        )
        return CoreTemplateResponse.model_validate(db_template)

    async def remove_core_template(self, db: AsyncSession, template_id: int, admin: AdminDetails) -> None:
        db_template = await self.get_validated_core_template(db, template_id)
        template_type = CoreTemplateType(db_template.template_type)

        if db_template.is_system:
            await self.raise_error(message="Cannot delete system template", code=403)

        template_count = await count_core_templates_by_type(db, template_type)
        if template_count <= 1:
            await self.raise_error(message="Cannot delete the last template for this type", code=403)

        replacement = None
        if db_template.is_default:
            replacement = await get_first_template_by_type(db, template_type, exclude_id=db_template.id)

        await remove_core_template(db, db_template)

        if replacement is not None:
            await set_default_template(db, replacement)

        logger.info(f'Core template "{db_template.name}" ({template_type.value}) deleted by admin "{admin.username}"')

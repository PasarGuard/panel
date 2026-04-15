from sqlalchemy.exc import IntegrityError

from app.db import AsyncSession
import asyncio

from app.db.models import Admin
from app.db.crud.user_template import (
    UserTemplateSortingOptionsSimple,
    create_user_template,
    get_user_templates,
    get_user_templates_simple,
    load_user_template_attrs,
    modify_user_template,
    remove_user_template,
    remove_user_templates,
)
from app.operation import BaseOperation
from app.models.user_template import (
    BulkUserTemplatesActionResponse,
    BulkUserTemplateSelection,
    RemoveUserTemplatesResponse,
    UserTemplateCreate,
    UserTemplateModify,
    UserTemplateResponse,
    UserTemplateSimple,
    UserTemplatesSimpleResponse,
)
from app.utils.logger import get_logger
from app import notification

logger = get_logger("user-template-operation")


class UserTemplateOperation(BaseOperation):
    async def create_user_template(
        self, db: AsyncSession, new_user_template: UserTemplateCreate, admin: Admin
    ) -> UserTemplateResponse:
        for group_id in new_user_template.group_ids:
            await self.get_validated_group(db, group_id)
        try:
            db_user_template = await create_user_template(db, new_user_template)
        except IntegrityError:
            await self.raise_error("Template by this name already exists", 409, db=db)

        user_template = UserTemplateResponse.model_validate(db_user_template)

        asyncio.create_task(notification.create_user_template(user_template, admin.username))

        logger.info(f'User template "{db_user_template.name}" created by admin "{admin.username}"')
        return db_user_template

    async def modify_user_template(
        self, db: AsyncSession, template_id: int, modified_user_template: UserTemplateModify, admin: Admin
    ) -> UserTemplateResponse:
        db_user_template = await self.get_validated_user_template(db, template_id)
        if modified_user_template.group_ids:
            for group_id in modified_user_template.group_ids:
                await self.get_validated_group(db, group_id)
        try:
            db_user_template = await modify_user_template(db, db_user_template, modified_user_template)
        except IntegrityError:
            await self.raise_error("Template by this name already exists", 409, db=db)

        user_template = UserTemplateResponse.model_validate(db_user_template)

        asyncio.create_task(notification.modify_user_template(user_template, admin.username))

        logger.info(f'User template "{db_user_template.name}" modified by admin "{admin.username}"')
        return db_user_template

    async def remove_user_template(self, db: AsyncSession, template_id: int, admin: Admin) -> None:
        db_user_template = await self.get_validated_user_template(db, template_id)
        await remove_user_template(db, db_user_template)
        logger.info(f'User template "{db_user_template.name}" deleted by admin "{admin.username}"')

        asyncio.create_task(notification.remove_user_template(db_user_template.name, admin.username))

    async def get_user_templates(
        self, db: AsyncSession, offset: int = None, limit: int = None
    ) -> list[UserTemplateResponse]:
        return await get_user_templates(db, offset, limit)

    async def get_user_templates_simple(
        self,
        db: AsyncSession,
        offset: int | None = None,
        limit: int | None = None,
        search: str | None = None,
        sort: str | None = None,
        all: bool = False,
    ) -> UserTemplatesSimpleResponse:
        """Get lightweight user template list with only id and name"""
        sort_list = []
        if sort is not None:
            opts = sort.strip(",").split(",")
            for opt in opts:
                try:
                    enum_member = UserTemplateSortingOptionsSimple[opt]
                    sort_list.append(enum_member)
                except KeyError:
                    await self.raise_error(message=f'"{opt}" is not a valid sort option', code=400)

        rows, total = await get_user_templates_simple(
            db=db,
            offset=offset,
            limit=limit,
            search=search,
            sort=sort_list if sort_list else None,
            skip_pagination=all,
        )

        templates = [UserTemplateSimple(id=row[0], name=row[1]) for row in rows]

        return UserTemplatesSimpleResponse(templates=templates, total=total)

    async def bulk_remove_user_templates(
        self, db: AsyncSession, bulk_templates: BulkUserTemplateSelection, admin: Admin
    ) -> RemoveUserTemplatesResponse:
        """Remove multiple user templates by ID"""
        db_templates = []
        for template_id in bulk_templates.ids:
            db_template = await self.get_validated_user_template(db, template_id)
            db_templates.append(db_template)

        template_ids = [t.id for t in db_templates]
        template_names = [t.name for t in db_templates]

        # Batch delete using CRUD function
        await remove_user_templates(db, template_ids)

        # Log and notify
        for name in template_names:
            logger.info(f'User template "{name}" deleted by admin "{admin.username}"')
            asyncio.create_task(notification.remove_user_template(name, admin.username))

        return RemoveUserTemplatesResponse(templates=template_names, count=len(db_templates))

    @staticmethod
    def _build_bulk_action_response(templates: list) -> BulkUserTemplatesActionResponse:
        names = [template.name for template in templates]
        return BulkUserTemplatesActionResponse(templates=names, count=len(names))

    async def bulk_set_user_templates_disabled(
        self,
        db: AsyncSession,
        bulk_templates: BulkUserTemplateSelection,
        admin: Admin,
        *,
        is_disabled: bool,
    ) -> BulkUserTemplatesActionResponse:
        db_templates = []
        for template_id in bulk_templates.ids:
            db_templates.append(await self.get_validated_user_template(db, template_id))

        templates_to_update = [db_template for db_template in db_templates if db_template.is_disabled != is_disabled]

        for db_template in templates_to_update:
            db_template.is_disabled = is_disabled

        await db.commit()

        for db_template in templates_to_update:
            await db.refresh(db_template)
            await load_user_template_attrs(db_template)
            user_template = UserTemplateResponse.model_validate(db_template)
            asyncio.create_task(notification.modify_user_template(user_template, admin.username))
            logger.info(
                f'User template "{db_template.name}" bulk {"disabled" if is_disabled else "enabled"} by admin "{admin.username}"'
            )

        return self._build_bulk_action_response(templates_to_update)

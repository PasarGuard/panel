import asyncio

from sqlalchemy.exc import IntegrityError

from app import notification
from app.db import AsyncSession
from app.db.crud.user_template import (
    create_user_template,
    get_user_templates,
    get_user_templates_simple,
    load_user_template_attrs,
    modify_user_template,
    remove_user_template,
    remove_user_templates,
)
from app.db.models import Admin, UserTemplate
from app.models.user_template import (
    BulkUserTemplatesActionResponse,
    BulkUserTemplateSelection,
    RemoveUserTemplatesResponse,
    UserTemplateCreate,
    UserTemplateListQuery,
    UserTemplateModify,
    UserTemplateResponse,
    UserTemplateSimple,
    UserTemplateSimpleListQuery,
    UserTemplatesSimpleResponse,
)
from app.operation import BaseOperation
from app.operation.permissions import apply_template_access
from app.utils.logger import get_logger

logger = get_logger("user-template-operation")


class UserTemplateOperation(BaseOperation):
    async def _get_template_with_access(self, db: AsyncSession, template_id: int, admin: Admin) -> UserTemplate:
        """Fetch a user template, returning 404 if outside the admin's allowed set."""
        allowed = apply_template_access(admin, [template_id])
        if allowed is not None and template_id not in allowed:
            await self.raise_error("User Template not found", 404)
        return await self.get_validated_user_template(db, template_id)

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
        db_user_template = await self._get_template_with_access(db, template_id, admin)
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
        db_user_template = await self._get_template_with_access(db, template_id, admin)
        await remove_user_template(db, db_user_template)
        logger.info(f'User template "{db_user_template.name}" deleted by admin "{admin.username}"')

        asyncio.create_task(notification.remove_user_template(db_user_template.name, admin.username))

    async def get_user_templates(
        self, db: AsyncSession, query: UserTemplateListQuery, admin: Admin
    ) -> list[UserTemplateResponse]:
        query.ids = apply_template_access(admin, query.ids)
        return await get_user_templates(db, query)

    async def get_user_templates_simple(
        self, db: AsyncSession, query: UserTemplateSimpleListQuery, admin: Admin
    ) -> UserTemplatesSimpleResponse:
        """Get lightweight user template list with only id and name"""
        query.ids = apply_template_access(admin, query.ids)
        rows, total = await get_user_templates_simple(db=db, query=query)
        templates = [UserTemplateSimple(id=row[0], name=row[1]) for row in rows]
        return UserTemplatesSimpleResponse(templates=templates, total=total)

    async def bulk_remove_user_templates(
        self, db: AsyncSession, bulk_templates: BulkUserTemplateSelection, admin: Admin
    ) -> RemoveUserTemplatesResponse:
        """Remove multiple user templates by ID"""
        requested_ids = list(bulk_templates.ids)
        allowed_ids = apply_template_access(admin, requested_ids)
        # Fetch all in one query
        db_templates = await get_user_templates(db, UserTemplateListQuery(ids=allowed_ids or []))
        found_ids = {t.id for t in db_templates}
        for tid in requested_ids:
            if tid not in found_ids:
                await self.raise_error("User Template not found", 404)

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
        requested_ids = list(bulk_templates.ids)
        allowed_ids = apply_template_access(admin, requested_ids)
        db_templates = await get_user_templates(db, UserTemplateListQuery(ids=allowed_ids or []))
        found_ids = {t.id for t in db_templates}
        for tid in requested_ids:
            if tid not in found_ids:
                await self.raise_error("User Template not found", 404)

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

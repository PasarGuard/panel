import asyncio

from sqlalchemy.exc import IntegrityError

from app import notification
from app.db import AsyncSession
from app.db.crud.admin_role import (
    count_admins_by_role,
    create_role,
    delete_role,
    get_role,
    get_roles,
    get_roles_simple,
    modify_role,
)
from app.models.admin import AdminDetails
from app.models.admin_role import (
    AdminRoleCreate,
    AdminRoleListQuery,
    AdminRoleModify,
    AdminRoleResponse,
    AdminRoleSimple,
    AdminRolesResponse,
    AdminRolesSimpleResponse,
)
from app.operation import BaseOperation
from app.utils.logger import get_logger

logger = get_logger("admin-role-operation")


class AdminRoleOperation(BaseOperation):
    async def get_roles(self, db: AsyncSession, query: AdminRoleListQuery) -> AdminRolesResponse:
        """List all roles with optional search and pagination."""
        roles, total = await get_roles(db, query)
        return AdminRolesResponse(
            roles=[AdminRoleResponse.model_validate(r) for r in roles],
            total=total,
        )

    async def get_roles_simple(self, db: AsyncSession) -> AdminRolesSimpleResponse:
        """List all roles as lightweight id/name/is_owner tuples."""
        rows = await get_roles_simple(db)
        return AdminRolesSimpleResponse(
            roles=[AdminRoleSimple(id=row[0], name=row[1], is_owner=row[2]) for row in rows],
            total=len(rows),
        )

    async def get_role(self, db: AsyncSession, role_id: int) -> AdminRoleResponse:
        """Fetch a single role by ID."""
        role = await get_role(db, role_id)
        if role is None:
            await self.raise_error(message="Role not found", code=404)
        return AdminRoleResponse.model_validate(role)

    async def create_role(self, db: AsyncSession, data: AdminRoleCreate, admin: AdminDetails) -> AdminRoleResponse:
        """Create a new role."""
        try:
            role = await create_role(db, data)
            await db.commit()
            await db.refresh(role)
        except IntegrityError:
            await self.raise_error(message="Role with this name already exists", code=409, db=db)

        logger.info(f'Role "{role.name}" created by admin "{admin.username}"')
        asyncio.create_task(notification.create_admin_role(AdminRoleResponse.model_validate(role), admin.username))
        return AdminRoleResponse.model_validate(role)

    async def modify_role(
        self, db: AsyncSession, role_id: int, data: AdminRoleModify, admin: AdminDetails
    ) -> AdminRoleResponse:
        """Modify an existing role. Owner role cannot be modified."""
        role = await get_role(db, role_id)
        if role is None:
            await self.raise_error(message="Role not found", code=404)

        try:
            role = await modify_role(db, role, data)
            await db.commit()
        except ValueError as e:
            await self.raise_error(message=str(e), code=403)
        except IntegrityError:
            await self.raise_error(message="Role with this name already exists", code=409, db=db)

        logger.info(f'Role "{role.name}" modified by admin "{admin.username}"')
        response = AdminRoleResponse.model_validate(role)
        asyncio.create_task(notification.modify_admin_role(response, admin.username))
        return response

    async def delete_role(self, db: AsyncSession, role_id: int, admin: AdminDetails) -> None:
        """Delete a role. Built-in roles (id 1, 2, 3) cannot be deleted."""
        role = await get_role(db, role_id)
        if role is None:
            await self.raise_error(message="Role not found", code=404)

        if role.is_builtin:
            await self.raise_error(message=f"Cannot delete built-in role '{role.name}'", code=403)

        count = await count_admins_by_role(db, role_id)
        if count > 0:
            await self.raise_error(
                message=f"Cannot delete role '{role.name}': {count} admin(s) are assigned to it",
                code=409,
            )

        try:
            await delete_role(db, role)
            await db.commit()
        except ValueError as e:
            await self.raise_error(message=str(e), code=403)

        logger.info(f'Role "{role.name}" deleted by admin "{admin.username}"')
        asyncio.create_task(notification.remove_admin_role(AdminRoleResponse.model_validate(role), admin.username))

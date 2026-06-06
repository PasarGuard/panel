from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Admin, AdminRole
from app.models.admin_role import AdminRoleCreate, AdminRoleListQuery, AdminRoleModify, AdminRoleSortField


def _sort_clause(sort_option):
    field_map = {
        AdminRoleSortField.id: AdminRole.id,
        AdminRoleSortField.name: AdminRole.name,
        AdminRoleSortField.created_at: AdminRole.created_at,
    }
    col = field_map[sort_option.field]
    return col.desc() if sort_option.is_desc else col.asc()


async def get_role(db: AsyncSession, role_id: int) -> AdminRole | None:
    return (await db.execute(select(AdminRole).where(AdminRole.id == role_id))).scalar_one_or_none()


async def get_role_by_name(db: AsyncSession, name: str) -> AdminRole | None:
    return (await db.execute(select(AdminRole).where(AdminRole.name == name))).scalar_one_or_none()


async def get_roles(db: AsyncSession, query: AdminRoleListQuery) -> tuple[list[AdminRole], int]:
    stmt = select(AdminRole)
    if query.search:
        stmt = stmt.where(AdminRole.name.ilike(f"%{query.search}%"))
    if query.sort:
        stmt = stmt.order_by(*[_sort_clause(s) for s in query.sort])

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

    if query.offset:
        stmt = stmt.offset(query.offset)
    if query.limit:
        stmt = stmt.limit(query.limit)

    roles = list((await db.execute(stmt)).scalars().all())
    return roles, total


async def get_roles_simple(db: AsyncSession) -> list[AdminRole]:
    return list((await db.execute(select(AdminRole.id, AdminRole.name, AdminRole.is_owner))).all())


async def create_role(db: AsyncSession, data: AdminRoleCreate) -> AdminRole:
    role = AdminRole(
        name=data.name,
        permissions=data.permissions.model_dump(exclude_none=True),
        limits=data.limits.model_dump(),
        features=data.features.model_dump(),
        access=data.access.model_dump(),
        hwid=data.hwid.model_dump(),
        disabled_when_limited=data.disabled_when_limited,
        disconnect_users_when_limited=data.disconnect_users_when_limited,
        disconnect_users_when_disabled=data.disconnect_users_when_disabled,
    )
    db.add(role)
    await db.flush()
    await db.refresh(role)
    return role


async def modify_role(db: AsyncSession, role: AdminRole, data: AdminRoleModify) -> AdminRole:
    if role.is_owner:
        raise ValueError(f"Cannot modify owner role '{role.name}'")
    if data.name is not None:
        role.name = data.name
    if data.permissions is not None:
        role.permissions = data.permissions.model_dump(exclude_none=True)
    if data.limits is not None:
        role.limits = data.limits.model_dump()
    if data.features is not None:
        role.features = data.features.model_dump()
    if data.access is not None:
        role.access = data.access.model_dump()
    if data.hwid is not None:
        role.hwid = data.hwid.model_dump()
    if data.disabled_when_limited is not None:
        role.disabled_when_limited = data.disabled_when_limited
    if data.disconnect_users_when_limited is not None:
        role.disconnect_users_when_limited = data.disconnect_users_when_limited
    if data.disconnect_users_when_disabled is not None:
        role.disconnect_users_when_disabled = data.disconnect_users_when_disabled
    await db.flush()
    await db.refresh(role)
    return role


async def count_admins_by_role(db: AsyncSession, role_id: int) -> int:
    """Return the number of admins assigned to the given role."""
    return (await db.execute(select(func.count()).where(Admin.role_id == role_id))).scalar() or 0


async def delete_role(db: AsyncSession, role: AdminRole) -> None:
    if role.id in (1, 2, 3):
        raise ValueError(f"Cannot delete built-in role '{role.name}'")
    await db.delete(role)
    await db.flush()

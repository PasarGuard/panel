from app.db import AsyncSession, GetDB
from app.db.crud.admin import get_active_to_limited_admins, update_admin_status
from app.db.crud.user import get_users
from app.db.models import Admin, AdminStatus, UserStatus
from app.models.user import UserListQuery
from app.node.sync import remove_users as sync_remove_users, sync_users


async def admin_users_sync_blocked(admin: Admin) -> bool:
    role = admin.__dict__.get("role")
    if role is None:
        try:
            role = await admin.awaitable_attrs.role
        except AttributeError:
            role = None

    if admin.status == AdminStatus.limited:
        return bool(role and role.disconnect_users_when_limited)
    if admin.status == AdminStatus.disabled:
        return bool(role and role.disconnect_users_when_disabled)
    return False


async def sync_admin_users_for_block_transition(
    db: AsyncSession,
    admin: Admin,
    was_blocked: bool,
) -> int:
    is_blocked = await admin_users_sync_blocked(admin)
    if was_blocked == is_blocked:
        return 0

    if is_blocked:
        users = await get_users(
            db,
            query=UserListQuery(status=[UserStatus.active, UserStatus.on_hold]),
            admin=admin,
        )
        await sync_remove_users(users)
    else:
        users = await get_users(db, query=UserListQuery(), admin=admin, load_admin_role=True)
        await sync_users(users)

    return len(users)


async def limit_exceeded_admins(db: AsyncSession, logger=None) -> int:
    admins = await get_active_to_limited_admins(db)
    if not admins:
        return 0

    for admin in admins:
        await update_admin_status(db, admin, AdminStatus.limited)
        if logger:
            logger.info(f'Admin "{admin.username}" status changed to limited')

        synced_count = await sync_admin_users_for_block_transition(db, admin, was_blocked=False)
        if synced_count and logger:
            logger.info(f'Admin "{admin.username}" removed {synced_count} users from nodes')

    return len(admins)


async def enforce_admin_limits_now(logger=None):
    """Flip active admins that exceeded data_limit without waiting for the scheduler tick."""
    async with GetDB() as db:
        await limit_exceeded_admins(db, logger=logger)

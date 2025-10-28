from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Admin, AdminUsageLogs
from app.models.admin import AdminCreate, AdminModify

AdminsSortingOptions = Enum(
    "AdminsSortingOptions",
    {
        "username": Admin.username.asc(),
        "created_at": Admin.created_at.asc(),
        "used_traffic": Admin.used_traffic.asc(),
        "-username": Admin.username.desc(),
        "-created_at": Admin.created_at.desc(),
        "-used_traffic": Admin.used_traffic.desc(),
    },
)


def get_admin_query():
    return select(Admin).options(selectinload(Admin.users), selectinload(Admin.usage_logs))


async def get_admin(db: AsyncSession, username: str) -> Admin:
    """
    Retrieves an admin by username.

    Args:
        db (AsyncSession): Database session.
        username (str): The username of the admin.

    Returns:
        Admin: The admin object.
    """
    admin = (await db.execute(get_admin_query().where(Admin.username == username))).unique().scalar_one_or_none()
    return admin


async def create_admin(db: AsyncSession, admin: AdminCreate) -> Admin:
    """
    Creates a new admin in the database.

    Args:
        db (AsyncSession): Database session.
        admin (AdminCreate): The admin creation data.

    Returns:
        Admin: The created admin object.
    """
    db_admin = Admin(**admin.model_dump(exclude={"password"}), hashed_password=admin.hashed_password)
    db.add(db_admin)
    await db.commit()

    # Re-fetch the admin with relationships eagerly loaded to prevent lazy-loading in sync context
    return await get_admin(db, admin.username)


async def update_admin(db: AsyncSession, db_admin: Admin, modified_admin: AdminModify) -> Admin:
    """
    Updates an admin's details.

    Args:
        db (AsyncSession): Database session.
        dbadmin (Admin): The admin object to be updated.
        modified_admin (AdminModify): The modified admin data.

    Returns:
        Admin: The updated admin object.
    """
    if modified_admin.is_sudo is not None:
        db_admin.is_sudo = modified_admin.is_sudo
    if modified_admin.is_disabled is not None:
        db_admin.is_disabled = modified_admin.is_disabled
    if modified_admin.hashed_password is not None and db_admin.hashed_password != modified_admin.hashed_password:
        db_admin.hashed_password = modified_admin.hashed_password
        db_admin.password_reset_at = datetime.now(timezone.utc)
    if modified_admin.telegram_id is not None:
        db_admin.telegram_id = modified_admin.telegram_id
    if modified_admin.discord_webhook is not None:
        db_admin.discord_webhook = modified_admin.discord_webhook
    if modified_admin.discord_id is not None:
        db_admin.discord_id = modified_admin.discord_id
    if modified_admin.sub_template is not None:
        db_admin.sub_template = modified_admin.sub_template
    if modified_admin.sub_domain is not None:
        db_admin.sub_domain = modified_admin.sub_domain
    if modified_admin.support_url is not None:
        db_admin.support_url = modified_admin.support_url
    if modified_admin.profile_title is not None:
        db_admin.profile_title = modified_admin.profile_title

    username = db_admin.username

    await db.commit()

    # Return a freshly loaded admin instance to avoid accessing expired attributes
    return await get_admin(db, username)


async def remove_admin(db: AsyncSession, dbadmin: Admin) -> None:
    """
    Removes an admin from the database.

    Args:
        db (AsyncSession): Database session.
        dbadmin (Admin): The admin object to be removed.
    """
    await db.delete(dbadmin)
    await db.commit()


async def get_admin_by_id(db: AsyncSession, id: int) -> Admin:
    """
    Retrieves an admin by their ID.

    Args:
        db (AsyncSession): Database session.
        id (int): The ID of the admin.

    Returns:
        Admin: The admin object.
    """
    admin = (await db.execute(get_admin_query().where(Admin.id == id))).first()
    return admin


async def get_admin_by_telegram_id(db: AsyncSession, telegram_id: int) -> Admin:
    """
    Retrieves an admin by their Telegram ID.

    Args:
        db (AsyncSession): Database session.
        telegram_id (int): The Telegram ID of the admin.

    Returns:
        Admin: The admin object.
    """
    admin = (await db.execute(get_admin_query().where(Admin.telegram_id == telegram_id))).scalar_one_or_none()
    return admin


async def get_admin_by_discord_id(db: AsyncSession, discord_id: int) -> Admin:
    """
    Retrieves an admin by their Discord ID.

    Args:
        db (AsyncSession): Database session.
        discord_id (int): The Discord ID of the admin.

    Returns:
        Admin: The admin object.
    """
    admin = (await db.execute(get_admin_query().where(Admin.discord_id == discord_id))).first()
    return admin


async def get_admins(
    db: AsyncSession,
    offset: int | None = None,
    limit: int | None = None,
    username: str | None = None,
    sort: list[AdminsSortingOptions] | None = None,
) -> list[Admin]:
    """
    Retrieves a list of admins with optional filters and pagination.

    Args:
        db (AsyncSession): Database session.
        offset (Optional[int]): The number of records to skip (for pagination).
        limit (Optional[int]): The maximum number of records to return.
        username (Optional[str]): The username to filter by.
        sort (Optional[list[AdminsSortingOptions]]): Sort options for ordering results.

    Returns:
        List[Admin]: A list of admin objects.
    """
    query = get_admin_query()
    if username:
        query = query.where(Admin.username.ilike(f"%{username}%"))

    if sort:
        query = query.order_by(*sort)

    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    admins = (await db.execute(query)).scalars().all()

    return admins


async def reset_admin_usage(db: AsyncSession, db_admin: Admin) -> Admin:
    """
    Retrieves an admin's usage by their username.
    Args:
        db (AsyncSession): Database session.
        db_admin (Admin): The admin object to be updated.
    Returns:
        Admin: The updated admin.
    """
    if db_admin.used_traffic == 0:
        return db_admin

    usage_log = AdminUsageLogs(admin_id=db_admin.id, used_traffic_at_reset=db_admin.used_traffic)
    db.add(usage_log)
    db_admin.used_traffic = 0

    await db.commit()
    await db.refresh(db_admin)
    return db_admin


async def get_admins_count(db: AsyncSession) -> int:
    """
    Retrieves the total count of admins.

    Args:
        db (AsyncSession): Database session.

    Returns:
        int: The total number of admins.
    """
    count = (await db.execute(select(func.count(Admin.id)))).scalar_one()
    return count

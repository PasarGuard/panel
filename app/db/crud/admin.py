from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.general import _build_trunc_expression, _convert_period_start_timezone
from app.db.models import Admin, AdminUsageLogs, NodeUserUsage, User
from app.models.admin import AdminCreate, AdminDetails, AdminModify, hash_password
from app.models.stats import Period, UserUsageStat, UserUsageStatsList


async def load_admin_attrs(admin: Admin):
    try:
        await admin.awaitable_attrs.users
        await admin.awaitable_attrs.usage_logs
    except AttributeError:
        pass


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


AdminsSortingOptionsSimple = Enum(
    "AdminsSortingOptionsSimple",
    {
        "username": Admin.username.asc(),
        "-username": Admin.username.desc(),
    },
)


async def get_admin(db: AsyncSession, username: str) -> Admin:
    """
    Retrieves an admin by username.

    Args:
        db (AsyncSession): Database session.
        username (str): The username of the admin.

    Returns:
        Admin: The admin object.
    """
    admin = (await db.execute(select(Admin).where(Admin.username == username))).unique().scalar_one_or_none()
    if admin:
        await load_admin_attrs(admin)
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
    db_admin = Admin(**admin.model_dump(exclude={"password"}), hashed_password=await hash_password(admin.password))
    db.add(db_admin)
    await db.commit()
    await db.refresh(db_admin)
    await load_admin_attrs(db_admin)
    return db_admin


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
    if modified_admin.password is not None:
        db_admin.hashed_password = await hash_password(modified_admin.password)
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
    if modified_admin.notification_enable is not None:
        db_admin.notification_enable = modified_admin.notification_enable.model_dump()

    await db.commit()
    await load_admin_attrs(db_admin)
    return db_admin


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
    admin = (await db.execute(select(Admin).where(Admin.id == id))).first()
    if admin:
        await load_admin_attrs(admin)
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
    admin = (await db.execute(select(Admin).where(Admin.telegram_id == telegram_id))).scalar_one_or_none()
    if admin:
        await load_admin_attrs(admin)
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
    admin = (await db.execute(select(Admin).where(Admin.discord_id == discord_id))).first()
    if admin:
        await load_admin_attrs(admin)
    return admin


async def get_admins(
    db: AsyncSession,
    offset: int | None = None,
    limit: int | None = None,
    username: str | None = None,
    sort: list[AdminsSortingOptions] | None = None,
    return_with_count: bool = False,
    compact: bool = False,
) -> list[Admin] | tuple[list[Admin], int, int, int]:
    """
    Retrieves a list of admins with optional filters and pagination.

    Args:
        db (AsyncSession): Database session.
        offset (Optional[int]): The number of records to skip (for pagination).
        limit (Optional[int]): The maximum number of records to return.
        username (Optional[str]): The username to filter by.
        sort (Optional[list[AdminsSortingOptions]]): Sort options for ordering results.
        return_with_count (bool): If True, returns tuple with (admins, total, active, disabled).

    Returns:
        List[Admin] | tuple[list[Admin], int, int, int]: A list of admin objects or tuple with counts.
    """
    base_query = select(Admin)
    if username:
        base_query = base_query.where(Admin.username.ilike(f"%{username}%"))

    total = None
    active = None
    disabled = None

    if return_with_count:
        counts_stmt = select(
            func.count(Admin.id).label("total"),
            func.sum(case((Admin.is_disabled.is_(False), 1), else_=0)).label("active"),
            func.sum(case((Admin.is_disabled.is_(True), 1), else_=0)).label("disabled"),
        )
        if username:
            counts_stmt = counts_stmt.where(Admin.username.ilike(f"%{username}%"))
        result = await db.execute(counts_stmt)
        row = result.one()
        total = row.total or 0
        active = row.active or 0
        disabled = row.disabled or 0

    query = base_query
    if sort:
        query = query.order_by(*sort)

    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    if compact:
        users_count_subq = (
            select(User.admin_id.label("admin_id"), func.count(User.id).label("total_users"))
            .group_by(User.admin_id)
            .subquery()
        )
        reset_usage_subq = (
            select(
                AdminUsageLogs.admin_id.label("admin_id"),
                func.coalesce(func.sum(AdminUsageLogs.used_traffic_at_reset), 0).label("reseted_usage"),
            )
            .group_by(AdminUsageLogs.admin_id)
            .subquery()
        )

        query = (
            select(
                Admin,
                func.coalesce(users_count_subq.c.total_users, 0).label("total_users"),
                func.coalesce(reset_usage_subq.c.reseted_usage, 0).label("reseted_usage"),
            )
            .outerjoin(users_count_subq, users_count_subq.c.admin_id == Admin.id)
            .outerjoin(reset_usage_subq, reset_usage_subq.c.admin_id == Admin.id)
        )
        if username:
            query = query.where(Admin.username.ilike(f"%{username}%"))
        if sort:
            query = query.order_by(*sort)
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        rows = (await db.execute(query)).all()
        admins = []
        for admin, total_users, reseted_usage in rows:
            lifetime_used_traffic = int((reseted_usage or 0) + (admin.used_traffic or 0))
            admins.append(
                AdminDetails(
                    id=admin.id,
                    username=admin.username,
                    is_sudo=admin.is_sudo,
                    total_users=int(total_users or 0),
                    used_traffic=int(admin.used_traffic or 0),
                    is_disabled=admin.is_disabled,
                    telegram_id=admin.telegram_id,
                    discord_webhook=admin.discord_webhook,
                    sub_domain=admin.sub_domain,
                    profile_title=admin.profile_title,
                    support_url=admin.support_url,
                    notification_enable=admin.notification_enable,
                    discord_id=admin.discord_id,
                    sub_template=admin.sub_template,
                    lifetime_used_traffic=lifetime_used_traffic,
                )
            )

        if return_with_count:
            return admins, total, active, disabled
        return admins

    admins = (await db.execute(query)).scalars().all()
    for admin in admins:
        await load_admin_attrs(admin)

    if return_with_count:
        return admins, total, active, disabled
    return admins


async def get_admins_simple(
    db: AsyncSession,
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: list[AdminsSortingOptionsSimple] | None = None,
    skip_pagination: bool = False,
) -> tuple[list[tuple[int, str]], int]:
    """
    Retrieves lightweight admin data with only id and username.

    Args:
        db: Database session.
        offset: Number of records to skip.
        limit: Number of records to retrieve.
        search: Search term for username.
        sort: Sort options.
        skip_pagination: If True, ignore offset/limit and return all records (max 1,000).

    Returns:
        Tuple of (list of (id, username) tuples, total_count).
    """
    stmt = select(Admin.id, Admin.username)

    if search:
        stmt = stmt.where(Admin.username.ilike(f"%{search}%"))

    if sort:
        sort_list = []
        for s in sort:
            if isinstance(s.value, tuple):
                sort_list.extend(s.value)
            else:
                sort_list.append(s.value)
        stmt = stmt.order_by(*sort_list)

    # Get count BEFORE pagination (always)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    # Apply pagination or safety limit
    if not skip_pagination:
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
    else:
        stmt = stmt.limit(10000)  # Safety limit when all=true

    # Execute and return
    result = await db.execute(stmt)
    rows = result.all()

    return rows, total


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
    await load_admin_attrs(db_admin)
    return db_admin


async def get_admin_usages(
    db: AsyncSession,
    admin_id: int | None,
    start: datetime,
    end: datetime,
    period: Period,
    node_id: int | None = None,
    group_by_node: bool = False,
) -> UserUsageStatsList:
    """
    Retrieves aggregated usage data for an admin's users within a specified time range,
    grouped by the specified time period.

    Args:
        db (AsyncSession): Database session for querying.
        admin_id (int | None): Admin ID to filter users by. If None, include all admins.
        start (datetime): Start of the period.
        end (datetime): End of the period.
        period (Period): Time period to group by ('minute', 'hour', 'day', 'month').
        node_id (Optional[int]): Filter results by specific node ID if provided.

    Returns:
        UserUsageStatsList: Aggregated usage data for each period.
    """
    # Build truncation expression with timezone support
    trunc_expr = _build_trunc_expression(db, period, NodeUserUsage.created_at, start=start)

    conditions = [
        NodeUserUsage.created_at >= start,
        NodeUserUsage.created_at <= end,
    ]

    if admin_id is not None:
        conditions.append(User.admin_id == admin_id)

    if node_id is not None:
        conditions.append(NodeUserUsage.node_id == node_id)
    else:
        node_id = -1

    if group_by_node:
        stmt = (
            select(
                trunc_expr.label("period_start"),
                func.coalesce(NodeUserUsage.node_id, 0).label("node_id"),
                func.sum(NodeUserUsage.used_traffic).label("total_traffic"),
            )
            .select_from(NodeUserUsage)
            .join(User, User.id == NodeUserUsage.user_id)
            .where(and_(*conditions))
            .group_by(trunc_expr, NodeUserUsage.node_id)
            .order_by(trunc_expr)
        )
    else:
        stmt = (
            select(
                trunc_expr.label("period_start"),
                func.sum(NodeUserUsage.used_traffic).label("total_traffic"),
            )
            .select_from(NodeUserUsage)
            .join(User, User.id == NodeUserUsage.user_id)
            .where(and_(*conditions))
            .group_by(trunc_expr)
            .order_by(trunc_expr)
        )

    target_tz = start.tzinfo
    result = await db.execute(stmt)
    stats = {}
    for row in result.mappings():
        row_dict = dict(row)
        node_id_val = row_dict.pop("node_id", node_id)

        _convert_period_start_timezone(row_dict, target_tz)

        if node_id_val not in stats:
            stats[node_id_val] = []
        stats[node_id_val].append(UserUsageStat(**row_dict))

    return UserUsageStatsList(period=period, start=start, end=end, stats=stats)


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

from datetime import datetime, timezone

from sqlalchemy import and_, case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.general import (
    _build_trunc_expression,
    attach_timezone_to_period_start,
    get_complete_period_start_for_filter,
    to_utc_for_filter,
)
from app.db.models import Admin, AdminUsageLogs, NodeUserUsage, User
from app.models.admin import (
    AdminCreate,
    AdminDetails,
    AdminListQuery,
    AdminModify,
    AdminSimpleListQuery,
    AdminSimpleSortField,
    AdminSimpleSortOption,
    AdminSortField,
    AdminSortOption,
    hash_password,
)
from app.models.stats import Period, UserUsageStat, UserUsageStatsList
from app.utils.logger import get_logger

logger = get_logger("admin-crud")


async def load_admin_attrs(admin: Admin, load_users: bool = True, load_usage_logs: bool = True):
    try:
        if load_users:
            await admin.awaitable_attrs.users
        if load_usage_logs:
            await admin.awaitable_attrs.usage_logs
    except AttributeError:
        pass


def _build_admin_sort_clause(sort_option: AdminSortOption):
    field_map = {
        AdminSortField.username: Admin.username,
        AdminSortField.created_at: Admin.created_at,
        AdminSortField.used_traffic: Admin.used_traffic,
    }
    column = field_map[sort_option.field]
    return column.desc() if sort_option.value.startswith("-") else column.asc()


def _build_admin_simple_sort_clause(sort_option: AdminSimpleSortOption):
    field_map = {
        AdminSimpleSortField.id: Admin.id,
        AdminSimpleSortField.username: Admin.username,
    }
    column = field_map[sort_option.field]
    return column.desc() if sort_option.value.startswith("-") else column.asc()


async def get_admin(
    db: AsyncSession,
    username: str,
    *,
    load_users: bool = True,
    load_usage_logs: bool = True,
) -> Admin:
    admin = (await db.execute(select(Admin).where(Admin.username == username))).unique().scalar_one_or_none()
    if admin:
        await load_admin_attrs(admin, load_users=load_users, load_usage_logs=load_usage_logs)
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
    if modified_admin.note is not None:
        db_admin.note = modified_admin.note
    if modified_admin.notification_enable is not None:
        db_admin.notification_enable = modified_admin.notification_enable.model_dump()

    await db.commit()
    await db.refresh(db_admin)
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


async def get_admin_by_id(
    db: AsyncSession,
    id: int,
    *,
    load_users: bool = True,
    load_usage_logs: bool = True,
) -> Admin:
    admin = (await db.execute(select(Admin).where(Admin.id == id))).unique().scalar_one_or_none()
    if admin:
        await load_admin_attrs(admin, load_users=load_users, load_usage_logs=load_usage_logs)
    return admin


async def get_admin_by_telegram_id(
    db: AsyncSession,
    telegram_id: int,
    *,
    load_users: bool = True,
    load_usage_logs: bool = True,
) -> Admin:
    admins = (
        (await db.execute(select(Admin).where(Admin.telegram_id == telegram_id).order_by(Admin.id.asc()).limit(2)))
        .scalars()
        .all()
    )
    if len(admins) > 1:
        logger.error(
            "Duplicate telegram_id found for admins; using earliest record",
            extra={"telegram_id": telegram_id, "admin_ids": [admin.id for admin in admins]},
        )
    admin = admins[0] if admins else None
    if admin:
        await load_admin_attrs(admin, load_users=load_users, load_usage_logs=load_usage_logs)
    return admin


async def find_admins_by_telegram_id(
    db: AsyncSession,
    telegram_id: int,
    *,
    exclude_admin_id: int | None = None,
    limit: int | None = None,
) -> list[Admin]:
    stmt = select(Admin).where(Admin.telegram_id == telegram_id).order_by(Admin.id.asc())
    if exclude_admin_id is not None:
        stmt = stmt.where(Admin.id != exclude_admin_id)
    if limit is not None:
        stmt = stmt.limit(limit)
    return (await db.execute(stmt)).scalars().all()


async def get_admin_by_discord_id(
    db: AsyncSession,
    discord_id: int,
    *,
    load_users: bool = True,
    load_usage_logs: bool = True,
) -> Admin:
    admin = (await db.execute(select(Admin).where(Admin.discord_id == discord_id))).scalar_one_or_none()
    if admin:
        await load_admin_attrs(admin, load_users=load_users, load_usage_logs=load_usage_logs)
    return admin


async def get_admins(
    db: AsyncSession,
    query: AdminListQuery,
    return_with_count: bool = False,
    compact: bool = False,
) -> list[Admin] | tuple[list[Admin], int, int, int]:
    """
    Retrieves a list of admins with optional filters and pagination.

    Args:
        db (AsyncSession): Database session.
        query: Structured admin list query.
        return_with_count (bool): If True, returns tuple with (admins, total, active, disabled).

    Returns:
        List[Admin] | tuple[list[Admin], int, int, int]: A list of admin objects or tuple with counts.
    """
    params = query
    total = None
    active = None
    disabled = None

    if return_with_count:
        counts_stmt = select(
            func.count(Admin.id).label("total"),
            func.sum(case((Admin.is_disabled.is_(False), 1), else_=0)).label("active"),
            func.sum(case((Admin.is_disabled.is_(True), 1), else_=0)).label("disabled"),
        )
        if params.ids:
            counts_stmt = counts_stmt.where(Admin.id.in_(params.ids))
        if params.usernames:
            counts_stmt = counts_stmt.where(Admin.username.in_(params.usernames))
        if params.username:
            counts_stmt = counts_stmt.where(Admin.username.ilike(f"%{params.username}%"))

        result = await db.execute(counts_stmt)
        row = result.one()
        total = row.total or 0
        active = row.active or 0
        disabled = row.disabled or 0

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

        stmt = select(
            Admin,
            func.coalesce(users_count_subq.c.total_users, 0).label("total_users"),
            func.coalesce(reset_usage_subq.c.reseted_usage, 0).label("reseted_usage"),
        )
        stmt = stmt.outerjoin(users_count_subq, users_count_subq.c.admin_id == Admin.id)
        stmt = stmt.outerjoin(reset_usage_subq, reset_usage_subq.c.admin_id == Admin.id)
    else:
        stmt = select(Admin)

    # Apply filters consistently
    if params.ids:
        stmt = stmt.where(Admin.id.in_(params.ids))
    if params.usernames:
        stmt = stmt.where(Admin.username.in_(params.usernames))
    if params.username:
        stmt = stmt.where(Admin.username.ilike(f"%{params.username}%"))

    # Apply sorting
    if params.sort:
        stmt = stmt.order_by(*[_build_admin_sort_clause(sort_option) for sort_option in params.sort])

    # Apply pagination
    if params.offset is not None:
        stmt = stmt.offset(params.offset)
    if params.limit is not None:
        stmt = stmt.limit(params.limit)

    if compact:
        rows = (await db.execute(stmt)).unique().all()
        admins = []
        for admin, total_users, reseted_usage in rows:
            lifetime_used_traffic = int((reseted_usage or 0) + (admin.used_traffic or 0))
            admins.append(
                AdminDetails(
                    id=admin.id,
                    username=admin.username,
                    total_users=int(total_users or 0),
                    used_traffic=int(admin.used_traffic or 0),
                    is_disabled=admin.is_disabled,
                    telegram_id=admin.telegram_id,
                    discord_webhook=admin.discord_webhook,
                    sub_domain=admin.sub_domain,
                    profile_title=admin.profile_title,
                    support_url=admin.support_url,
                    note=admin.note,
                    notification_enable=admin.notification_enable,
                    discord_id=admin.discord_id,
                    sub_template=admin.sub_template,
                    lifetime_used_traffic=lifetime_used_traffic,
                )
            )
    else:
        admins = list((await db.execute(stmt)).scalars().all())
        for admin in admins:
            await load_admin_attrs(admin)

    if return_with_count:
        return admins, total, active, disabled
    return admins


async def get_admins_simple(
    db: AsyncSession,
    query: AdminSimpleListQuery,
) -> tuple[list[tuple[int, str]], int]:
    """
    Retrieves lightweight admin data with only id and username.

    Args:
        db: Database session.
        query: Structured lightweight admin query.

    Returns:
        Tuple of (list of (id, username) tuples, total_count).
    """
    stmt = select(Admin.id, Admin.username)

    if query.ids:
        stmt = stmt.where(Admin.id.in_(query.ids))
    if query.usernames:
        stmt = stmt.where(Admin.username.in_(query.usernames))
    if query.search:
        stmt = stmt.where(Admin.username.ilike(f"%{query.search}%"))

    if query.sort:
        stmt = stmt.order_by(*[_build_admin_simple_sort_clause(sort_option) for sort_option in query.sort])

    # Get count BEFORE pagination (always)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Apply pagination or safety limit
    if not query.all:
        if query.offset is not None:
            stmt = stmt.offset(query.offset)
        if query.limit is not None:
            stmt = stmt.limit(query.limit)
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
    await db.refresh(db_admin, attribute_names=["usage_logs"])
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
    Groups data by periods in the timezone of the start/end parameters.

    Args:
        db (AsyncSession): Database session for querying.
        admin_id (int | None): Admin ID to filter users by. If None, include all admins.
        start (datetime): Start of the period (with timezone).
        end (datetime): End of the period (with timezone).
        period (Period): Time period to group by ('minute', 'hour', 'day', 'month').
        node_id (Optional[int]): Filter results by specific node ID if provided.

    Returns:
        UserUsageStatsList: Aggregated usage data for each period.
    """
    # Build truncation expression with timezone support
    trunc_expr = _build_trunc_expression(db, period, NodeUserUsage.created_at, start=start)

    # Filter using UTC timestamps (DB stores naive UTC) from first complete bucket
    start_utc = get_complete_period_start_for_filter(start, period)
    end_utc = to_utc_for_filter(end)
    conditions = [
        NodeUserUsage.created_at >= start_utc,
        NodeUserUsage.created_at < end_utc,
    ]

    if admin_id is not None:
        conditions.append(User.admin_id == admin_id)

    if node_id is not None:
        conditions.append(NodeUserUsage.node_id == node_id)
    else:
        node_id = -1

    dialect = db.bind.dialect.name

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

    result = await db.execute(stmt)
    stats = {}
    for row in result.mappings():
        row_dict = dict(row)
        node_id_val = row_dict.pop("node_id", node_id)

        # Attach timezone info to period_start
        attach_timezone_to_period_start(row_dict, start.tzinfo, dialect)
        if node_id_val not in stats:
            stats[node_id_val] = []
        stats[node_id_val].append(UserUsageStat(**row_dict))

    return UserUsageStatsList(period=period, start=start, end=end, stats=stats)


async def update_owner_password(db: AsyncSession, owner: Admin, new_password: str) -> Admin:
    """Reset the owner's password. All DB work stays in the CRUD layer."""
    owner.hashed_password = await hash_password(new_password)
    owner.password_reset_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(owner)
    await load_admin_attrs(owner)
    return owner


async def get_owner(db: AsyncSession) -> Admin | None:
    """Return the owner admin (role_id=1), or None if not found."""
    return (await db.execute(select(Admin).where(Admin.role_id == 1))).scalar_one_or_none()


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


async def remove_admins(db: AsyncSession, admin_ids: list[int]) -> None:
    """
    Removes multiple admins from the database by ID.

    Args:
        db (AsyncSession): Database session.
        admin_ids (list[int]): List of admin IDs to remove.
    """
    if not admin_ids:
        return

    await db.execute(update(User).where(User.admin_id.in_(admin_ids)).values(admin_id=None))
    await db.execute(delete(AdminUsageLogs).where(AdminUsageLogs.admin_id.in_(admin_ids)))
    await db.execute(delete(Admin).where(Admin.id.in_(admin_ids)))
    await db.commit()

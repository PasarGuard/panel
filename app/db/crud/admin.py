from datetime import datetime, timezone

from sqlalchemy import and_, case, delete, func, not_, select, update
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.exc import DetachedInstanceError

from app.db.crud.general import (
    _build_trunc_expression,
    attach_timezone_to_period_start,
    get_complete_period_start_for_filter,
    to_utc_for_filter,
)
from app.db.models import Admin, AdminNotificationReminder, AdminRole, AdminUsageLogs, NodeUserUsage, ReminderType, User
from app.models.admin import (
    AdminCreate,
    AdminDetails,
    AdminListQuery,
    AdminModify,
    AdminRoleData,
    AdminSimpleListQuery,
    AdminSimpleSortField,
    AdminSimpleSortOption,
    AdminSortField,
    AdminSortOption,
    AdminStatus,
    hash_password,
)
from app.models.admin_role import RoleLimits
from app.models.stats import Period, UserUsageStat, UserUsageStatsList
from app.utils.logger import get_logger

logger = get_logger("admin-crud")


async def _load_admin_non_role_attrs(
    admin: Admin,
    *,
    load_users: bool = True,
    load_usage_logs: bool = True,
):
    try:
        if load_users:
            await admin.awaitable_attrs.users
        if load_usage_logs:
            await admin.awaitable_attrs.usage_logs
    except AttributeError:
        pass


def build_admin_details(
    db_admin: Admin,
    *,
    total_users: int | None = None,
    reseted_usage: int | None = None,
    include_loaded_metrics: bool = False,
) -> AdminDetails:
    used_traffic = int(db_admin.used_traffic or 0)
    if include_loaded_metrics:
        if total_users is None:
            total_users = db_admin.total_users
        if reseted_usage is None:
            reseted_usage = db_admin.reseted_usage

    role = None
    if "role" in getattr(db_admin, "__dict__", {}):
        try:
            role = AdminRoleData.model_validate(db_admin.role) if db_admin.role is not None else None
        except DetachedInstanceError, InvalidRequestError:
            role = None

    return AdminDetails(
        id=db_admin.id,
        username=db_admin.username,
        total_users=int(total_users or 0),
        used_traffic=used_traffic,
        data_limit=db_admin.data_limit,
        status=db_admin.status,
        telegram_id=db_admin.telegram_id,
        discord_webhook=db_admin.discord_webhook,
        sub_domain=db_admin.sub_domain,
        profile_title=db_admin.profile_title,
        support_url=db_admin.support_url,
        custom_variables=db_admin.custom_variables or [],
        note=db_admin.note,
        notification_enable=db_admin.notification_enable,
        sub_template=db_admin.sub_template,
        lifetime_used_traffic=None if reseted_usage is None else int(reseted_usage or 0) + used_traffic,
        role=role,
        permission_overrides=RoleLimits.model_validate(db_admin.permission_overrides)
        if db_admin.permission_overrides
        else None,
    )


async def load_admin_attrs(
    admin: Admin,
    load_users: bool = True,
    load_usage_logs: bool = True,
    load_role: bool = True,
):
    try:
        if load_users:
            await admin.awaitable_attrs.users
        if load_usage_logs:
            await admin.awaitable_attrs.usage_logs
        if load_role:
            await admin.awaitable_attrs.role
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
    load_role: bool = True,
) -> Admin:
    stmt = select(Admin).where(Admin.username == username)
    if load_role:
        stmt = stmt.options(selectinload(Admin.role))
    admin = (await db.execute(stmt)).unique().scalar_one_or_none()
    if admin:
        await _load_admin_non_role_attrs(admin, load_users=load_users, load_usage_logs=load_usage_logs)
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
    if modified_admin.status is not None:
        if modified_admin.status != db_admin.status:
            db_admin.status = modified_admin.status
            db_admin.last_status_change = datetime.now(timezone.utc)
    if modified_admin.data_limit is not None:
        db_admin.data_limit = modified_admin.data_limit if modified_admin.data_limit > 0 else None
        # Recompute limited/active based on new data_limit — never touch disabled
        if db_admin.status != AdminStatus.disabled:
            should_be_limited = (
                db_admin.data_limit is not None
                and db_admin.data_limit > 0
                and db_admin.used_traffic >= db_admin.data_limit
            )
            new_status = AdminStatus.limited if should_be_limited else AdminStatus.active
            if db_admin.status != new_status:
                db_admin.status = new_status
                db_admin.last_status_change = datetime.now(timezone.utc)
    if modified_admin.password is not None:
        db_admin.hashed_password = await hash_password(modified_admin.password)
        db_admin.password_reset_at = datetime.now(timezone.utc)
    if modified_admin.role_id is not None:
        db_admin.role_id = modified_admin.role_id
    if modified_admin.permission_overrides is not None:
        db_admin.permission_overrides = modified_admin.permission_overrides.model_dump()
    if modified_admin.telegram_id is not None:
        db_admin.telegram_id = modified_admin.telegram_id
    if modified_admin.discord_webhook is not None:
        db_admin.discord_webhook = modified_admin.discord_webhook
    if modified_admin.sub_template is not None:
        db_admin.sub_template = modified_admin.sub_template
    if modified_admin.sub_domain is not None:
        db_admin.sub_domain = modified_admin.sub_domain
    if modified_admin.support_url is not None:
        db_admin.support_url = modified_admin.support_url
    if modified_admin.profile_title is not None:
        db_admin.profile_title = modified_admin.profile_title
    if modified_admin.custom_variables is not None:
        db_admin.custom_variables = [variable.model_dump() for variable in modified_admin.custom_variables]
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
    load_role: bool = True,
) -> Admin:
    stmt = select(Admin).where(Admin.id == id)
    if load_role:
        stmt = stmt.options(selectinload(Admin.role))
    admin = (await db.execute(stmt)).unique().scalar_one_or_none()
    if admin:
        await _load_admin_non_role_attrs(admin, load_users=load_users, load_usage_logs=load_usage_logs)
    return admin


async def get_admin_by_telegram_id(
    db: AsyncSession,
    telegram_id: int,
    *,
    load_users: bool = True,
    load_usage_logs: bool = True,
    load_role: bool = True,
) -> Admin:
    stmt = select(Admin).where(Admin.telegram_id == telegram_id).order_by(Admin.id.asc()).limit(2)
    if load_role:
        stmt = stmt.options(selectinload(Admin.role))
    admins = (await db.execute(stmt)).scalars().all()
    if len(admins) > 1:
        logger.error(
            "Duplicate telegram_id found for admins; using earliest record",
            extra={"telegram_id": telegram_id, "admin_ids": [admin.id for admin in admins]},
        )
    admin = admins[0] if admins else None
    if admin:
        await _load_admin_non_role_attrs(admin, load_users=load_users, load_usage_logs=load_usage_logs)
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


async def get_admins(
    db: AsyncSession,
    query: AdminListQuery,
    return_with_count: bool = False,
    compact: bool = False,
    include_owner: bool = True,
    load_role: bool = True,
) -> list[Admin] | tuple[list[Admin], int, int, int, int]:
    """
    Retrieves a list of admins with optional filters and pagination.

    Args:
        db (AsyncSession): Database session.
        query: Structured admin list query.
        return_with_count (bool): If True, returns tuple with (admins, total, active, disabled, limited).

    Returns:
        List[Admin] | tuple[list[Admin], int, int, int, int]:
            A list of admin objects or tuple with counts (total, active, disabled, limited).
    """
    params = query
    total = None
    active = None
    disabled = None

    if return_with_count:
        counts_stmt = select(
            func.count(Admin.id).label("total"),
            func.sum(case((Admin.status == AdminStatus.active, 1), else_=0)).label("active"),
            func.sum(case((Admin.status == AdminStatus.disabled, 1), else_=0)).label("disabled"),
            func.sum(case((Admin.status == AdminStatus.limited, 1), else_=0)).label("limited"),
        )
        if params.ids:
            counts_stmt = counts_stmt.where(Admin.id.in_(params.ids))
        if params.usernames:
            counts_stmt = counts_stmt.where(Admin.username.in_(params.usernames))
        if params.username:
            counts_stmt = counts_stmt.where(Admin.username.ilike(f"%{params.username}%"))
        if not include_owner:
            counts_stmt = counts_stmt.where(Admin.role.has(AdminRole.is_owner.is_(False)))

        result = await db.execute(counts_stmt)
        row = result.one()
        total = row.total or 0
        active = row.active or 0
        disabled = row.disabled or 0
        limited = row.limited or 0

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

    if load_role:
        stmt = stmt.options(selectinload(Admin.role))

    # Apply filters consistently
    if params.ids:
        stmt = stmt.where(Admin.id.in_(params.ids))
    if params.usernames:
        stmt = stmt.where(Admin.username.in_(params.usernames))
    if params.username:
        stmt = stmt.where(Admin.username.ilike(f"%{params.username}%"))
    if not include_owner:
        stmt = stmt.where(Admin.role.has(AdminRole.is_owner.is_(False)))

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
            admins.append(build_admin_details(admin, total_users=total_users, reseted_usage=reseted_usage))
    else:
        admins = list((await db.execute(stmt)).scalars().all())
        for admin in admins:
            await load_admin_attrs(admin, load_role=load_role)

    if return_with_count:
        return admins, total, active, disabled, limited
    return admins


async def get_admins_simple(
    db: AsyncSession,
    query: AdminSimpleListQuery,
    include_owner: bool = True,
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
    if not include_owner:
        stmt = stmt.where(Admin.role.has(AdminRole.is_owner.is_(False)))

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
        stmt = stmt.limit(10000)

    # Execute and return
    result = await db.execute(stmt)
    rows = result.all()

    return rows, total


async def get_active_admins_with_data_limit(
    db: AsyncSession,
    *,
    threshold: int | None = None,
    admin_ids: list[int] | None = None,
) -> list[Admin]:
    """Return active admins with a finite data_limit, used by warning-threshold checks."""
    stmt = select(Admin).where(
        Admin.status == AdminStatus.active,
        Admin.data_limit.isnot(None),
        Admin.data_limit > 0,
    )

    if threshold is not None:
        stmt = stmt.where(Admin.used_traffic >= (Admin.data_limit * (threshold / 100)))

    if admin_ids is not None:
        if not admin_ids:
            return []
        stmt = stmt.where(Admin.id.in_(admin_ids))

    return list((await db.execute(stmt)).scalars().all())


async def get_usage_percentage_reached_admins(
    db: AsyncSession,
    percentage: int,
    admin_ids: list[int] | None = None,
) -> list[Admin]:
    """Get active admins who reached a usage threshold and have no reminder for that threshold."""
    if admin_ids is not None and not admin_ids:
        return []

    existing_reminder_subq = (
        select(AdminNotificationReminder.admin_id)
        .where(
            AdminNotificationReminder.admin_id == Admin.id,
            AdminNotificationReminder.type == ReminderType.data_usage,
            AdminNotificationReminder.threshold == percentage,
        )
        .exists()
    )

    stmt = (
        select(Admin)
        .options(selectinload(Admin.role))
        .where(
            Admin.status == AdminStatus.active,
            Admin.data_limit.isnot(None),
            Admin.data_limit > 0,
            (Admin.used_traffic * 100) >= (Admin.data_limit * percentage),
            not_(existing_reminder_subq),
        )
    )

    if admin_ids is not None:
        stmt = stmt.where(Admin.id.in_(admin_ids))

    return list((await db.execute(stmt)).scalars().all())


async def bulk_create_admin_notification_reminders(db: AsyncSession, reminder_data: list[dict]) -> None:
    """Bulk-insert admin reminder rows after successful sends."""
    if not reminder_data:
        return

    db.add_all([AdminNotificationReminder(**data) for data in reminder_data])
    await db.commit()


async def create_admin_notification_reminder_if_absent(
    db: AsyncSession,
    admin_id: int,
    reminder_type: ReminderType,
    threshold: int | None = None,
) -> bool:
    """Create an admin reminder row and return whether this call claimed it."""
    existing_reminder_id = await db.scalar(
        select(AdminNotificationReminder.id)
        .where(
            AdminNotificationReminder.admin_id == admin_id,
            AdminNotificationReminder.type == reminder_type,
            AdminNotificationReminder.threshold == threshold,
        )
        .limit(1)
    )
    if existing_reminder_id is not None:
        return False

    db.add(AdminNotificationReminder(admin_id=admin_id, type=reminder_type, threshold=threshold))
    await db.commit()
    return True


async def delete_admin_notification_reminders(
    db: AsyncSession,
    admin_id: int,
    reminder_type: ReminderType,
) -> None:
    """Delete persisted admin reminders for a specific type (used when re-arming thresholds)."""
    await db.execute(
        delete(AdminNotificationReminder).where(
            AdminNotificationReminder.admin_id == admin_id,
            AdminNotificationReminder.type == reminder_type,
        )
    )


async def get_active_to_limited_admins(db: AsyncSession) -> list[Admin]:
    """Return ALL active admins that have exceeded their data_limit (for status flip)."""
    stmt = (
        select(Admin)
        .options(selectinload(Admin.role))
        .where(
            Admin.status == AdminStatus.active,
            Admin.data_limit.isnot(None),
            Admin.data_limit > 0,
            Admin.used_traffic >= Admin.data_limit,
        )
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_limited_admin_ids_with_user_sync(db: AsyncSession) -> set[int]:
    """Return IDs of currently limited admins that have disconnect_users_when_limited=True.
    Used to exclude their users from node sync — avoids loading relationships."""
    stmt = (
        select(Admin.id)
        .join(AdminRole, Admin.role_id == AdminRole.id)
        .where(
            Admin.status == AdminStatus.limited,
            AdminRole.disconnect_users_when_limited.is_(True),
        )
    )
    result = await db.execute(stmt)
    return set(result.scalars().all())


async def update_admin_status(db: AsyncSession, db_admin: Admin, new_status: AdminStatus) -> Admin:
    """
    Update an admin's status and record the transition time.

    Args:
        db: Database session.
        db_admin: The admin to update.
        new_status: The new status to set.

    Returns:
        Admin: The updated admin object.
    """
    db_admin.status = new_status
    db_admin.last_status_change = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(db_admin)
    await load_admin_attrs(db_admin)
    return db_admin


async def reset_admin_usage(db: AsyncSession, db_admin: Admin) -> Admin:
    """
    Retrieves an admin's usage by their username.
    Args:
        db (AsyncSession): Database session.
        db_admin (Admin): The admin object to be updated.
    Returns:
        Admin: The updated admin.
    """
    await delete_admin_notification_reminders(db, db_admin.id, ReminderType.data_usage)

    if db_admin.used_traffic == 0:
        await db.commit()
        return db_admin

    usage_log = AdminUsageLogs(admin_id=db_admin.id, used_traffic_at_reset=db_admin.used_traffic)
    db.add(usage_log)
    db_admin.used_traffic = 0

    # After reset, used_traffic = 0 so the admin is no longer limited
    if db_admin.status == AdminStatus.limited:
        db_admin.status = AdminStatus.active
        db_admin.last_status_change = datetime.now(timezone.utc)

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


async def owner_exists(db: AsyncSession) -> bool:
    """Return whether at least one owner admin exists."""
    return (await db.execute(select(func.count(Admin.id)).where(Admin.role_id == 1))).scalar_one() > 0


class OwnerUpgradeError(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


async def upgrade_admin_to_owner(db: AsyncSession, username: str) -> Admin:
    """Promote an existing admin to owner."""
    target_admin = (await db.execute(select(Admin).where(Admin.username == username))).scalar_one_or_none()
    if target_admin is None:
        raise OwnerUpgradeError("admin not found")

    target_admin.role_id = 1
    await db.commit()
    await db.refresh(target_admin)
    await load_admin_attrs(target_admin)
    return target_admin


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

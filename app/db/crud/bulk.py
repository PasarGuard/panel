from collections.abc import Iterator, Sequence
from datetime import UTC, datetime as dt, timedelta
from typing import Literal

from sqlalchemy import and_, case, cast, delete, func, insert, or_, select, text, true, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.db.models import (
    Admin,
    Group,
    NextPlan,
    NodeUserUsage,
    User,
    UserStatus,
    UserUsageResetLogs,
    users_groups_association,
)
from app.models.group import BulkGroup
from app.models.user import BulkUser, BulkUserExpire, BulkUserFilter, BulkUsersProxy

from .general import get_datetime_add_expression
from .user import _build_user_select_stmt, _explicit_ids


class BulkUserUpdateConflict(ValueError):
    """A checked target changed before the conditional bulk update completed."""


def expire_anchor_base(bulk_model: BulkUser, current_time: dt) -> dt | None:
    """Absolute instant that replaces each user's expire date, or None when the expire date itself is the base."""
    if not isinstance(bulk_model, BulkUserExpire) or bulk_model.anchor == "expire":
        return None
    return current_time if bulk_model.anchor == "now" else bulk_model.anchor


def _bulk_user_target_filter(
    bulk_model: BulkUser, field: Literal["expire", "data_limit"], target_ids: Sequence[int] | None = None
):
    """Select exactly the finite values that the requested bulk adjustment can change."""
    selection = _create_final_filter(bulk_model) if target_ids is None else _explicit_ids(User.id, target_ids)
    if field == "expire":
        if isinstance(bulk_model, BulkUserExpire) and bulk_model.anchor != "expire":
            return and_(selection, User.status != UserStatus.on_hold)
        return and_(selection, User.expire.isnot(None))
    conditions = [selection, User.data_limit.isnot(None), User.data_limit != 0]
    if bulk_model.amount < 0:
        conditions.append(User.data_limit > -bulk_model.amount)
    return and_(*conditions)


async def get_bulk_user_limit_targets(
    db: AsyncSession, bulk_model: BulkUser, field: Literal["expire", "data_limit"], *, lock: bool = True
):
    """Read only IDs and values for limit validation, locking targets before a write."""
    column = User.expire if field == "expire" else User.data_limit
    stmt = select(User.id, column).where(_bulk_user_target_filter(bulk_model, field))
    if lock:
        stmt = stmt.with_for_update(of=User)
    result = await db.execute(stmt)
    return result.all()


def _bulk_final_value_bounds(value, minimum, maximum):
    """Constrain final values again in the write to protect against concurrent changes."""
    conditions = []
    if minimum is not None:
        conditions.append(value >= minimum)
    if maximum is not None:
        conditions.append(value <= maximum)
    return and_(*conditions) if conditions else true()


async def _check_bulk_update_count(db: AsyncSession, result, target_ids: Sequence[int] | None) -> None:
    """Roll back the whole batch if any validated target no longer meets the write guards."""
    if target_ids is not None and result.rowcount != len(target_ids):
        await db.rollback()
        raise BulkUserUpdateConflict("Selected users changed during the bulk update; retry the request")


def _bulk_user_reload_stmt(*, load_group_inbounds: bool = False) -> Select:
    """Reload bulk results with batched relationships and aggregate lifetime usage."""
    # Bulk SQL bypasses relationship collections; replace any cached memberships.
    return _build_user_select_stmt(
        load_admin_role=True,
        load_usage_logs=False,
        load_group_inbounds=load_group_inbounds,
        load_lifetime_used_traffic=True,
    ).execution_options(populate_existing=True)


def _chunked(ids: Sequence[int]) -> Iterator[Sequence[int]]:
    """Yield ids 5k at a time. asyncpg rejects statements with more than 32767 bind parameters, and these
    statements bind the group ids next to the user ids, so stay well below 10k."""
    for start in range(0, len(ids), 5_000):
        yield ids[start : start + 5_000]


async def _reload_group_users(db: AsyncSession, user_ids: Sequence[int]) -> list[User]:
    """Reload users for a node sync after a bulk change, with their groups' inbounds preloaded."""
    users: list[User] = []
    for chunk in _chunked(user_ids):
        result = await db.execute(_bulk_user_reload_stmt(load_group_inbounds=True).where(User.id.in_(chunk)))
        users += result.scalars().all()
    return users


async def reset_all_users_data_usage(
    db: AsyncSession,
    admin: Admin | None = None,
    *,
    clean_chart_data: bool = False,
):
    """
    Efficiently resets data usage for all users, or users under a specific admin if provided.

    This function performs a high-performance reset by executing bulk database operations
    rather than iterating over ORM-mapped objects, improving speed and reducing memory usage.

    Operations performed:
        - Sets `used_traffic` to 0 for all target users.
        - Sets `status` to `active` for all users, unless filtered by admin.
        - Deletes all related `UserUsageResetLogs` and `NextPlan` entries.
        - Deletes `NodeUserUsage` chart rows when `clean_chart_data` is enabled.

    Args:
        db (AsyncSession): The SQLAlchemy async session used for database operations.
        admin (Optional[Admin]): If provided, only resets data usage for users belonging to this admin.
                                 If None, resets usage for all users in the system.

    Notes:
        - All operations are executed in bulk for performance.
        - This function assumes proper foreign key constraints and cascading rules are in place.
        - The function commits changes at the end of the operation.
    """
    user_ids = select(User.id).where(User.admin_id == admin.id) if admin else select(User.id)

    reset_status = case((User.status == UserStatus.limited, UserStatus.active), else_=User.status)
    reset_users = update(User).values(used_traffic=0, status=reset_status)
    if admin:
        reset_users = reset_users.where(User.admin_id == admin.id)
    await db.execute(reset_users)

    await db.execute(delete(UserUsageResetLogs).where(UserUsageResetLogs.user_id.in_(user_ids)))
    if clean_chart_data:
        await db.execute(delete(NodeUserUsage).where(NodeUserUsage.user_id.in_(user_ids)))
    await db.execute(delete(NextPlan).where(NextPlan.user_id.in_(user_ids)))

    await db.commit()


async def disable_all_active_users(db: AsyncSession, admin: Admin | None = None):
    """
    Disable all active users or users under a specific admin.

    Args:
        db (AsyncSession): Database session.
        admin (Optional[Admin]): Admin to filter users by, if any.
    """
    query = update(User).where(User.status.in_((UserStatus.active, UserStatus.on_hold)))
    if admin:
        query = query.filter(User.admin_id == admin.id)

    await db.execute(
        query.values(
            {User.status: UserStatus.disabled, User.last_status_change: dt.now(UTC)},
        )
    )

    await db.commit()
    await db.refresh(admin)


async def activate_all_disabled_users(db: AsyncSession, admin: Admin | None = None):
    """
    Activate all disabled users or users under a specific admin.

    Args:
        db (AsyncSession): Database session.
        admin (Optional[Admin]): Admin to filter users by, if any.
    """
    query_for_active_users = update(User).where(User.status == UserStatus.disabled)
    query_for_on_hold_users = update(User).where(
        and_(
            User.status == UserStatus.disabled,
            User.expire.is_(None),
            User.on_hold_expire_duration.isnot(None),
        )
    )
    if admin:
        query_for_active_users = query_for_active_users.where(User.admin_id == admin.id)
        query_for_on_hold_users = query_for_on_hold_users.where(User.admin_id == admin.id)

    await db.execute(
        query_for_on_hold_users.values(
            {User.status: UserStatus.on_hold, User.last_status_change: dt.now(UTC)},
        )
    )
    await db.execute(
        query_for_active_users.values(
            {User.status: UserStatus.active, User.last_status_change: dt.now(UTC)},
        )
    )

    await db.commit()
    await db.refresh(admin)


def _create_group_filter(bulk_model: BulkGroup):
    """Create a comprehensive SQLAlchemy filter condition from a BulkGroup model."""
    other_conditions = []
    if bulk_model.admins:
        other_conditions.append(User.admin_id.in_(bulk_model.admins))
    if bulk_model.has_group_ids:
        other_conditions.append(User.groups.any(Group.id.in_(bulk_model.has_group_ids)))
    if bulk_model.has_no_group:
        other_conditions.append(~User.groups.any())

    user_ids = bulk_model.users or []

    filter_conditions = []
    if user_ids:
        filter_conditions.append(_explicit_ids(User.id, user_ids))
    if other_conditions:
        filter_conditions.append(and_(*other_conditions))

    if len(filter_conditions) > 1:
        return or_(*filter_conditions)
    elif filter_conditions:
        return filter_conditions[0]
    else:
        return True


async def add_groups_to_users(db: AsyncSession, bulk_model: BulkGroup) -> tuple[list, int] | tuple[list[User], int]:
    """
    Bulk add groups to users and return list of affected User objects.
    """
    final_filter = _create_group_filter(bulk_model)
    count_effctive_users = await count_bulk_group_scope(db, bulk_model)

    # Users in scope that miss at least one of the requested groups (snapshot taken before any insert).
    memberships = (
        select(func.count(users_groups_association.c.groups_id))
        .where(
            users_groups_association.c.user_id == User.id,
            users_groups_association.c.groups_id.in_(bulk_model.group_ids),
        )
        .scalar_subquery()
    )
    missing_group = memberships < len(bulk_model.group_ids)
    result = await db.execute(select(User.id).where(final_filter, missing_group))
    affected_user_ids = result.scalars().all()

    if not affected_user_ids:
        return [], count_effctive_users

    # Insert the missing (user, group) pairs server-side, one statement per chunk of users.
    for user_ids in _chunked(affected_user_ids):
        missing_pairs = (
            select(User.id, Group.id)
            .select_from(User)
            .join(Group, true())
            .where(
                User.id.in_(user_ids),
                Group.id.in_(bulk_model.group_ids),
                ~select(users_groups_association.c.user_id)
                .where(
                    users_groups_association.c.user_id == User.id,
                    users_groups_association.c.groups_id == Group.id,
                )
                .exists(),
            )
        )
        await db.execute(
            insert(users_groups_association).from_select(["user_id", "groups_id"], missing_pairs),
        )
    await db.commit()

    # Return users that actually had groups added
    return await _reload_group_users(db, affected_user_ids), count_effctive_users


async def remove_groups_from_users(
    db: AsyncSession, bulk_model: BulkGroup
) -> tuple[list, int] | tuple[list[User], int]:
    """
    Bulk remove groups from users and return list of affected User objects.
    """
    final_filter = _create_group_filter(bulk_model)
    count_effctive_users = await count_bulk_group_scope(db, bulk_model)

    # Identify affected users (those in scope who actually have the groups to be removed)
    has_group = (
        select(users_groups_association.c.user_id)
        .where(
            users_groups_association.c.user_id == User.id,
            users_groups_association.c.groups_id.in_(bulk_model.group_ids),
        )
        .exists()
    )
    result = await db.execute(select(User.id).where(final_filter, has_group))
    affected_user_ids = result.scalars().all()

    if not affected_user_ids:
        return [], count_effctive_users

    for user_ids in _chunked(affected_user_ids):
        await db.execute(
            delete(users_groups_association).where(
                users_groups_association.c.user_id.in_(user_ids),
                users_groups_association.c.groups_id.in_(bulk_model.group_ids),
            )
        )
    await db.commit()
    return await _reload_group_users(db, affected_user_ids), count_effctive_users


async def count_bulk_expire_targets(db: AsyncSession, bulk_model: BulkUser) -> int:
    """Count finite expirations eligible for the requested adjustment."""
    return (
        await db.execute(select(func.count(User.id)).where(_bulk_user_target_filter(bulk_model, "expire")))
    ).scalar_one_or_none() or 0


async def count_bulk_datalimit_targets(db: AsyncSession, bulk_model: BulkUser) -> int:
    """Count finite quotas eligible for the requested adjustment, including subtraction guards."""
    return (
        await db.execute(select(func.count(User.id)).where(_bulk_user_target_filter(bulk_model, "data_limit")))
    ).scalar_one_or_none() or 0


async def count_bulk_proxy_targets(db: AsyncSession, bulk_model: BulkUsersProxy) -> int:
    final_filter = _create_final_filter(bulk_model)
    return (await db.execute(select(func.count(User.id)).where(final_filter))).scalar_one_or_none() or 0


async def count_bulk_group_scope(db: AsyncSession, bulk_model: BulkGroup) -> int:
    final_filter = _create_group_filter(bulk_model)
    return (await db.execute(select(func.count(User.id)).where(final_filter))).scalar_one_or_none() or 0


def _create_final_filter(bulk_model: BulkUserFilter):
    """Create a comprehensive SQLAlchemy filter condition from a bulk model."""
    other_conditions = []
    if bulk_model.status:
        other_conditions.append(User.status.in_([i.value for i in bulk_model.status]))
    if bulk_model.expire_after:
        other_conditions.append(User.expire >= bulk_model.expire_after)
    if bulk_model.expire_before:
        other_conditions.append(User.expire <= bulk_model.expire_before)
    if bulk_model.admins:
        other_conditions.append(User.admin_id.in_([i for i in bulk_model.admins]))
    if bulk_model.group_ids:
        other_conditions.append(User.groups.any(Group.id.in_(bulk_model.group_ids)))

    user_ids = bulk_model.users or []

    filter_conditions = []
    if user_ids:
        filter_conditions.append(_explicit_ids(User.id, user_ids))
    if other_conditions:
        filter_conditions.append(and_(*other_conditions))

    if len(filter_conditions) > 1:
        return or_(*filter_conditions)
    elif filter_conditions:
        return filter_conditions[0]
    else:
        return True


async def update_users_expire(
    db: AsyncSession,
    bulk_model: BulkUserExpire,
    *,
    target_ids: Sequence[int] | None = None,
    minimum: dt | None = None,
    maximum: dt | None = None,
) -> tuple[list[User], int] | tuple[list, int]:
    """
    Bulk update user expiration dates and return list of User objects where status changed.
    """
    final_filter = _bulk_user_target_filter(bulk_model, "expire", target_ids)

    count_effctive_users = (await db.execute(select(func.count(User.id)).where(final_filter))).scalar_one_or_none() or 0
    current_time = dt.now(UTC)
    anchor_base = expire_anchor_base(bulk_model, current_time)
    if anchor_base is None:
        new_expire = get_datetime_add_expression(db, User.expire, bulk_model.amount)
    else:
        new_expire = anchor_base + timedelta(seconds=bulk_model.amount)

    # First, get the users that will have status changes BEFORE updating
    status_change_conditions = or_(
        and_(new_expire <= current_time, User.status == UserStatus.active),
        and_(new_expire > current_time, User.status == UserStatus.expired),
    )

    # Get IDs of users whose status will change
    result = await db.execute(select(User.id).where(and_(final_filter, status_change_conditions)))
    status_changed_user_ids = [row[0] for row in result.fetchall()]

    # Perform the update
    status_cases = [
        (and_(new_expire <= current_time, User.status == UserStatus.active), UserStatus.expired),
        (and_(new_expire > current_time, User.status == UserStatus.expired), UserStatus.active),
    ]

    result = await db.execute(
        update(User)
        .where(final_filter, _bulk_final_value_bounds(new_expire, minimum, maximum))
        .values(expire=new_expire, status=case(*status_cases, else_=User.status))
    )
    await _check_bulk_update_count(db, result, target_ids)
    await db.commit()

    # Return the users whose status changed
    if status_changed_user_ids:
        users = await _reload_group_users(db, status_changed_user_ids)
        return users, count_effctive_users
    return [], count_effctive_users


async def update_users_datalimit(
    db: AsyncSession,
    bulk_model: BulkUser,
    *,
    target_ids: Sequence[int] | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> tuple[list[User], int] | tuple[list, int]:
    """
    Bulk update user data limits and return list of User objects where status changed.
    """
    final_filter = _bulk_user_target_filter(bulk_model, "data_limit", target_ids)

    count_effctive_users = (await db.execute(select(func.count(User.id)).where(final_filter))).scalar_one_or_none() or 0

    # First, get the users that will have status changes BEFORE updating
    status_change_conditions = or_(
        and_(User.data_limit + bulk_model.amount <= User.used_traffic, User.status == UserStatus.active),
        and_(User.data_limit + bulk_model.amount > User.used_traffic, User.status == UserStatus.limited),
    )

    # Get IDs of users whose status will change
    result = await db.execute(select(User.id).where(and_(final_filter, status_change_conditions)))
    status_changed_user_ids = [row[0] for row in result.fetchall()]

    # Perform the update
    status_cases = [
        (
            and_(User.data_limit + bulk_model.amount <= User.used_traffic, User.status == UserStatus.active),
            UserStatus.limited,
        ),
        (
            and_(User.data_limit + bulk_model.amount > User.used_traffic, User.status == UserStatus.limited),
            UserStatus.active,
        ),
    ]

    result = await db.execute(
        update(User)
        .where(final_filter, _bulk_final_value_bounds(User.data_limit + bulk_model.amount, minimum, maximum))
        .values(data_limit=User.data_limit + bulk_model.amount, status=case(*status_cases, else_=User.status))
    )
    await _check_bulk_update_count(db, result, target_ids)
    await db.commit()

    # Return the users whose status changed
    if status_changed_user_ids:
        users = await _reload_group_users(db, status_changed_user_ids)
        return users, count_effctive_users
    return [], count_effctive_users


async def update_users_proxy_settings(
    db: AsyncSession, bulk_model: BulkUsersProxy
) -> tuple[list, int] | tuple[list[User], int]:
    """
    Bulk update the `proxy_settings` JSON field for users and return updated rows.
    """
    final_filter = _create_final_filter(bulk_model)

    # Capture target IDs without materializing users before the update.
    select_stmt = select(User.id).where(final_filter)
    result = await db.execute(select_stmt)
    updated_user_ids = result.scalars().all()
    count_effctive_users = len(updated_user_ids)

    if not updated_user_ids:
        return [], count_effctive_users

    dialect = db.bind.dialect.name

    # Prepare the update statement
    if dialect == "postgresql":
        proxy_settings_expr = cast(User.proxy_settings, JSONB)
        if bulk_model.method is not None:
            proxy_settings_expr = func.jsonb_set(
                proxy_settings_expr,
                text("'{shadowsocks,method}'"),
                cast(f"{bulk_model.method.value}", JSONB),
                True,
            )
    else:
        proxy_settings_expr = User.proxy_settings
        if bulk_model.method is not None:
            proxy_settings_expr = func.json_set(
                proxy_settings_expr, "$.shadowsocks.method", f"{bulk_model.method.value}"
            )

    # Perform the update
    update_stmt = update(User).where(final_filter).values(proxy_settings=proxy_settings_expr)
    await db.execute(update_stmt)
    await db.commit()

    # Reload the captured targets and preserve their original selection order.
    refreshed_users = await _reload_group_users(db, updated_user_ids)
    refreshed_users_map = {user.id: user for user in refreshed_users}
    ordered_refreshed_users = [refreshed_users_map[uid] for uid in updated_user_ids if uid in refreshed_users_map]

    return ordered_refreshed_users, count_effctive_users

from collections.abc import Iterable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CoordinationLock, Group

GROUP_POLICY_LOCK_NAME = "group_policy"


async def lock_group_policy_writes(db: AsyncSession) -> None:
    """Serialize group-inbound association discovery and mutation."""
    # A no-op UPDATE on the dedicated coordination row provides a portable
    # transaction-scoped mutex: a row lock on MySQL/PostgreSQL and a write
    # lock on SQLite, where SELECT FOR UPDATE is ignored.
    await db.execute(
        update(CoordinationLock)
        .where(CoordinationLock.name == GROUP_POLICY_LOCK_NAME)
        .values(name=CoordinationLock.name)
    )
    lock_exists = await db.scalar(select(CoordinationLock.name).where(CoordinationLock.name == GROUP_POLICY_LOCK_NAME))
    if lock_exists is None:
        raise RuntimeError("group policy coordination lock is not initialized")


async def lock_group_rows_for_sync(db: AsyncSession, group_ids: Iterable[int]) -> None:
    """Acquire portable write locks for group access-policy coordination."""
    for group_id in sorted(set(group_ids)):
        # A no-op UPDATE obtains a row lock on MySQL/PostgreSQL and a write
        # lock on SQLite, where SELECT FOR UPDATE is ignored.
        await db.execute(update(Group).where(Group.id == group_id).values(is_disabled=Group.is_disabled))

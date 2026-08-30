from collections.abc import Iterable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Group


async def lock_group_rows_for_sync(db: AsyncSession, group_ids: Iterable[int]) -> None:
    """Acquire portable write locks for group access-policy coordination."""
    for group_id in sorted(set(group_ids)):
        # A no-op UPDATE obtains a row lock on MySQL/PostgreSQL and a write
        # lock on SQLite, where SELECT FOR UPDATE is ignored.
        await db.execute(update(Group).where(Group.id == group_id).values(is_disabled=Group.is_disabled))

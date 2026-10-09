from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from app.db import AsyncSession
from app.db.models import NodeWarpProfile


async def claim_warp_registration(db: AsyncSession, node_id: int, *, retry: bool = False) -> str | None:
    profile = await db.get(NodeWarpProfile, node_id)
    if profile is None:
        try:
            async with db.begin_nested():
                db.add(NodeWarpProfile(node_id=node_id))
                await db.flush()
        except IntegrityError:
            # Another worker created the row; the conditional UPDATE below elects one owner.
            pass
    now = datetime.now(UTC)
    token = str(uuid4())
    stmt = update(NodeWarpProfile).where(
        NodeWarpProfile.node_id == node_id,
        NodeWarpProfile.settings.is_(None),
        or_(NodeWarpProfile.lease_expires_at.is_(None), NodeWarpProfile.lease_expires_at < now),
    )
    if not retry:
        stmt = stmt.where(
            or_(NodeWarpProfile.last_attempt_at.is_(None), NodeWarpProfile.last_attempt_at < now - timedelta(minutes=5))
        )
    result = await db.execute(
        stmt.values(
            lease_token=token,
            lease_expires_at=now + timedelta(seconds=60),
            last_attempt_at=now,
            last_error=None,
        ).execution_options(synchronize_session=False)
    )
    await db.commit()
    return token if result.rowcount == 1 else None


async def finish_warp_registration(
    db: AsyncSession, node_id: int, token: str, *, settings: dict | None = None, error: str | None = None
) -> None:
    values = {"lease_token": None, "lease_expires_at": None, "last_error": error}
    if settings is not None:
        values.update(settings=settings, registered_at=datetime.now(UTC))
    await db.execute(
        update(NodeWarpProfile)
        .where(NodeWarpProfile.node_id == node_id, NodeWarpProfile.lease_token == token)
        .values(**values)
    )
    await db.commit()


async def get_warp_settings(db: AsyncSession, node_id: int) -> dict | None:
    return await db.scalar(select(NodeWarpProfile.settings).where(NodeWarpProfile.node_id == node_id))


async def claim_warp_apply(db: AsyncSession, node_id: int, core_id: int, tag: str) -> str | None:
    now = datetime.now(UTC)
    token = str(uuid4())
    result = await db.execute(
        update(NodeWarpProfile)
        .where(
            NodeWarpProfile.node_id == node_id,
            NodeWarpProfile.settings.is_not(None),
            or_(NodeWarpProfile.lease_expires_at.is_(None), NodeWarpProfile.lease_expires_at < now),
            or_(
                NodeWarpProfile.applied_core_id.is_(None),
                NodeWarpProfile.applied_tag.is_(None),
                NodeWarpProfile.applied_core_id != core_id,
                NodeWarpProfile.applied_tag != tag,
            ),
        )
        .values(lease_token=token, lease_expires_at=now + timedelta(minutes=10), last_attempt_at=now)
    )
    await db.commit()
    return token if result.rowcount == 1 else None


async def release_warp_apply(db: AsyncSession, node_id: int, token: str) -> None:
    await db.execute(
        update(NodeWarpProfile)
        .where(NodeWarpProfile.node_id == node_id, NodeWarpProfile.lease_token == token)
        .values(lease_token=None, lease_expires_at=None)
    )
    await db.commit()


async def mark_warp_applied(db: AsyncSession, node_id: int, core_id: int, tag: str) -> None:
    await db.execute(
        update(NodeWarpProfile)
        .where(NodeWarpProfile.node_id == node_id, NodeWarpProfile.settings.is_not(None))
        .values(applied_core_id=core_id, applied_tag=tag, applied_at=datetime.now(UTC), last_error=None)
    )
    await db.commit()

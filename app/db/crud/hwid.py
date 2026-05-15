from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserHWID


async def get_user_hwids(db: AsyncSession, user_id: int) -> list[UserHWID]:
    """Retrieve all HWIDs registered for a specific user."""
    stmt = select(UserHWID).where(UserHWID.user_id == user_id).order_by(UserHWID.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_user_hwid_by_value(db: AsyncSession, user_id: int, hwid_str: str) -> UserHWID | None:
    """Retrieve a specific HWID for a user by its value."""
    stmt = select(UserHWID).where(UserHWID.user_id == user_id, UserHWID.hwid == hwid_str)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_user_hwid_count(db: AsyncSession, user_id: int) -> int:
    """Count the number of HWIDs registered for a user."""
    stmt = select(func.count(UserHWID.id)).where(UserHWID.user_id == user_id)
    return (await db.execute(stmt)).scalar_one()


async def register_user_hwid(
    db: AsyncSession,
    user_id: int,
    hwid: str,
    device_os: str | None = None,
    os_version: str | None = None,
    device_model: str | None = None,
) -> UserHWID:
    """Register a new HWID for a user."""
    new_hwid = UserHWID(
        user_id=user_id,
        hwid=hwid,
        device_os=device_os[:256] if device_os else None,
        os_version=os_version[:128] if os_version else None,
        device_model=device_model[:256] if device_model else None,
    )
    db.add(new_hwid)
    await db.commit()
    await db.refresh(new_hwid)
    return new_hwid


async def update_hwid_last_used(db: AsyncSession, hwid_obj: UserHWID) -> None:
    """Update the last_used_at timestamp for an HWID."""
    hwid_obj.last_used_at = datetime.now(timezone.utc)
    await db.commit()


async def delete_user_hwid(db: AsyncSession, user_id: int, hwid: str) -> bool:
    """Delete a specific HWID for a user by its value. Returns True if deleted."""
    stmt = delete(UserHWID).where(UserHWID.user_id == user_id, UserHWID.hwid == hwid)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0


async def reset_user_hwids(db: AsyncSession, user_id: int) -> int:
    """Delete all HWIDs for a user. Returns the number of HWIDs deleted."""
    stmt = delete(UserHWID).where(UserHWID.user_id == user_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount

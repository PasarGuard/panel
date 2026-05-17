import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TempKey

KEY_TTL_MINUTES = 5


async def create_temp_key(db: AsyncSession) -> TempKey:
    """Create a new single-use temp key valid for 5 minutes."""
    key = TempKey(
        key=str(uuid.uuid4()),
        action="pending",  # updated to the actual action when consumed
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=KEY_TTL_MINUTES),
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return key


async def get_temp_key(db: AsyncSession, key: str) -> TempKey | None:
    return (await db.execute(select(TempKey).where(TempKey.key == key))).scalar_one_or_none()


async def consume_temp_key(db: AsyncSession, key: TempKey, action: str, ip: str) -> None:
    """Mark key as used, recording what action it was consumed for."""
    key.action = action
    key.used_at = datetime.now(timezone.utc)
    key.used_by_ip = ip
    await db.commit()

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TempKey

KEY_TTL_MINUTES = 5
PENDING_ACTION = "pending"


class TempKeyConsumeError(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


async def create_temp_key(db: AsyncSession, action: str | None = None) -> TempKey:
    """Create a new single-use temp key valid for 5 minutes.

    Passing ``action`` binds the key to that action, so it cannot be consumed by any other one.
    Without an action the key stays unbound (``pending``) and accepts the first action presented.
    """
    key = TempKey(
        key=str(uuid.uuid4()),
        action=action if action is not None else PENDING_ACTION,  # bound action, or set when consumed
        expires_at=datetime.now(UTC) + timedelta(minutes=KEY_TTL_MINUTES),
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return key


async def get_temp_key(db: AsyncSession, key: str) -> TempKey | None:
    return (await db.execute(select(TempKey).where(TempKey.key == key))).scalar_one_or_none()


def _normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def consume_temp_key(db: AsyncSession, key: str, action: str, ip: str) -> None:
    """Atomically validate and mark a temp key as used.

    A key bound to an action can only be consumed by that same action; unbound (``pending``) keys
    accept any action, which keeps keys issued before actions were bound usable.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        update(TempKey)
        .where(
            TempKey.key == key,
            TempKey.used_at.is_(None),
            or_(TempKey.expires_at.is_(None), TempKey.expires_at > now),
            or_(TempKey.action == PENDING_ACTION, TempKey.action == action),
        )
        .values(action=action, used_at=now, used_by_ip=ip)
    )
    if result.rowcount == 1:
        await db.commit()
        return

    await db.rollback()
    temp_key = await get_temp_key(db, key)
    if temp_key is None:
        raise TempKeyConsumeError("invalid key")
    if temp_key.used_at is not None:
        raise TempKeyConsumeError("key already used")
    expires_at = _normalize_utc(temp_key.expires_at)
    if expires_at is not None and expires_at <= now:
        raise TempKeyConsumeError("key expired")
    # The key exists, is unused and unexpired, so the only remaining reason is that it is bound to
    # another action. Report it like an unknown key so the bound action is never disclosed.
    raise TempKeyConsumeError("invalid key")


async def mark_temp_key_used(db: AsyncSession, key: TempKey, action: str, ip: str) -> None:
    """Backward-compatible helper for code paths that already own a locked TempKey instance."""
    if key.action not in (PENDING_ACTION, action):
        raise TempKeyConsumeError("invalid key")
    key.action = action
    key.used_at = datetime.now(UTC)
    key.used_by_ip = ip
    await db.commit()

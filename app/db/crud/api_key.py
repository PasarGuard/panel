import uuid
from datetime import UTC, datetime as dt

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Admin, AdminStatus, APIKey, APIKeyStatus
from app.models.api_key import APIKeyCreate
from app.utils.crypto import api_key_lookup_id, hash_api_key, verify_api_key


async def create_api_key(
    db: AsyncSession,
    admin_id: int,
    model: APIKeyCreate,
) -> tuple[str, APIKey]:
    raw_uuid = str(uuid.uuid4())
    raw_key = f"pg_key_{raw_uuid}"
    db_key = APIKey(
        admin_id=admin_id,
        permissions={} if model.inherit_permissions else model.permissions.model_dump(exclude_none=True),
        inherit_permissions=model.inherit_permissions,
        name=model.name,
        note=model.note,
        key_hash=hash_api_key(raw_key),
        api_key_trimmed=f"pg_key_{raw_uuid[:3]}***{raw_uuid[-3:]}",
        expire_date=model.expire_date,
        max_requests=model.max_requests,
        delete_on_limit=model.delete_on_limit,
    )
    db.add(db_key)
    await db.flush()
    await db.refresh(db_key)
    return raw_key, db_key


async def get_api_key_by_raw_key(db: AsyncSession, raw_api_key: str) -> APIKey | None:
    lookup_id = api_key_lookup_id(raw_api_key)

    stmt = (
        select(APIKey)
        .where(
            APIKey.key_hash.startswith(f"v1${lookup_id}$"),
            APIKey.status != APIKeyStatus.disabled,
        )
        .options(selectinload(APIKey.admin).selectinload(Admin.role))
        .limit(1)
    )
    db_key = (await db.execute(stmt)).scalar_one_or_none()

    if db_key is None or not verify_api_key(raw_api_key, db_key.key_hash):
        return None
    # Reject if the owning admin is disabled
    if db_key.admin is not None and db_key.admin.status == AdminStatus.disabled:
        return None
    return db_key


async def get_api_key_by_id(db: AsyncSession, key_id: int) -> APIKey | None:
    stmt = select(APIKey).where(APIKey.id == key_id).options(selectinload(APIKey.admin))
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_api_keys_by_ids(db: AsyncSession, key_ids: list[int]) -> list[APIKey]:
    if not key_ids:
        return []

    stmt = select(APIKey).where(APIKey.id.in_(key_ids)).options(selectinload(APIKey.admin))
    return list((await db.execute(stmt)).scalars().all())


async def get_api_keys(
    db: AsyncSession,
    *,
    admin_id: int | None,
    offset: int,
    limit: int,
    key_id: int | None = None,
    name: str | None = None,
    status: APIKeyStatus | None = None,
) -> tuple[list[APIKey], int]:
    stmt = select(APIKey)
    if admin_id is not None:
        stmt = stmt.where(APIKey.admin_id == admin_id)
    if key_id is not None:
        stmt = stmt.where(APIKey.id == key_id)
    if name is not None:
        stmt = stmt.where(APIKey.name == name)
    if status is not None:
        if status == APIKeyStatus.active:
            # active = stored status is active AND not past expire_date
            stmt = stmt.where(APIKey.status == APIKeyStatus.active, ~APIKey.is_expired)
        else:
            # disabled = stored status is disabled (expire_date irrelevant)
            stmt = stmt.where(APIKey.status == APIKeyStatus.disabled)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

    stmt = stmt.order_by(APIKey.created_at.desc()).offset(offset).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return rows, total


async def increment_api_key_usage(db: AsyncSession, key_id: int) -> int | None:
    """Atomically increment request_count only when below max_requests.

    The UPDATE is conditioned on the key still being under its limit, so
    concurrent requests cannot race past max_requests.  The updated value is
    read back inside the same transaction (with FOR UPDATE) before committing,
    keeping the result consistent with what was actually written.

    Returns the new request_count, or None when no row was matched (key does
    not exist or was already at/above max_requests and the limit has been
    reached — callers should treat None as "key exhausted / missing").
    """
    # Conditional increment: only touch the row when it is still below the
    # limit (or has no limit at all).
    stmt = (
        update(APIKey)
        .where(
            APIKey.id == key_id,
            or_(
                APIKey.max_requests.is_(None),
                APIKey.request_count < APIKey.max_requests,
            ),
        )
        .values(request_count=APIKey.request_count + 1)
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        # Either the key doesn't exist or it has already hit its limit.
        await db.rollback()
        return None

    # Read the committed value back inside the same transaction so we see
    # exactly what we wrote (MySQL does not support UPDATE…RETURNING).
    new_count_row = await db.execute(
        select(APIKey.request_count).where(APIKey.id == key_id).with_for_update()
    )
    new_count = new_count_row.scalar_one()
    await db.commit()
    return new_count


async def delete_api_key(db: AsyncSession, db_key: APIKey) -> None:
    await db.delete(db_key)
    await db.flush()


async def revoke_api_key(db: AsyncSession, db_key: APIKey) -> tuple[str, APIKey]:
    raw_uuid = str(uuid.uuid4())
    raw_key = f"pg_key_{raw_uuid}"
    db_key.key_hash = hash_api_key(raw_key)
    db_key.api_key_trimmed = f"pg_key_{raw_uuid[:3]}***{raw_uuid[-3:]}"
    db_key.revoked_at = dt.now(UTC)
    db_key.status = APIKeyStatus.active
    db_key.request_count = 0
    await db.flush()
    await db.refresh(db_key)
    return raw_key, db_key


async def update_api_key(db: AsyncSession, db_key: APIKey, update_data: dict) -> APIKey:
    for key, value in update_data.items():
        setattr(db_key, key, value)
    await db.flush()
    await db.refresh(db_key)
    return db_key

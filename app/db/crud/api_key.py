import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Admin, APIKey
from app.models.api_key import APIKeyCreate
from app.utils.crypto import hash_api_key


async def create_api_key(
    db: AsyncSession,
    admin_id: int,
    model: APIKeyCreate,
) -> tuple[str, APIKey]:
    raw_key = str(uuid.uuid4())
    db_key = APIKey(
        admin_id=admin_id,
        role_id=model.role_id,
        name=model.name,
        note=model.note,
        key_hash=hash_api_key(model.raw_key),
        expire_date=model.expire_date,
    )
    db.add(db_key)
    await db.flush()
    await db.refresh(db_key)
    return raw_key, db_key


async def get_api_key_by_hash(db: AsyncSession, key_hash: str) -> APIKey | None:
    stmt = (
        select(APIKey)
        .where(APIKey.key_hash == key_hash)
        .options(selectinload(APIKey.admin).selectinload(Admin.role), selectinload(APIKey.role))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_api_key_by_id(db: AsyncSession, key_id: int) -> APIKey | None:
    stmt = select(APIKey).where(APIKey.id == key_id).options(selectinload(APIKey.admin), selectinload(APIKey.role))
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_api_keys(
    db: AsyncSession,
    *,
    admin_id: int | None,
    offset: int,
    limit: int,
    key_id: int | None = None,
    name: str | None = None,
) -> tuple[list[APIKey], int]:
    stmt = select(APIKey).options(selectinload(APIKey.role))
    if admin_id is not None:
        stmt = stmt.where(APIKey.admin_id == admin_id)
    if key_id is not None:
        stmt = stmt.where(APIKey.id == key_id)
    if name is not None:
        stmt = stmt.where(APIKey.name == name)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

    stmt = stmt.order_by(APIKey.created_at.desc()).offset(offset).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return rows, total


async def delete_api_key(db: AsyncSession, db_key: APIKey) -> None:
    await db.delete(db_key)
    await db.flush()

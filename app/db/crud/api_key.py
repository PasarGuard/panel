import hashlib
import uuid
from datetime import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Admin, APIKey


def hash_api_key(raw_api_key: str) -> str:
    return hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()


async def create_api_key(
    db: AsyncSession,
    *,
    admin_id: int,
    role_id: int,
    name: str,
    note: str | None,
    expire_date: dt | None,
) -> tuple[str, APIKey]:
    raw_key = str(uuid.uuid4())
    db_key = APIKey(
        admin_id=admin_id,
        role_id=role_id,
        name=name,
        note=note,
        key_hash=hash_api_key(raw_key),
        expire_date=expire_date,
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


async def get_api_key_by_id_for_admin(db: AsyncSession, *, key_id: int, admin_id: int | None = None) -> APIKey | None:
    stmt = select(APIKey).where(APIKey.id == key_id).options(selectinload(APIKey.admin), selectinload(APIKey.role))
    if admin_id is not None:
        stmt = stmt.where(APIKey.admin_id == admin_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_api_key_by_name(db: AsyncSession, *, admin_id: int, name: str) -> APIKey | None:
    stmt = select(APIKey).where(APIKey.admin_id == admin_id, APIKey.name == name)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_api_keys(db: AsyncSession, *, admin_id: int | None, offset: int, limit: int) -> tuple[list[APIKey], int]:
    stmt = select(APIKey).options(selectinload(APIKey.role))
    if admin_id is not None:
        stmt = stmt.where(APIKey.admin_id == admin_id)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

    stmt = stmt.order_by(APIKey.created_at.desc()).offset(offset).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return rows, total


async def delete_api_key(db: AsyncSession, db_key: APIKey) -> None:
    await db.delete(db_key)
    await db.flush()

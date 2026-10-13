from datetime import UTC, datetime
from typing import cast

from sqlalchemy import bindparam, delete, func, insert, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.schema import Table

from app.db.models import User, UserHWID


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
    *,
    limit: int | None = None,
) -> bool:
    """Commit an HWID insert/refresh, or return False if a new device exceeds the limit."""
    dialect = db.bind.dialect.name
    if limit is not None and limit > 0:
        # Subscription validation may have established a read snapshot already.
        # Start fresh so MySQL's REPEATABLE READ sees registrations committed
        # before this request acquires the parent lock.
        await db.commit()
        if dialect == "sqlite":
            # Acquire SQLite's write lock before reading the HWID set. A no-op
            # write serializes even separate workers without upgrading a snapshot.
            user_table = cast(Table, User.__table__)
            await db.execute(
                update(user_table).where(user_table.c.id == user_id).values(hwid_limit=user_table.c.hwid_limit)
            )
        else:
            # Lock the parent: locking HWID rows alone cannot protect an empty set.
            await db.execute(select(User.id).where(User.id == user_id).with_for_update())

        existing_stmt = select(UserHWID.id).where(UserHWID.user_id == user_id, UserHWID.hwid == hwid)
        existing_id = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing_id is None and await get_user_hwid_count(db, user_id) >= limit:
            await db.commit()  # Release the lock on rejected registrations too.
            return False

    now = datetime.now(UTC)
    params = {
        "user_id": user_id,
        "hwid": hwid,
        "device_os": device_os[:256] if device_os else None,
        "os_version": os_version[:128] if os_version else None,
        "device_model": device_model[:256] if device_model else None,
        "created_at": now,
        "last_used_at": now,
    }
    table = cast(Table, UserHWID.__table__)

    if dialect == "postgresql":
        stmt = pg_insert(table).values(
            user_id=bindparam("user_id"),
            hwid=bindparam("hwid"),
            device_os=bindparam("device_os"),
            os_version=bindparam("os_version"),
            device_model=bindparam("device_model"),
            created_at=bindparam("created_at"),
            last_used_at=bindparam("last_used_at"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "hwid"],
            set_={"last_used_at": bindparam("last_used_at")},
        )
        await db.execute(stmt, [params])
    elif dialect == "mysql":
        stmt = mysql_insert(table).values(
            user_id=bindparam("user_id"),
            hwid=bindparam("hwid"),
            device_os=bindparam("device_os"),
            os_version=bindparam("os_version"),
            device_model=bindparam("device_model"),
            created_at=bindparam("created_at"),
            last_used_at=bindparam("last_used_at"),
        )
        stmt = stmt.on_duplicate_key_update(last_used_at=stmt.inserted.last_used_at)
        await db.execute(stmt, [params])
    else:  # SQLite
        insert_stmt = (
            insert(table)
            .values(
                user_id=bindparam("user_id"),
                hwid=bindparam("hwid"),
                device_os=bindparam("device_os"),
                os_version=bindparam("os_version"),
                device_model=bindparam("device_model"),
                created_at=bindparam("created_at"),
                last_used_at=bindparam("last_used_at"),
            )
            .prefix_with("OR IGNORE")
        )
        update_stmt = (
            update(table)
            .values(last_used_at=bindparam("last_used_at"))
            .where(table.c.user_id == bindparam("b_user_id"), table.c.hwid == bindparam("b_hwid"))
        )
        update_params = {
            "last_used_at": now,
            "b_user_id": user_id,
            "b_hwid": hwid,
        }
        await db.execute(insert_stmt, [params])
        await db.execute(update_stmt, [update_params])

    await db.commit()
    return True


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

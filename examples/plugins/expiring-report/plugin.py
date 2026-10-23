"""Example plugin: users expiring within N days (endpoint, UI page, daily job)."""

from datetime import UTC, datetime, timedelta

from fastapi import Depends, Query
from sqlalchemy import select

# Panel internals: allowed, but not a stable API.
from app.db.models import User, UserStatus


def setup(ctx):
    async def expiring_users(days: int) -> list[dict]:
        now = datetime.now(UTC)
        query = (
            select(User.id, User.username, User.expire, User.status)
            .where(User.expire.isnot(None), User.expire > now, User.expire <= now + timedelta(days=days))
            .where(User.status.in_([UserStatus.active, UserStatus.on_hold]))
            .order_by(User.expire)
        )
        async with ctx.db() as db:
            rows = (await db.execute(query)).all()
        users = []
        for row in rows:
            expire = row.expire if row.expire.tzinfo else row.expire.replace(tzinfo=UTC)
            users.append(
                {
                    "id": row.id,
                    "username": row.username,
                    "status": getattr(row.status, "value", row.status),
                    "expire": expire.isoformat(),
                    "days_left": max((expire - now).days, 0),
                }
            )
        return users

    # Owner-only: the list covers all users, and a sub-admin may only see their own.
    @ctx.router.get("/users", dependencies=[Depends(ctx.deps.owner)])
    async def list_expiring_users(days: int | None = Query(None, ge=1, le=3650)):
        days = days or ctx.settings.get()["days"]
        return {"days": days, "users": await expiring_users(days)}

    async def daily_report():
        days = ctx.settings.get()["days"]
        users = await expiring_users(days)
        ctx.logger.info(f"{len(users)} user(s) expire within {days} day(s)")

    ctx.job(daily_report, cron="0 9 * * *")

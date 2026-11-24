"""Node payloads carry every inbound tag of a user on every database.

MySQL cuts GROUP_CONCAT output at group_concat_max_len, 1024 bytes by default.
Locally this runs on in-memory SQLite; with TEST_FROM set (CI's PostgreSQL,
MySQL and MariaDB jobs) it runs on the application engine against the migrated
test database, so the engine's per-connection setup is part of the test.
"""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.models import Group, ProxyInbound, User, UserStatus, inbounds_groups_association, users_groups_association
from app.node.user import core_users


# On the test's loop, so the teardown can still close the connections it opened.
@pytest_asyncio.fixture(loop_scope="function")
async def session_factory():
    if os.getenv("TEST_FROM", "local").lower() == "local":
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        async with engine.begin() as conn:
            await conn.run_sync(base.Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
        await engine.dispose()
    else:
        # The app engine outlives each test's event loop: drop pooled connections
        # an earlier test opened on its (now closed) loop, and close ours before
        # this loop ends.
        await base.engine.dispose(close=False)
        yield base.SessionLocal
        await base.engine.dispose()


async def test_user_with_many_inbounds_gets_every_tag(session_factory):
    suffix = uuid4().hex[:8]
    # 40 tags of 31 characters: 1279 bytes once joined, past MySQL's default limit.
    tags = [f"VLESS-TCP-REALITY-{suffix}-{i:04d}" for i in range(40)]
    async with session_factory() as db:
        # inserted_primary_key, not RETURNING: MySQL has no INSERT ... RETURNING.
        group_id = (
            await db.execute(insert(Group).values(name=f"many-{suffix}", is_disabled=False))
        ).inserted_primary_key[0]
        inbound_ids = [(await db.execute(insert(ProxyInbound).values(tag=tag))).inserted_primary_key[0] for tag in tags]
        await db.execute(
            insert(inbounds_groups_association),
            [{"inbound_id": inbound_id, "group_id": group_id} for inbound_id in inbound_ids],
        )
        user_id = (
            await db.execute(
                insert(User).values(
                    username=f"many-{suffix}",
                    status=UserStatus.active,
                    created_at=datetime.now(UTC),
                    proxy_settings={"vless": {"id": str(uuid4())}},
                )
            )
        ).inserted_primary_key[0]
        await db.execute(insert(users_groups_association).values(user_id=user_id, groups_id=group_id))
        await db.commit()

    try:
        async with session_factory() as db:
            # The Start shape (one core's tags) and the delivery refresh shape (user ids).
            [start] = await core_users(db, inbound_tags=tags)
            [refresh] = await core_users(db, user_ids=[user_id])
        assert sorted(start.inbounds) == tags
        assert sorted(refresh.inbounds) == tags
    finally:
        async with session_factory() as db:
            await db.execute(delete(users_groups_association).where(users_groups_association.c.user_id == user_id))
            await db.execute(
                delete(inbounds_groups_association).where(inbounds_groups_association.c.group_id == group_id)
            )
            await db.execute(delete(User).where(User.id == user_id))
            await db.execute(delete(ProxyInbound).where(ProxyInbound.id.in_(inbound_ids)))
            await db.execute(delete(Group).where(Group.id == group_id))
            await db.commit()

"""A temp key bound to one owner setup action must only be consumable by that action."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.temp_key import (
    TempKeyConsumeError,
    consume_temp_key,
    create_temp_key,
    get_temp_key,
    mark_temp_key_used,
)

# Keys are created by the CLI (GetDB session) and consumed by a request session, so every step below
# uses its own session, as the real flow does.
ACTION = "delete_owner"
OTHER_ACTION = "reset_owner"
IP = "10.0.0.1"


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)
    yield async_sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    await engine.dispose()


async def _create(session_factory, action: str | None) -> str:
    async with session_factory() as db:
        return (await create_temp_key(db, action=action)).key


async def _consume(session_factory, key: str, action: str) -> str | None:
    """Consume ``key`` and return the error detail, or None when the key was accepted."""
    async with session_factory() as db:
        try:
            await consume_temp_key(db, key, action=action, ip=IP)
        except TempKeyConsumeError as exc:
            return exc.detail
    return None


async def test_bound_key_is_not_consumed_by_another_action(session_factory):
    """A delete key must not authorise a password reset, and must survive the attempt."""
    key = await _create(session_factory, ACTION)

    assert await _consume(session_factory, key, OTHER_ACTION) == "invalid key"

    async with session_factory() as db:
        stored = await get_temp_key(db, key)
    assert stored is not None
    assert stored.used_at is None
    assert stored.used_by_ip is None
    assert stored.action == ACTION


async def test_bound_key_is_consumed_by_its_own_action(session_factory):
    """The action a key was bound to still consumes it."""
    key = await _create(session_factory, ACTION)

    assert await _consume(session_factory, key, ACTION) is None

    async with session_factory() as db:
        stored = await get_temp_key(db, key)
    assert stored is not None
    assert stored.used_at is not None
    assert stored.used_by_ip == IP
    assert stored.action == ACTION


async def test_unbound_key_is_consumed_by_any_action(session_factory):
    """Keys created without an action stay unbound and accept the first action presented."""
    for action in ("create_owner", "reset_owner", "delete_owner", "upgrade_owner"):
        pending = await _create(session_factory, None)

        async with session_factory() as db:
            assert (await get_temp_key(db, pending)).action == "pending"

        assert await _consume(session_factory, pending, action) is None

        async with session_factory() as db:
            assert (await get_temp_key(db, pending)).action == action


async def test_mark_temp_key_used_respects_the_binding(session_factory):
    """The instance based helper must not let a bound key be used for another action."""
    key = await _create(session_factory, ACTION)

    async with session_factory() as db:
        row = await get_temp_key(db, key)
        with pytest.raises(TempKeyConsumeError) as exc_info:
            await mark_temp_key_used(db, row, action=OTHER_ACTION, ip=IP)
        assert exc_info.value.detail == "invalid key"

    async with session_factory() as db:
        stored = await get_temp_key(db, key)
    assert stored.used_at is None
    assert stored.action == ACTION


async def test_unknown_used_and_expired_keys_keep_their_errors(session_factory):
    """Existing failure messages are unchanged by the action binding."""
    assert await _consume(session_factory, "00000000-0000-0000-0000-000000000000", "create_owner") == "invalid key"

    used = await _create(session_factory, "create_owner")
    assert await _consume(session_factory, used, "create_owner") is None
    assert await _consume(session_factory, used, "create_owner") == "key already used"

    expired = await _create(session_factory, "create_owner")
    async with session_factory() as db:
        row = await get_temp_key(db, expired)
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()
    assert await _consume(session_factory, expired, "create_owner") == "key expired"

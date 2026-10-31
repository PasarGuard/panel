import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import begin_immediate_if_sqlite


@pytest.mark.asyncio
async def test_begin_immediate_restarts_existing_sqlite_transaction():
    """SQLite write serialization must precede the read phase of reorder/allocation flows."""
    db = Mock()
    db.bind.dialect.name = "sqlite"
    db.in_transaction.return_value = True
    db.rollback = AsyncMock()
    db.execute = AsyncMock()

    await begin_immediate_if_sqlite(db)

    db.rollback.assert_awaited_once_with()
    statement = db.execute.await_args.args[0]
    assert str(statement) == "BEGIN IMMEDIATE"


@pytest.mark.asyncio
async def test_begin_immediate_is_noop_for_row_locking_databases():
    """Databases with row-level locks should retain their normal transaction flow."""
    db = Mock()
    db.bind.dialect.name = "postgresql"
    db.rollback = AsyncMock()
    db.execute = AsyncMock()

    await begin_immediate_if_sqlite(db)

    db.rollback.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_begin_immediate_serializes_sqlite_allocations(tmp_path):
    """Concurrent allocators must observe distinct, freshly committed sort slots."""
    engine = create_async_engine(
        URL.create("sqlite+aiosqlite", database=str(tmp_path / "sort-order.db")),
        connect_args={"timeout": 1},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    first_has_lock = asyncio.Event()
    release_first = asyncio.Event()

    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE sortable_items (sort_order INTEGER NOT NULL)"))

    async def allocate(*, pause: bool) -> int:
        async with sessions() as db:
            await begin_immediate_if_sqlite(db)
            next_slot = (
                await db.execute(text("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM sortable_items"))
            ).scalar_one()
            if pause:
                first_has_lock.set()
                await release_first.wait()
            await db.execute(text("INSERT INTO sortable_items (sort_order) VALUES (:slot)"), {"slot": next_slot})
            await db.commit()
            return next_slot

    try:
        first = asyncio.create_task(allocate(pause=True))
        await first_has_lock.wait()
        second = asyncio.create_task(allocate(pause=False))
        await asyncio.sleep(0.05)
        assert not second.done()

        release_first.set()
        assert await asyncio.gather(first, second) == [0, 1]
    finally:
        await engine.dispose()

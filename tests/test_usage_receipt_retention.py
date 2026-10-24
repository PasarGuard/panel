import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, select, text, update

from app.db.models import System, UsageReceipt, User
from app.jobs import record_usages as job
from app.jobs._usage_storage import Receipt, StaleUsageCollection, UsageStore
from tests import test_record_usages as usage_tests

session_factory = usage_tests.session_factory


@pytest.fixture(autouse=True)
def reset_recording(monkeypatch):
    job._tasks.clear()
    job._unstaged.clear()
    job._dialect_cache.clear()
    job._usage_coefficient_cache.clear()
    monkeypatch.setattr(job, "_stopping", False)
    monkeypatch.setattr(job, "_enforcement_task", None)
    monkeypatch.setattr(job, "_enforcement_dirty", False)
    monkeypatch.setattr(job, "enforce_admin_limits_now", AsyncMock())


async def seed(factory):
    async with factory() as db:
        user = User(username="retention-user")
        db.add_all([user, System()])
        await db.commit()
        return user.id


async def make_receipt(store, uid, kind="users", amount=12, node_id=1):
    epoch = await store.prepare(kind, node_id)
    stats = [{"uid": uid, "value": amount}] if kind == "users" else [{"up": amount, "down": 0}]
    return Receipt.create(kind, node_id, epoch, stats, False)


async def expire(factory, receipt, *, applied=True, acknowledged=True):
    old = datetime.now(UTC) - timedelta(days=31)
    values = {}
    if applied:
        values["applied_at"] = old
    if acknowledged:
        values["acknowledged_at"] = old
    async with factory() as db:
        await db.execute(update(UsageReceipt).where(UsageReceipt.receipt_id == receipt.receipt_id).values(**values))
        await db.commit()


async def traffic(factory, kind="users"):
    async with factory() as db:
        column = User.used_traffic if kind == "users" else System.uplink
        return (await db.execute(select(column))).scalar_one()


@pytest.mark.parametrize("kind", ["users", "outbounds"])
async def test_cleanup_fences_late_reply_and_survives_store_restart(session_factory, kind):
    uid = await seed(session_factory)
    store = UsageStore(job._transaction, await job.get_dialect())
    receipt = await make_receipt(store, uid, kind)
    await store.stage(receipt)
    await store.apply(kind, 1)
    await store.acknowledge(receipt)
    await expire(session_factory, receipt)
    assert await store.cleanup(30, 100) == 1
    store = UsageStore(job._transaction, await job.get_dialect())
    with pytest.raises(StaleUsageCollection):
        await store.stage(receipt)
    assert await traffic(session_factory, kind) == 12
    fresh = await make_receipt(store, uid, kind, 23)
    await store.stage(fresh)
    await store.stage(fresh)
    await store.apply(kind, 1)
    assert await traffic(session_factory, kind) == 35


@pytest.mark.parametrize("kind", ["users", "outbounds"])
async def test_only_old_applied_and_acknowledged_receipts_expire(session_factory, kind):
    uid = await seed(session_factory)
    store = UsageStore(job._transaction, await job.get_dialect())
    receipts = [await make_receipt(store, uid, kind) for _ in range(6)]
    for receipt in receipts[:5]:
        await store.stage(receipt)
    await store.apply(kind, 1)
    # eligible, unACKed, recently ACKed, recently applied, legacy tombstone
    for index in (0, 2, 3):
        await store.acknowledge(receipts[index])
    await expire(session_factory, receipts[0])
    await expire(session_factory, receipts[1], acknowledged=False)
    await expire(session_factory, receipts[2], acknowledged=False)
    await expire(session_factory, receipts[3], applied=False)
    async with session_factory() as db:
        await db.execute(
            update(UsageReceipt).where(UsageReceipt.receipt_id == receipts[4].receipt_id).values(applied_at=None)
        )
        await db.commit()
    await store.stage(receipts[5])  # pending, even if ACK is already confirmed
    await expire(session_factory, receipts[5])
    assert await store.cleanup(30, 100) == 1
    async with session_factory() as db:
        remaining = set((await db.execute(select(UsageReceipt.receipt_id))).scalars())
    assert remaining == {receipt.receipt_id for receipt in receipts[1:]}
    await store.apply(kind, 1)
    assert await traffic(session_factory, kind) == 72


async def test_cleanup_is_bounded_across_streams(session_factory):
    uid = await seed(session_factory)
    store = UsageStore(job._transaction, await job.get_dialect())
    for node_id in (1, 2):
        for _ in range(3):
            receipt = await make_receipt(store, uid, node_id=node_id)
            await store.stage(receipt)
            await store.apply("users", node_id)
            await store.acknowledge(receipt)
            await expire(session_factory, receipt)
    assert await store.cleanup(30, 4) == 4
    assert await store.cleanup(30, 4) == 2
    assert await store.cleanup(30, 4) == 0
    assert await traffic(session_factory) == 72


async def test_cleanup_failure_rolls_back_deletion_and_fence(session_factory):
    uid = await seed(session_factory)
    store = UsageStore(job._transaction, await job.get_dialect())
    receipt = await make_receipt(store, uid)
    await store.stage(receipt)
    await store.apply("users", 1)
    await store.acknowledge(receipt)
    await expire(session_factory, receipt)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.lower().startswith("delete from usage_receipt_ledger"):
            raise RuntimeError("injected cleanup failure")

    event.listen(job.engine.sync_engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            await store.cleanup(30, 100)
    finally:
        event.remove(job.engine.sync_engine, "before_cursor_execute", fail)
    assert await store.prepare("users", 1) == receipt.collection_epoch
    await store.stage(receipt)
    await store.apply("users", 1)
    assert await traffic(session_factory) == 12
    assert await store.cleanup(30, 100) == 1


async def test_applied_timestamp_rolls_back_with_accounting(session_factory):
    uid = await seed(session_factory)
    store = UsageStore(job._transaction, await job.get_dialect())
    receipt = await make_receipt(store, uid)
    await store.stage(receipt)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.lower().startswith("update usage_receipt_ledger") and "processed=" in statement.lower():
            raise RuntimeError("injected accounting failure")

    event.listen(job.engine.sync_engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            await store.apply("users", 1)
    finally:
        event.remove(job.engine.sync_engine, "before_cursor_execute", fail)
    async with session_factory() as db:
        row = (await db.execute(select(UsageReceipt))).scalar_one()
        assert row.applied_at is None and not row.processed and row.payload is not None
    assert await traffic(session_factory) == 0
    await store.apply("users", 1)
    assert await traffic(session_factory) == 12


class ReplayNode:
    def __init__(self, uid, amount=23):
        self.sample = SimpleNamespace(
            receipt_id=str(uuid4()),
            collected_at=int(datetime.now(UTC).timestamp() * 1000),
            stats=[SimpleNamespace(name=str(uid), type="uplink", link="traffic", value=amount)],
        )
        self.collect_usage = AsyncMock(side_effect=lambda **kwargs: self.sample)
        self.acknowledge_usage = AsyncMock(side_effect=self.acknowledge)
        self.get_extra = AsyncMock(return_value={"usage_coefficient": 1})

    async def acknowledge(self, **kwargs):
        assert kwargs["receipt_id"] == self.sample.receipt_id
        self.sample = SimpleNamespace(receipt_id="", collected_at=self.sample.collected_at, stats=[])


async def test_cleanup_during_collection_recollects_without_premature_ack(session_factory):
    uid = await seed(session_factory)
    store = UsageStore(job._transaction, await job.get_dialect())
    previous = await make_receipt(store, uid)
    await store.stage(previous)
    await store.apply("users", 1)
    await store.acknowledge(previous)
    await expire(session_factory, previous)
    node = ReplayNode(uid)

    async def delayed(**kwargs):
        assert await store.cleanup(30, 100) == 1
        return node.sample

    node.collect_usage.side_effect = delayed
    await job._process_stream("users", 1, node)
    node.acknowledge_usage.assert_not_awaited()
    assert await traffic(session_factory) == 12
    assert not job._unstaged
    node.collect_usage.side_effect = lambda **kwargs: node.sample
    await job._process_stream("users", 1, node)
    node.acknowledge_usage.assert_awaited_once()
    assert await traffic(session_factory) == 35


async def test_unstaged_late_applied_receipt_does_not_block_stream(session_factory):
    uid = await seed(session_factory)
    store = UsageStore(job._transaction, await job.get_dialect())
    old = await make_receipt(store, uid)
    await store.stage(old)
    await store.apply("users", 1)
    await store.acknowledge(old)
    await expire(session_factory, old)
    await store.cleanup(30, 100)
    job._unstaged[("users", 1)] = old
    await job._process_stream("users", 1, ReplayNode(uid))
    assert not job._unstaged
    assert await traffic(session_factory) == 35


@pytest.mark.parametrize("lost_response", [False, True])
async def test_failed_ack_never_marks_receipt_deletable(session_factory, lost_response):
    uid = await seed(session_factory)
    node = ReplayNode(uid)
    ack = node.acknowledge

    async def fail(**kwargs):
        if lost_response:
            await ack(**kwargs)
        raise TimeoutError("ACK response lost")

    node.acknowledge_usage.side_effect = fail
    await job._process_stream("users", 1, node)
    async with session_factory() as db:
        row = (await db.execute(select(UsageReceipt))).scalar_one()
        assert row.processed and row.applied_at is not None and row.acknowledged_at is None
        await db.execute(update(UsageReceipt).values(applied_at=datetime.now(UTC) - timedelta(days=31)))
        await db.commit()
    store = UsageStore(job._transaction, await job.get_dialect())
    assert await store.cleanup(30, 100) == 0
    node.acknowledge_usage.side_effect = ack
    await job._process_stream("users", 1, node)
    assert await traffic(session_factory) == 23


async def test_shutdown_drains_cleanup(monkeypatch):
    import asyncio

    started, finish = asyncio.Event(), asyncio.Event()

    async def cleanup():
        started.set()
        await finish.wait()

    monkeypatch.setattr(job, "_cleanup_usage_receipts", cleanup)
    monkeypatch.setattr(job, "_cleanup_task", None)
    await job._schedule_receipt_cleanup()
    await started.wait()
    shutdown = asyncio.create_task(job.drain_usage_recording())
    await asyncio.sleep(0)
    assert not shutdown.done()
    finish.set()
    await shutdown
    assert job._cleanup_task.done()


def test_migration_preserves_old_rows_and_guards_downgrade():
    root = Path(__file__).resolve().parents[1]

    def migration(name, conn):
        path = root / "app/db/migrations/versions" / name
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.op = Operations(MigrationContext.configure(conn))
        return module

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        migration("c6d8e2f4a901_add_usage_receipts.py", conn).upgrade()
        conn.execute(
            text("INSERT INTO usage_receipts VALUES (1, 'users', 'pending', '{}'), (2, 'users', 'applied', NULL)")
        )
        migration("d8f1a7b9c203_usage_receipt_ledger.py", conn).upgrade()
        retention = migration("f2a7b9c4d610_usage_receipt_retention.py", conn)
        retention.upgrade()
        rows = conn.execute(select(UsageReceipt.__table__).order_by(UsageReceipt.node_id)).all()
        assert len(rows) == 2
        assert not rows[0].processed and rows[0].payload == {}
        assert rows[1].processed and rows[1].payload is None
        assert all(row.applied_at is None and row.acknowledged_at is None for row in rows)
        retention.downgrade()  # permitted before new collectors initialize
        retention.upgrade()
        conn.execute(text("INSERT INTO usage_streams VALUES (1, 'users', 'epoch')"))
        conn.execute(text("DELETE FROM usage_receipt_ledger"))
        with pytest.raises(RuntimeError, match="collection fences"):
            retention.downgrade()
    engine.dispose()


def test_full_migration_matches_models(tmp_path):
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.config_file_name = None  # Alembic's fileConfig must not disable pytest's existing loggers.
    cfg.set_main_option("script_location", str(root / "app/db/migrations"))
    cfg.set_main_option("sqlalchemy.url", "sqlite+aiosqlite:///" + (tmp_path / "migration.db").as_posix())
    command.upgrade(cfg, "head")
    command.check(cfg)
    command.downgrade(cfg, "e9c3b6a71204")
    command.upgrade(cfg, "head")
    command.check(cfg)

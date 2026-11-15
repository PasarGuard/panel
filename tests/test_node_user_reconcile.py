"""Background reconciliation of node users: deltas only, fresh state, fenced, never touching node status."""

import asyncio
import contextlib
import gc
import logging
import math
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from PasarGuardNodeBridge import Health, InMemoryUserSyncStore
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser
from PasarGuardNodeBridge.controller import FailedUsers
from sqlalchemy import delete, insert, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.node as node_package
from app.db.base import Base
from app.db.models import (
    Group,
    NodeStatus,
    ProxyInbound,
    User,
    UserStatus,
    inbounds_groups_association,
    users_groups_association,
)
from app.jobs import node_user_reconcile as reconcile
from app.models.core import CoreType
from app.nats.kv_cas import MemoryCasKv
from app.node import NodeManager, UserSyncPreemptedError, bridge as bridge_module, sync as node_sync
from app.node.bridge import FullSyncConflictError
from app.node.nats_memory import NatsUserSyncStore
from app.operation import node as operation_node
from app.operation.node import NodeOperation
from tests.test_node_bridge import FakeNodeState, attach_fake_transport, close_node, make_node, wait_until

INBOUND = "in-1"


class NodeUsers(FakeNodeState):
    """A node's user set: a payload with inbounds adds or updates, one without removes."""

    def __init__(self):
        super().__init__()
        self.answer = None  # optional callable(users) -> failed users, before anything is applied
        self.hang_once = False

    async def apply_delta(self, users):
        self.delta_started.set()
        if self.hang_once:
            self.hang_once = False
            await asyncio.Event().wait()
        if self.gate is not None:
            await self.gate.wait()
        if self.answer is not None and (failed := self.answer(users)):
            return failed
        for user in users:
            if user.inbounds:
                self.users[user.email] = list(user.inbounds)
            else:
                self.users.pop(user.email, None)
        self.deltas.append([user.email for user in users])
        return []

    def sent(self) -> list[str]:
        return [email for delta in self.deltas for email in delta]


class _Session:
    def __init__(self, maker):
        self._session = maker()

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        await self._session.close()
        return False


# The node and its queue worker must live on the test's own event loop.
@pytest_asyncio.fixture(loop_scope="function", params=["memory", "nats"])
async def env(request, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(node_sync, "GetDB", lambda: _Session(maker))
    monkeypatch.setattr(reconcile, "GetDB", lambda: _Session(maker))
    monkeypatch.setattr(node_sync, "_current_state", node_sync.CurrentStateReader())
    # Queue deliveries read the database too, as in production.
    monkeypatch.setattr(bridge_module, "_refresh_handler", node_sync.refresh_node_users)

    for name, value in {
        "_states": {},
        "_running": {},
        "_sweep_node": None,
        "_last_regular_start": -math.inf,
        "_last_sweep_start": -math.inf,
        "_highest_user_id_seen": 0,
        "_stopping": False,
        "CONNECT_DELAY": 0.0,
        "CHUNK_GAP_MIN": 0.01,
        "CHUNK_GAP_MAX": 0.05,
        "BATCH_PAUSE": 0.0,
    }.items():
        monkeypatch.setattr(reconcile, name, value)
    monkeypatch.setattr(reconcile.job_settings, "node_user_reconcile_interval", 1800)
    monkeypatch.setattr(reconcile.job_settings, "node_user_removal_sweep_interval", 86400)

    manager = NodeManager()
    monkeypatch.setattr(reconcile, "node_manager", manager)
    monkeypatch.setattr(operation_node, "node_manager", manager)
    leader = {"value": True}
    monkeypatch.setattr(reconcile, "is_job_leader", lambda: leader["value"])
    db_nodes = {1: (NodeStatus.connected, 1)}
    cores = {1: SimpleNamespace(type=CoreType.xray)}

    async def fake_db_nodes(node_ids):
        return {node_id: db_nodes[node_id] for node_id in node_ids if node_id in db_nodes}

    monkeypatch.setattr(reconcile, "_db_nodes", fake_db_nodes)
    monkeypatch.setattr(reconcile.core_manager, "get_core", AsyncMock(side_effect=lambda core_id: cores.get(core_id)))

    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv) if request.param == "nats" else InMemoryUserSyncStore()
    node = make_node("grpc", store, node_id="1")
    state = attach_fake_transport(monkeypatch, node, NodeUsers())
    node.start = AsyncMock(name="start")
    await node.connect("0.5.5", "26.3.27")
    manager._nodes[1] = node

    async with maker() as db:
        inbound_id = (
            await db.execute(insert(ProxyInbound).values(tag=INBOUND).returning(ProxyInbound.id))
        ).scalar_one()
        group_id = (
            await db.execute(insert(Group).values(name="g", is_disabled=False).returning(Group.id))
        ).scalar_one()
        await db.execute(insert(inbounds_groups_association).values(inbound_id=inbound_id, group_id=group_id))
        await db.commit()

    async def add_user(status=UserStatus.active, *, changed: datetime | None = None) -> int:
        async with maker() as db:
            user_id = (
                await db.execute(
                    insert(User)
                    .values(
                        username=f"u{uuid4().hex[:10]}",
                        status=status,
                        created_at=datetime.now(UTC) - timedelta(days=60),
                        last_status_change=changed,
                        proxy_settings={"vless": {"id": str(uuid4())}},
                    )
                    .returning(User.id)
                )
            ).scalar_one()
            await db.execute(insert(users_groups_association).values(user_id=user_id, groups_id=group_id))
            await db.commit()
        return user_id

    async def set_status(user_id: int, status: UserStatus, changed: datetime | None = None) -> None:
        async with maker() as db:
            values = {"status": status, "last_status_change": changed or datetime.now(UTC)}
            await db.execute(update(User).where(User.id == user_id).values(**values))
            await db.commit()

    async def remove_user(user_id: int) -> None:
        async with maker() as db:
            await db.execute(delete(users_groups_association).where(users_groups_association.c.user_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()

    harness = SimpleNamespace(
        kind=request.param,
        maker=maker,
        manager=manager,
        node=node,
        state=state,
        store=store,
        leader=leader,
        db_nodes=db_nodes,
        cores=cores,
        add_user=add_user,
        set_status=set_status,
        remove_user=remove_user,
    )
    try:
        yield harness
    finally:
        if state.gate is not None:
            state.gate.set()
        for task in list(reconcile._running.values()):
            task.cancel()
        await asyncio.gather(*reconcile._running.values(), return_exceptions=True)
        await manager.stop_user_sync_retries()
        await close_node(node)
        if request.param == "nats":
            await store.close()
        await engine.dispose()


def node_state(node_id: int = 1) -> reconcile._NodeState:
    return reconcile._states[node_id]


def settled_state(*, swept: bool = True) -> reconcile._NodeState:
    """A node reconciled 30 minutes ago (and swept just now), now due again."""
    return reconcile._NodeState(
        next_due=0.0,
        last_success_at=datetime.now(UTC) - timedelta(minutes=30),
        last_sweep_at=time.monotonic() if swept else None,
    )


def make_due(node_id: int = 1) -> None:
    node_state(node_id).next_due = 0.0
    reconcile._last_regular_start = -math.inf


async def run_pass(env) -> None:
    task = await reconcile.reconcile_node_users()
    assert task is not None, "no pass was started"
    await asyncio.wait_for(task, 10)


async def queue_settled(env) -> None:
    await wait_until(lambda: env.node._sync_worker_task is None or env.node._sync_worker_task.done(), timeout=5)


# 1, 2 ------------------------------------------------------------------------------------------------
async def test_pass_uses_only_delta_sync_and_adds_a_user_missing_on_the_node(env):
    present, missing = await env.add_user(), await env.add_user()
    env.state.users[str(present)] = [INBOUND]

    await run_pass(env)

    assert env.state.users == {str(present): [INBOUND], str(missing): [INBOUND]}
    assert env.state.snapshots == []  # never the full snapshot that restarts the core
    env.node.start.assert_not_called()
    assert env.state.deltas


# 3 ---------------------------------------------------------------------------------------------------
async def test_user_expired_ten_minutes_ago_with_a_lost_removal_is_removed_by_the_frequent_pass(env):
    keep = await env.add_user()
    expired = await env.add_user()
    await env.set_status(expired, UserStatus.expired, datetime.now(UTC) - timedelta(minutes=10))
    env.state.users = {str(keep): [INBOUND], str(expired): [INBOUND]}  # its removal never arrived
    reconcile._states[1] = settled_state()

    await run_pass(env)

    assert env.state.users == {str(keep): [INBOUND]}


async def test_long_inactive_and_deleted_users_are_removed_by_the_sweep_only(env):
    active = await env.add_user()
    old_expired = await env.add_user(UserStatus.expired, changed=datetime.now(UTC) - timedelta(days=30))
    deleted = await env.add_user()
    deleted_last = await env.add_user()
    reconcile._states[1] = settled_state()
    await run_pass(env)  # sees the highest id while that user still exists
    await env.remove_user(deleted)
    await env.remove_user(deleted_last)
    stale = {str(old_expired): [INBOUND], str(deleted): [INBOUND], str(deleted_last): [INBOUND]}
    env.state.users.update(stale)

    make_due()
    await run_pass(env)  # frequent pass only: nothing it sends covers them
    assert set(stale) <= set(env.state.users)

    node_state().last_sweep_at = time.monotonic() - 86400
    make_due()
    await run_pass(env)
    assert env.state.users == {str(active): [INBOUND]}


async def test_sweep_reaches_the_last_id_the_counter_issued(env, monkeypatch):
    user_id = await env.add_user()
    monkeypatch.setattr(reconcile, "_last_issued_user_id", AsyncMock(return_value=user_id + 2))
    assert await reconcile._removal_sweep_ids(set()) == [user_id + 1, user_id + 2]

    monkeypatch.setattr(reconcile, "_last_issued_user_id", AsyncMock(return_value=None))
    reconcile._highest_user_id_seen = user_id + 3  # counter unreadable: the highest id seen still counts
    assert await reconcile._removal_sweep_ids(set()) == [user_id + 1, user_id + 2, user_id + 3]


# 4 ---------------------------------------------------------------------------------------------------
async def test_user_removed_after_the_chunk_was_read_is_removed_after_the_chunk(env, monkeypatch):
    user_id = await env.add_user()
    reconcile._states[1] = settled_state()
    read = reconcile.refresh_node_users

    async def read_then_remove(node_id, emails):
        users = await read(node_id, emails)
        # The admin deletes the user right after the chunk was read: the app queues the removal.
        await env.remove_user(user_id)
        await env.node.update_user(ProtoUser(email=str(user_id)))
        return users

    monkeypatch.setattr(reconcile, "refresh_node_users", read_then_remove)
    await run_pass(env)

    await wait_until(lambda: str(user_id) not in env.state.users)
    await queue_settled(env)
    assert str(user_id) not in env.state.users
    sends = [index for index, delta in enumerate(env.state.deltas) if str(user_id) in delta]
    assert len(sends) == 2  # the chunk carried the user, the queued removal landed after it


async def test_user_activated_after_the_removal_list_was_built_stays_on_the_node(env, monkeypatch):
    user_id = await env.add_user(UserStatus.disabled, changed=datetime.now(UTC) - timedelta(days=30))
    reconcile._states[1] = settled_state(swept=False)
    collect = reconcile._removal_sweep_ids

    async def collect_then_activate(exclude, **kwargs):
        ids = await collect(exclude, **kwargs)
        assert user_id in ids
        await env.set_status(user_id, UserStatus.active)
        return ids

    monkeypatch.setattr(reconcile, "_removal_sweep_ids", collect_then_activate)
    await run_pass(env)

    assert env.state.users[str(user_id)] == [INBOUND]


# 5 ---------------------------------------------------------------------------------------------------
async def test_fence_held_elsewhere_skips_the_node_and_leaves_the_queue(env):
    user_id = await env.add_user()
    async with env.node.full_sync_fence():
        await env.node.update_user(ProtoUser(email=str(user_id), inbounds=[INBOUND]))
        assert await reconcile.reconcile_node_users() is None  # fence busy: skipped
        # The fence can also be taken between the check and the chunk: 409, nothing sent.
        await reconcile._run_pass(1, env.node, node_state(), sweep=False)
        assert env.state.deltas == []
        assert not node_state().failed and node_state().next_due <= time.monotonic()
    await wait_until(lambda: str(user_id) in env.state.users)  # the queued update was kept


async def test_deliveries_that_do_not_settle_skip_the_node(env, monkeypatch):
    await env.add_user()
    monkeypatch.setattr(
        env.node, "capture_queued_work", AsyncMock(side_effect=FullSyncConflictError(503, "claims in flight"))
    )
    await run_pass(env)
    assert env.state.deltas == []
    assert not node_state().failed and node_state().next_due <= time.monotonic()


async def test_chunk_limit_reached_before_anything_was_sent_is_a_skip(env, monkeypatch):
    monkeypatch.setattr(reconcile, "CHUNK_TIMEOUT", 0.2)
    await env.add_user()
    async with env.manager._user_sync_locks.setdefault(1, asyncio.Lock()):  # a long bulk sync holds the node
        await run_pass(env)
    assert env.state.deltas == []
    assert not node_state().failed and node_state().next_due <= time.monotonic()


async def test_queued_updates_defer_the_pass_three_ticks_then_it_runs(env, monkeypatch):
    await env.add_user()
    monkeypatch.setattr(env.node, "has_queued_users", AsyncMock(return_value=True))
    for _ in range(3):
        assert await reconcile.reconcile_node_users() is None
    task = await reconcile.reconcile_node_users()
    assert task is not None
    await task
    assert env.state.deltas


# 6 ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("case", ["unhealthy", "disabled", "limited", "old", "unknown_version", "mtproto"])
async def test_nodes_that_must_not_be_reconciled_get_nothing(env, case):
    await env.add_user()
    if case == "unhealthy":
        await env.node.set_health(Health.BROKEN)
    elif case in ("disabled", "limited"):
        env.db_nodes[1] = (NodeStatus(case), 1)
    elif case == "old":
        await env.node.set_reported_versions("0.5.4", "26.3.27")
    elif case == "unknown_version":
        await env.node.set_reported_versions("dev", "26.3.27")
    else:
        env.cores[1] = SimpleNamespace(type=CoreType.mtproto)

    for _ in range(2):
        assert await reconcile.reconcile_node_users() is None
        make_due()
    assert env.state.deltas == [] and env.state.snapshots == []
    if case in ("disabled", "limited"):
        assert not node_state().after_connect  # the plan is dropped
    if case == "unhealthy":
        assert node_state().after_connect  # kept for when it is healthy again


async def test_old_node_is_warned_about_once_per_connection(env, caplog):
    await env.node.set_reported_versions("0.5.4", "26.3.27")
    caplog.set_level(logging.WARNING)

    def warnings():
        return [r for r in caplog.records if "not reconciled" in r.getMessage()]

    for _ in range(3):
        await reconcile.reconcile_node_users()
        make_due()
    assert len(warnings()) == 1
    env.manager.request_user_reconcile(1)  # reconnected
    await reconcile.reconcile_node_users()
    assert len(warnings()) == 2


# 7 ---------------------------------------------------------------------------------------------------
async def test_not_leader_does_nothing(env):
    await env.add_user()
    env.leader["value"] = False
    assert await reconcile.reconcile_node_users() is None
    assert env.state.deltas == []


async def test_leadership_lost_between_chunks_drops_the_rest(env, monkeypatch):
    monkeypatch.setattr(reconcile, "CHUNK_SIZE", 2)
    ids = [await env.add_user() for _ in range(6)]
    reconcile._states[1] = settled_state()
    send_chunk = env.manager.reconcile_user_chunk

    async def chunk_then_lose_leadership(*args, **kwargs):
        result = await send_chunk(*args, **kwargs)
        env.leader["value"] = False
        return result

    monkeypatch.setattr(env.manager, "reconcile_user_chunk", chunk_then_lose_leadership)
    await run_pass(env)
    assert env.state.sent() == [str(user_id) for user_id in ids[:2]]


# 8 ---------------------------------------------------------------------------------------------------
async def test_cancel_mid_chunk_lifts_the_fence_and_gives_the_queue_back(env):
    user_id = await env.add_user()
    reconcile._states[1] = settled_state()
    env.state.gate = asyncio.Event()
    task = await reconcile.reconcile_node_users()
    await asyncio.wait_for(env.state.delta_started.wait(), 5)
    assert await env.node.full_sync_in_progress()
    await env.node.update_user(ProtoUser(email=str(user_id), inbounds=[INBOUND]))  # waits behind the fence

    await reconcile.stop_node_user_reconcile()  # app shutdown

    assert task.cancelled()
    assert not await env.node.full_sync_in_progress()
    env.state.gate.set()
    await wait_until(lambda: str(user_id) in env.state.users)  # the queued update still goes out
    assert await env.node.get_health() is Health.HEALTHY


async def test_hung_node_hits_the_chunk_limit_and_later_updates_still_arrive(env, monkeypatch):
    monkeypatch.setattr(reconcile, "CHUNK_TIMEOUT", 0.3)
    user_id = await env.add_user()
    reconcile._states[1] = settled_state()
    env.state.hang_once = True

    await run_pass(env)

    assert node_state().failed
    assert node_state().next_due > time.monotonic() + reconcile.FAILURE_RETRY - 10
    assert not await env.node.full_sync_in_progress()
    assert await env.node.get_health() is Health.HEALTHY
    await env.node.update_user(ProtoUser(email=str(user_id), inbounds=[INBOUND]))
    await wait_until(lambda: str(user_id) in env.state.users)


# 9 ---------------------------------------------------------------------------------------------------
async def test_rejected_batch_is_logged_and_the_pass_goes_on(env, monkeypatch, caplog):
    monkeypatch.setattr(reconcile, "CHUNK_SIZE", 4)
    monkeypatch.setattr(reconcile, "BATCH_SIZE", 2)
    ids = [await env.add_user() for _ in range(8)]
    bad = str(ids[2])
    env.state.answer = lambda users: (
        FailedUsers(users, rejected=True, detail="failed to update users: bad")
        if any(u.email == bad for u in users)
        else None
    )
    reconcile._states[1] = settled_state()
    caplog.set_level(logging.WARNING)

    await run_pass(env)

    assert set(env.state.users) == {str(user_id) for user_id in ids} - {str(ids[2]), str(ids[3])}
    assert any(bad in r.getMessage() and "rejected" in r.getMessage() for r in caplog.records)
    assert not node_state().failed
    assert await env.node.get_health() is Health.HEALTHY


async def test_transport_error_stops_the_pass_without_touching_node_status(env, monkeypatch):
    monkeypatch.setattr(reconcile, "CHUNK_SIZE", 2)
    ids = [await env.add_user() for _ in range(6)]
    env.state.answer = lambda users: FailedUsers(users, rejected=False, detail="UNAVAILABLE")
    reconcile._states[1] = settled_state()

    await run_pass(env)

    assert env.state.users == {}
    assert node_state().failed
    assert node_state().next_due > time.monotonic() + reconcile.FAILURE_RETRY - 10
    assert await env.node.get_health() is Health.HEALTHY
    env.state.answer = None
    make_due()
    await run_pass(env)  # the next pass succeeds and clears the failure
    assert set(env.state.users) == {str(user_id) for user_id in ids}
    assert not node_state().failed


# 10 --------------------------------------------------------------------------------------------------
async def test_manual_sync_during_a_pass_cancels_it_and_succeeds(env):
    user_id = await env.add_user()
    reconcile._states[1] = settled_state()
    env.state.gate = asyncio.Event()
    task = await reconcile.reconcile_node_users()
    await asyncio.wait_for(env.state.delta_started.wait(), 5)

    snapshot = [ProtoUser(email=str(user_id), inbounds=[INBOUND])]
    # No 409, and no wait for the chunk's time limit either.
    assert await asyncio.wait_for(env.manager.sync_full(1, snapshot), 3) is env.node

    await asyncio.wait_for(task, 5)
    assert env.state.snapshots == [[str(user_id)]]
    assert not env.manager.user_reconcile_running(1)


async def test_start_during_a_pass_cancels_it_and_succeeds(env):
    await env.add_user()
    reconcile._states[1] = settled_state()
    env.state.gate = asyncio.Event()
    task = await reconcile.reconcile_node_users()
    await asyncio.wait_for(env.state.delta_started.wait(), 5)
    info = SimpleNamespace(node_version="0.5.5", core_version="26.3.27", started=True)
    env.node.start = AsyncMock(return_value=info)
    db_node = SimpleNamespace(id=1, name="n1", keep_alive=0, default_timeout=10)
    core = SimpleNamespace(type=CoreType.xray, to_str=lambda: "{}", exclude_inbound_tags=[])

    result = await NodeOperation._start_or_attach_node(
        env.node, db_node, core, [], 1, force_start=True, stop_first=False
    )

    assert result is info  # the Start got the fence: no 409
    await asyncio.wait_for(task, 5)
    assert 1 in env.manager.take_user_reconcile_requests()  # and plans a pass


# 11 --------------------------------------------------------------------------------------------------
async def test_attach_plans_a_pass(env, monkeypatch):
    node = MagicMock(node_id="1")
    node.get_lifecycle_state = AsyncMock(return_value=None)
    node.info = AsyncMock(return_value=SimpleNamespace(started=True, node_version="0.5.5", core_version="26.3.27"))
    node.get_health = AsyncMock(return_value=Health.HEALTHY)
    node.connect = AsyncMock()
    monkeypatch.setattr(operation_node, "needs_shared_bridge_memory", lambda: False)

    assert await NodeOperation._attach_if_running(node, "n1") is not None
    assert 1 in env.manager.take_user_reconcile_requests()


async def test_a_second_pass_of_the_same_node_is_not_started(env):
    await env.add_user()
    reconcile._states[1] = settled_state()
    env.state.gate = asyncio.Event()
    first = await reconcile.reconcile_node_users()
    await asyncio.wait_for(env.state.delta_started.wait(), 5)

    make_due()
    assert await reconcile.reconcile_node_users() is None
    assert await env.manager.run_user_reconcile(1, asyncio.sleep(0, result="ran")) is None

    env.state.gate.set()
    await asyncio.wait_for(first, 5)


async def test_sweep_after_a_connect_runs_at_most_once_in_six_hours(env):
    gone = await env.add_user()
    await env.add_user()
    await env.remove_user(gone)

    def swept() -> bool:
        return str(gone) in env.state.sent()

    env.manager.request_user_reconcile(1)
    await run_pass(env)
    assert swept()  # first pass after the attach sweeps

    env.state.deltas.clear()
    reconcile._last_sweep_start = -math.inf  # only the six-hour rule can hold it back
    env.manager.request_user_reconcile(1)  # reconnected soon after
    await run_pass(env)
    assert env.state.deltas and not swept()

    node_state().last_sweep_at = time.monotonic() - 7 * 3600
    reconcile._last_sweep_start = -math.inf
    env.manager.request_user_reconcile(1)
    await run_pass(env)
    assert swept()


# 12 --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("interval", "registered"), [(0, False), (1800, True)])
def test_turned_off_job_is_not_registered(monkeypatch, interval, registered):
    monkeypatch.setattr(reconcile.job_settings, "node_user_reconcile_interval", interval)
    monkeypatch.setattr(reconcile, "on_shutdown", lambda func: func)
    fake_scheduler = MagicMock()
    assert reconcile.register_node_user_reconcile(fake_scheduler) is registered
    assert fake_scheduler.add_job.called is registered


# 13 --------------------------------------------------------------------------------------------------
def warnings_with(caplog, text: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and text in r.getMessage()]


async def test_sweep_stops_a_bounded_distance_above_the_highest_existing_id(env, monkeypatch, caplog):
    user_id = await env.add_user()
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(reconcile, "_last_issued_user_id", AsyncMock(return_value=user_id + 5))
    assert await reconcile._removal_sweep_ids(set(), node_id=1) == [user_id + offset for offset in range(1, 6)]
    assert warnings_with(caplog, "stops at id") == []

    counter = user_id + 1_000_000  # the id counter was pushed far ahead
    monkeypatch.setattr(reconcile, "_last_issued_user_id", AsyncMock(return_value=counter))
    ids = await reconcile._removal_sweep_ids(set(), node_id=1)
    ceiling = user_id + reconcile.MAX_SWEEP_IDS_ABOVE_EXISTING
    assert len(ids) == reconcile.MAX_SWEEP_IDS_ABOVE_EXISTING and ids[-1] == ceiling
    [warning] = warnings_with(caplog, "stops at id")
    assert f"counter is at {counter}" in warning and f"highest existing user id is {user_id};" in warning
    assert f"{counter - ceiling} id(s) above {ceiling}" in warning and "node 1" in warning


async def test_state_changed_between_chunks_is_read_fresh(env, monkeypatch):
    monkeypatch.setattr(reconcile, "CHUNK_SIZE", 1)
    first, second = await env.add_user(), await env.add_user()
    reconcile._states[1] = settled_state()
    pause = reconcile._pause_between_chunks

    async def disable_second_then_pause(node):
        # Committed after the pass listed its ids, before the second chunk is read.
        await env.set_status(second, UserStatus.disabled)
        await pause(node)

    monkeypatch.setattr(reconcile, "_pause_between_chunks", disable_second_then_pause)
    env.state.users[str(second)] = [INBOUND]
    await run_pass(env)
    assert str(first) in env.state.users
    assert str(second) not in env.state.users


async def test_fence_lost_mid_chunk_sends_no_further_batch(env, monkeypatch):
    monkeypatch.setattr(reconcile, "CHUNK_SIZE", 4)
    monkeypatch.setattr(reconcile, "BATCH_SIZE", 2)
    ids = [await env.add_user() for _ in range(4)]
    reconcile._states[1] = settled_state()
    fence, holds = env.node.full_sync_fence, []

    @contextlib.asynccontextmanager
    async def spied_fence(*args, **kwargs):
        async with fence(*args, **kwargs) as held:
            holds.append(held)
            yield held

    def lease_runs_out(users):
        holds[-1].until = 0.0  # its lease ran out while the first batch was sent

    monkeypatch.setattr(env.node, "full_sync_fence", spied_fence)
    env.state.answer = lease_runs_out
    await run_pass(env)

    assert env.state.sent() == [str(user_id) for user_id in ids[:2]]
    assert not node_state().failed  # another worker may hold the fence now: a skip
    assert not await env.node.full_sync_in_progress()


async def test_a_start_in_progress_holds_the_pass_back(env, monkeypatch):
    await env.add_user()
    reconcile._states[1] = settled_state()
    monkeypatch.setattr(NodeOperation, "_in_flight_connects", {1})
    assert await reconcile.reconcile_node_users() is None  # not even started
    assert env.state.deltas == []

    NodeOperation._in_flight_connects.clear()
    await run_pass(env)
    assert env.state.deltas


async def test_a_start_begun_while_the_chunk_waited_for_the_lock_stops_it(env):
    user_id = await env.add_user()

    async def read(emails):
        return await node_sync.refresh_node_users("1", emails)

    with pytest.raises(UserSyncPreemptedError, match="being started"):
        await env.manager.reconcile_user_chunk(
            1, env.node, [str(user_id)], read, abort=lambda: "the node is being started"
        )
    assert env.state.deltas == []
    assert not await env.node.full_sync_in_progress()


async def test_a_cancel_lost_in_an_await_that_suppresses_it_is_repeated(env, monkeypatch):
    monkeypatch.setattr(reconcile, "CHUNK_SIZE", 1)
    ids = [await env.add_user() for _ in range(2)]
    reconcile._states[1] = settled_state()
    in_pause = asyncio.Event()

    async def pause_that_swallows_a_cancel(node):
        # Like a fence being lifted: an await that suppresses a cancellation landing in it.
        in_pause.set()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(5)
        env.state.gate = asyncio.Event()  # the next chunk would then hang on the node

    monkeypatch.setattr(reconcile, "_pause_between_chunks", pause_that_swallows_a_cancel)
    task = await reconcile.reconcile_node_users()
    await asyncio.wait_for(in_pause.wait(), 5)

    await asyncio.wait_for(env.manager.cancel_user_reconcile(1), 3)

    await asyncio.wait_for(task, 5)
    assert not env.manager.user_reconcile_running(1)
    assert env.state.sent() == [str(ids[0])]
    assert not await env.node.full_sync_in_progress()


@pytest.mark.parametrize("step", ["begin", "end"])
async def test_cancel_while_the_fence_is_taken_or_lifted_still_lifts_it(env, monkeypatch, step):
    await env.add_user()
    reconcile._states[1] = settled_state()
    name = f"{step}_full_sync"
    original = getattr(env.store, name)
    reached = asyncio.Event()

    async def slow_store_call(*args, **kwargs):
        if step == "begin":
            token = await original(*args, **kwargs)  # the store took the fence ...
            reached.set()
            await asyncio.sleep(0.3)  # ... and its answer is still on its way
            return token
        reached.set()
        await asyncio.sleep(0.3)  # the release is still on its way to the store
        return await original(*args, **kwargs)

    monkeypatch.setattr(env.store, name, slow_store_call)
    capture = env.node.capture_queued_work
    captures = []

    async def counted_capture(*args, **kwargs):
        captures.append(1)
        return await capture(*args, **kwargs)

    monkeypatch.setattr(env.node, "capture_queued_work", counted_capture)
    task = await reconcile.reconcile_node_users()
    await asyncio.wait_for(reached.wait(), 5)

    await asyncio.wait_for(env.manager.cancel_user_reconcile(1), 5)

    await asyncio.wait_for(task, 5)
    assert not await env.node.full_sync_in_progress()  # not held until its lease runs out
    if step == "begin":
        # Cancelled while the fence was being taken: nothing is captured, read or sent.
        assert captures == [] and env.state.deltas == []


async def test_timeout_error_from_elsewhere_is_not_reported_as_the_chunk_limit(env, monkeypatch, caplog):
    for _ in range(2):
        await env.add_user()
    reconcile._states[1] = settled_state()
    monkeypatch.setattr(
        reconcile, "refresh_node_users", AsyncMock(side_effect=TimeoutError("database query timed out"))
    )
    caplog.set_level(logging.WARNING)

    await run_pass(env)

    [warning] = warnings_with(caplog, "was interrupted")
    assert "TimeoutError: database query timed out" in warning
    assert "took over" not in warning
    assert node_state().failed


async def test_a_user_that_cannot_be_read_is_skipped_and_the_rest_is_sent(env, monkeypatch, caplog):
    ids = [await env.add_user() for _ in range(5)]
    bad = str(ids[3])
    reconcile._states[1] = settled_state()
    read = reconcile.refresh_node_users

    async def read_or_fail(node_id, emails):
        if bad in emails:
            raise ValueError("broken proxy settings")
        return await read(node_id, emails)

    monkeypatch.setattr(reconcile, "refresh_node_users", read_or_fail)
    caplog.set_level(logging.WARNING)

    await run_pass(env)

    assert set(env.state.users) == {str(user_id) for user_id in ids} - {bad}
    [warning] = warnings_with(caplog, "could not be read")
    assert f"User {bad} " in warning and "node 1" in warning and "broken proxy settings" in warning
    assert not node_state().failed


async def test_a_database_that_cannot_be_read_at_all_interrupts_the_pass(env, monkeypatch, caplog):
    for _ in range(3):
        await env.add_user()
    reconcile._states[1] = settled_state()
    monkeypatch.setattr(reconcile, "refresh_node_users", AsyncMock(side_effect=ConnectionError("database is down")))
    caplog.set_level(logging.WARNING)

    await run_pass(env)

    assert env.state.deltas == []
    assert node_state().failed
    assert warnings_with(caplog, "could not be read") == []  # one warning for the pass, not one per user
    assert len(warnings_with(caplog, "database is down")) == 1


async def test_a_node_skipped_ten_times_in_a_row_is_warned_about_hourly(env, caplog):
    await env.add_user()
    reconcile._states[1] = settled_state()
    caplog.set_level(logging.WARNING)

    async def skipped_pass():
        await reconcile._run_pass(1, env.node, node_state(), sweep=False)

    async with env.node.full_sync_fence():  # held elsewhere the whole time
        for _ in range(reconcile.SKIP_WARN_AFTER - 1):
            await skipped_pass()
        assert warnings_with(caplog, "in a row") == []
        await skipped_pass()
        [warning] = warnings_with(caplog, "in a row")
        assert f"node 1 was skipped {reconcile.SKIP_WARN_AFTER} times" in warning and "in progress" in warning
        for _ in range(20):
            await skipped_pass()
        assert len(warnings_with(caplog, "in a row")) == 1  # not again within the hour
        node_state().skip_warned_at -= reconcile.SKIP_WARN_EVERY
        await skipped_pass()
        assert len(warnings_with(caplog, "in a row")) == 2

    await run_pass(env)
    assert node_state().skips == 0  # a pass that ran to its end starts the count over


def counted_reads(monkeypatch, fail) -> list[int]:
    """Replace the reconciliation read; ``fail(emails)`` returns an error to raise, or None to read."""
    calls: list[int] = []
    read = reconcile.refresh_node_users

    async def read_or_fail(node_id, emails):
        calls.append(len(emails))
        if (exc := fail(emails)) is not None:
            raise exc
        return await read(node_id, emails)

    monkeypatch.setattr(reconcile, "refresh_node_users", read_or_fail)
    return calls


async def test_a_database_connection_error_is_read_once_not_user_by_user(env, monkeypatch, caplog):
    for _ in range(6):
        await env.add_user()
    reconcile._states[1] = settled_state()
    error = OperationalError("SELECT", {}, ConnectionRefusedError("connection refused"))
    calls = counted_reads(monkeypatch, lambda emails: error)
    caplog.set_level(logging.WARNING)

    await run_pass(env)

    assert calls == [6]
    assert node_state().failed and env.state.deltas == []
    assert warnings_with(caplog, "could not be read") == []


async def test_every_user_failing_costs_a_few_reads_not_one_per_user(env, monkeypatch, caplog):
    for _ in range(200):
        await env.add_user()
    reconcile._states[1] = settled_state()
    calls = counted_reads(monkeypatch, lambda emails: ValueError("broken serializer"))
    caplog.set_level(logging.WARNING)

    await run_pass(env)

    assert len(calls) <= reconcile.MAX_READS_PER_CHUNK  # not 2n - 1 = 399 reads
    assert node_state().failed and env.state.deltas == []
    assert warnings_with(caplog, "could not be read") == []


async def test_two_unreadable_neighbours_are_skipped_and_the_rest_is_sent(env, monkeypatch, caplog):
    ids = [await env.add_user() for _ in range(4)]
    bad = {str(ids[0]), str(ids[1])}  # one half of the chunk, entirely
    reconcile._states[1] = settled_state()
    counted_reads(monkeypatch, lambda emails: ValueError("broken") if bad & set(emails) else None)
    caplog.set_level(logging.WARNING)

    await run_pass(env)

    assert set(env.state.users) == {str(ids[2]), str(ids[3])}
    assert len(warnings_with(caplog, "could not be read")) == 2
    assert not node_state().failed


async def test_unreadable_neighbours_do_not_stop_the_other_users_and_chunks(env, monkeypatch):
    monkeypatch.setattr(reconcile, "CHUNK_SIZE", 7)
    ids = [await env.add_user() for _ in range(10)]
    bad = {str(ids[0]), str(ids[1]), str(ids[2])}
    reconcile._states[1] = settled_state()
    counted_reads(monkeypatch, lambda emails: ValueError("broken") if bad & set(emails) else None)

    await run_pass(env)

    assert set(env.state.users) == {str(user_id) for user_id in ids[3:]}
    assert not node_state().failed


async def test_reads_of_a_chunk_are_bounded_and_the_unread_rest_is_skipped(env, monkeypatch, caplog):
    monkeypatch.setattr(reconcile, "MAX_READS_PER_CHUNK", 6)
    ids = [await env.add_user() for _ in range(16)]
    good = str(ids[0])
    reconcile._states[1] = settled_state()
    window_start = node_state().last_success_at
    calls = counted_reads(monkeypatch, lambda emails: ValueError("broken") if set(emails) != {good} else None)
    caplog.set_level(logging.WARNING)

    await run_pass(env)

    assert len(calls) == 6
    assert set(env.state.users) == {good}
    assert len(warnings_with(caplog, "Too many users could not be read")) == 1
    assert not node_state().failed
    assert node_state().last_success_at == window_start


async def test_a_pass_with_a_rejected_batch_does_not_move_its_window(env, monkeypatch):
    keep = await env.add_user()
    expired = await env.add_user()
    await env.set_status(expired, UserStatus.expired, datetime.now(UTC) - timedelta(minutes=10))
    env.state.users = {str(keep): [INBOUND], str(expired): [INBOUND]}  # its removal never arrived
    reconcile._states[1] = settled_state()
    window_start = node_state().last_success_at
    env.state.answer = lambda users: FailedUsers(users, rejected=True, detail="failed to update users: bad")

    await run_pass(env)  # the node rejects the batch with the removal
    assert str(expired) in env.state.users
    assert node_state().last_success_at == window_start

    env.state.answer = None
    make_due()
    await run_pass(env)  # the next frequent pass still covers the status change

    assert env.state.users == {str(keep): [INBOUND]}
    assert node_state().last_success_at > window_start


async def test_an_unreadable_user_is_warned_about_once_a_day(env, monkeypatch, caplog):
    ids = [await env.add_user() for _ in range(3)]
    bad = str(ids[1])
    reconcile._states[1] = settled_state()
    counted_reads(monkeypatch, lambda emails: ValueError("broken") if bad in emails else None)
    caplog.set_level(logging.WARNING)

    for _ in range(3):
        await run_pass(env)
        make_due()
    assert len(warnings_with(caplog, "could not be read")) == 1

    node_state().unreadable_warned_at[bad] -= reconcile.UNREADABLE_WARN_EVERY
    await run_pass(env)
    assert len(warnings_with(caplog, "could not be read")) == 2


async def test_a_pass_that_skipped_a_user_does_not_move_its_window(env, monkeypatch):
    keep = await env.add_user()
    expired = await env.add_user()
    await env.set_status(expired, UserStatus.expired, datetime.now(UTC) - timedelta(minutes=10))
    env.state.users = {str(keep): [INBOUND], str(expired): [INBOUND]}  # its removal never arrived
    reconcile._states[1] = settled_state()
    window_start = node_state().last_success_at
    broken = {"on": True}
    counted_reads(monkeypatch, lambda emails: ValueError("broken") if broken["on"] and str(expired) in emails else None)

    await run_pass(env)  # the expired user cannot be read this time
    assert str(expired) in env.state.users
    assert node_state().last_success_at == window_start

    broken["on"] = False
    make_due()
    await run_pass(env)  # the next frequent pass still covers its status change

    assert env.state.users == {str(keep): [INBOUND]}
    assert node_state().last_success_at > window_start  # a clean pass moves the window


async def test_the_window_of_a_frequent_pass_is_at_most_a_day(env, monkeypatch):
    reconcile._states[1] = settled_state()
    node_state().last_success_at = datetime.now(UTC) - timedelta(days=5)
    seen = []
    ids_to_reconcile = reconcile._ids_to_reconcile

    async def spy(since):
        seen.append(since)
        return await ids_to_reconcile(since)

    monkeypatch.setattr(reconcile, "_ids_to_reconcile", spy)

    await run_pass(env)

    [since] = seen
    assert datetime.now(UTC) - since < reconcile.FIRST_PASS_WINDOW + timedelta(minutes=1)


async def test_a_full_sync_in_progress_counts_as_a_skipped_pass(env, caplog):
    await env.add_user()
    reconcile._states[1] = settled_state()
    caplog.set_level(logging.WARNING)

    async with env.node.full_sync_fence():
        for _ in range(reconcile.SKIP_WARN_AFTER):
            make_due()
            assert await reconcile.reconcile_node_users() is None

    assert node_state().skips == reconcile.SKIP_WARN_AFTER
    [warning] = warnings_with(caplog, "in a row")
    assert "full user sync" in warning


def asyncio_errors(caplog) -> list[str]:
    gc.collect()  # "Task exception was never retrieved" is logged when the task is collected
    return [r.getMessage() for r in caplog.records if r.name == "asyncio" and r.levelno >= logging.ERROR]


async def test_a_chunk_failing_after_its_cancellation_logs_no_asyncio_error(env, monkeypatch, caplog):
    await env.add_user()
    reconcile._states[1] = settled_state()
    reached = asyncio.Event()

    async def fence_taken_elsewhere_meanwhile(*args, **kwargs):
        reached.set()
        await asyncio.sleep(0.3)  # then no token: FullSyncConflictError in the chunk, after it was cancelled

    monkeypatch.setattr(env.store, "begin_full_sync", fence_taken_elsewhere_meanwhile)
    monkeypatch.setattr(env.manager, "logger", MagicMock())
    caplog.set_level(logging.DEBUG)
    task = await reconcile.reconcile_node_users()
    await asyncio.wait_for(reached.wait(), 5)

    await asyncio.wait_for(env.manager.cancel_user_reconcile(1), 5)

    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert asyncio_errors(caplog) == []
    [(args, _)] = [call for call in env.manager.logger.debug.call_args_list if "chunk ended with" in call.args[0]]
    assert args[1] == "FullSyncConflictError"  # retrieved and noted, not lost


async def start_chunk(env, read) -> asyncio.Task:
    user_id = await env.add_user()
    return asyncio.create_task(env.manager.reconcile_user_chunk(1, env.node, [str(user_id)], read))


async def test_a_chunk_that_swallows_the_first_cancel_is_cancelled_again(env):
    reached = asyncio.Event()

    async def read(emails):
        reached.set()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(5)  # an await that suppresses the first cancellation ...
        await asyncio.Event().wait()  # ... and then hangs

    task = await start_chunk(env, read)
    await asyncio.wait_for(reached.wait(), 5)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)  # well before FENCED_CHUNK_STOP_LIMIT

    assert not await env.node.full_sync_in_progress()
    assert env.manager._lingering_reconcile_chunks == {}


async def swallow_cancels_while(control) -> None:
    """Swallow every cancellation while ``control.on`` (for 5 s at most, so a failed test cannot hang)."""
    loop = asyncio.get_running_loop()
    until = loop.time() + 5
    while control.on and loop.time() < until:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(0.02)


def stubborn_read(env):
    """A read that swallows every cancellation while ``on``, then reads or hangs."""
    control = SimpleNamespace(on=True, hang=False, reached=asyncio.Event())

    async def read(emails):
        control.reached.set()
        await swallow_cancels_while(control)
        if control.hang:
            await asyncio.sleep(5)  # hangs, but ends on a cancel (and, in a failed test, on its own)
        return await node_sync.refresh_node_users("1", emails)

    return control, read


async def test_a_chunk_that_outlives_its_cancellation_sends_nothing_more(env, monkeypatch, caplog):
    monkeypatch.setattr(node_package, "FENCED_CHUNK_STOP_LIMIT", 0.3)
    control, read = stubborn_read(env)
    caplog.set_level(logging.WARNING)
    task = await start_chunk(env, read)
    await asyncio.wait_for(control.reached.wait(), 5)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)

    [warning] = warnings_with(caplog, "was not lifted within")
    assert "stays up while" in warning and "lease" not in warning
    [lingering] = env.manager._lingering_reconcile_chunks[1]
    assert await env.node.full_sync_in_progress()

    control.on = False  # the read returns after all
    await asyncio.wait_for(asyncio.gather(lingering, return_exceptions=True), 3)

    assert env.state.deltas == []  # nothing is sent after the cancellation
    assert not await env.node.full_sync_in_progress()
    assert env.manager._lingering_reconcile_chunks == {}


@pytest.mark.parametrize("how", ["remove_node", "shutdown"])
async def test_a_lingering_chunk_is_stopped_with_its_node_or_the_panel(env, monkeypatch, how):
    monkeypatch.setattr(node_package, "FENCED_CHUNK_STOP_LIMIT", 0.3)
    control, read = stubborn_read(env)
    control.hang = True
    task = await start_chunk(env, read)
    await asyncio.wait_for(control.reached.wait(), 5)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    [lingering] = env.manager._lingering_reconcile_chunks[1]
    control.on = False  # now hangs, but would end on a cancel

    if how == "remove_node":
        await asyncio.wait_for(env.manager.remove_node(1, remote_stop=False), 5)
    else:
        await asyncio.wait_for(reconcile.stop_node_user_reconcile(), 5)

    assert lingering.done()
    assert env.manager._lingering_reconcile_chunks == {}
    assert not await env.node.full_sync_in_progress()


async def test_a_pass_that_does_not_stop_in_time_is_warned_about_and_left(env, monkeypatch, caplog):
    await env.add_user()
    reconcile._states[1] = settled_state()
    control = SimpleNamespace(on=True, reached=asyncio.Event())

    async def ids_to_reconcile_that_swallows_cancels(since):
        control.reached.set()
        await swallow_cancels_while(control)
        return []

    monkeypatch.setattr(reconcile, "_ids_to_reconcile", ids_to_reconcile_that_swallows_cancels)
    caplog.set_level(logging.WARNING)
    task = await reconcile.reconcile_node_users()
    await asyncio.wait_for(control.reached.wait(), 5)

    await asyncio.wait_for(env.manager.cancel_user_reconcile(1, limit=0.3), 2)

    [warning] = warnings_with(caplog, "did not stop within")
    assert "node 1" in warning and "0.3s" in warning
    assert not task.done()
    control.on = False
    await asyncio.wait_for(task, 5)

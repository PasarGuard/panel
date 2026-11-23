"""The Sync button re-sends a node's users through deltas and leaves its core running."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from PasarGuardNodeBridge import Health
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser
from PasarGuardNodeBridge.controller import FailedUsers

from app.db.models import NodeStatus, UserStatus
from app.jobs import node_user_reconcile as reconcile
from app.models.core import CoreType
from app.node import UserSyncPreemptedError, worker as worker_module
from app.operation import OperatorType, node as operation_node
from app.operation.node import NodeOperation
from tests.test_node_user_reconcile import INBOUND, env, node_state, settled_state  # noqa: F401


@pytest.fixture
def operator(env, monkeypatch):  # noqa: F811
    """The API operator over the harness node; the snapshot carries every active user, as in production."""
    operator = NodeOperation(operator_type=OperatorType.API)
    db_node = SimpleNamespace(id=1, name="n1", status=NodeStatus.connected, core_config_id=1)
    monkeypatch.setattr(operator, "get_validated_node", AsyncMock(return_value=db_node))
    monkeypatch.setattr(operation_node, "NodeResponse", SimpleNamespace(model_validate=lambda node: node))

    async def users_map(db, core_ids, lazy=False):
        async def load():
            emails = await reconcile._ids_to_reconcile(datetime.now(UTC))
            return [ProtoUser(email=str(user_id), inbounds=[INBOUND]) for user_id in emails]

        return {}, {1: load}

    monkeypatch.setattr(operator, "_get_core_users_map", users_map)
    update_status = AsyncMock()
    monkeypatch.setattr(operation_node, "update_node_status", update_status)
    operator.db_node = db_node
    operator.update_status = update_status
    operator.db = SimpleNamespace(close=AsyncMock())  # the request's session
    return operator


async def sync(operator, **kwargs):
    return await asyncio.wait_for(operator.sync_node_users(operator.db, 1, flush_users=True, **kwargs), 10)


async def sync_error(operator, **kwargs) -> HTTPException:
    with pytest.raises(HTTPException) as exc_info:
        await sync(operator, **kwargs)
    return exc_info.value


# -------------------------------------------------------------------------------- the two modes
async def test_sync_button_sends_deltas_and_never_the_snapshot(env, operator):  # noqa: F811
    deleted = await env.add_user()  # a lower id than the highest existing one: in the sweep
    await env.remove_user(deleted)
    present, missing = await env.add_user(), await env.add_user()
    expired = await env.add_user(UserStatus.expired, changed=datetime.now(UTC) - timedelta(days=30))
    env.state.users = {str(present): [INBOUND], str(expired): [INBOUND], str(deleted): [INBOUND]}

    assert await sync(operator) is operator.db_node

    assert env.state.snapshots == []  # no SyncUsers: the core is not restarted
    assert set(env.state.users) == {str(present), str(missing)}  # lost addition and removals repaired
    assert {str(expired), str(deleted)} <= set(env.state.sent())  # the sweep ran: inactive and deleted ids
    operator.update_status.assert_not_awaited()


async def test_full_sync_sends_the_snapshot_as_before(env, operator):  # noqa: F811
    user_id = await env.add_user()

    assert await sync(operator, full=True) is operator.db_node

    assert env.state.snapshots == [[str(user_id)]]
    assert env.state.deltas == []
    operator.db.close.assert_not_awaited()  # the snapshot path keeps its session as before


async def test_full_sync_interrupted_keeps_its_message(env, operator, monkeypatch):  # noqa: F811
    await env.add_user()
    monkeypatch.setattr(env.manager, "sync_full", AsyncMock(side_effect=UserSyncPreemptedError("preempted")))

    error = await sync_error(operator, full=True)

    assert error.status_code == 409
    # A Start does not interrupt a full sync (it answers 409 on the fence), so it is not named.
    assert error.detail == "User sync was interrupted by a change to the node's connection or its removal, retry"


async def test_sync_gives_the_request_connection_back_before_the_pass(env, operator, monkeypatch):  # noqa: F811
    await env.add_user()
    send_chunk = env.manager.reconcile_user_chunk
    closed_before_chunk = []

    async def chunk(*args, **kwargs):
        closed_before_chunk.append(operator.db.close.await_count)
        return await send_chunk(*args, **kwargs)

    monkeypatch.setattr(env.manager, "reconcile_user_chunk", chunk)

    assert await sync(operator) is operator.db_node

    assert closed_before_chunk == [1]


@pytest.mark.parametrize("case", ["old", "unknown_version", "mtproto", "unhealthy", "no_fence"])
async def test_node_that_cannot_take_deltas_gets_the_snapshot(env, operator, monkeypatch, case):  # noqa: F811
    await env.add_user()
    if case == "old":
        await env.node.set_reported_versions("0.5.4", "26.3.27")
    elif case == "unknown_version":
        await env.node.set_reported_versions("dev", "26.3.27")
    elif case == "mtproto":
        env.cores[1] = SimpleNamespace(type=CoreType.mtproto)
    elif case == "no_fence":
        monkeypatch.setattr(env.manager, "_supports_shared_sync", lambda node: False)
    else:
        await env.node.set_health(Health.BROKEN)
    sync_full = AsyncMock(return_value=env.node)
    monkeypatch.setattr(env.manager, "sync_full", sync_full)

    await sync(operator)

    sync_full.assert_awaited_once()
    assert sync_full.await_args.kwargs["flush_pending"] is True
    assert env.state.deltas == []


# ---------------------------------------------------------------------------- concurrent work
async def test_running_background_pass_gives_way_to_the_sync_button(env, operator):  # noqa: F811
    user_id = await env.add_user()
    reconcile._states[1] = settled_state()
    env.state.gate = asyncio.Event()
    background = await reconcile.reconcile_node_users()
    await asyncio.wait_for(env.state.delta_started.wait(), 5)

    manual = asyncio.create_task(sync(operator))
    await asyncio.wait_for(background, 5)  # cancelled by the manual pass, not waited for
    assert not manual.done()
    env.state.gate.set()

    assert await manual is operator.db_node
    assert str(user_id) in env.state.users
    assert env.state.snapshots == []
    assert not node_state().failed  # the background pass was stopped, not failed
    assert node_state().last_success_at > settled_state().last_success_at  # and the manual one counted


async def test_second_sync_of_the_same_node_answers_409(env, operator):  # noqa: F811
    user_id = await env.add_user()
    env.state.gate = asyncio.Event()
    first = asyncio.create_task(sync(operator))
    await asyncio.wait_for(env.state.delta_started.wait(), 5)

    error = await sync_error(operator)

    assert error.status_code == 409 and "already in progress" in error.detail
    assert not first.done()  # the first pass is not cancelled
    env.state.gate.set()
    assert await first is operator.db_node
    assert str(user_id) in env.state.users
    operator.update_status.assert_not_awaited()


async def test_start_during_the_sync_answers_409_and_keeps_the_node_status(env, operator):  # noqa: F811
    await env.add_user()
    env.state.gate = asyncio.Event()
    manual = asyncio.create_task(sync(operator))
    await asyncio.wait_for(env.state.delta_started.wait(), 5)
    info = SimpleNamespace(node_version="0.5.5", core_version="26.3.27", started=True)
    env.node.start = AsyncMock(return_value=info)
    db_node = SimpleNamespace(id=1, name="n1", keep_alive=0, default_timeout=10)
    core = SimpleNamespace(type=CoreType.xray, to_str=lambda: "{}", exclude_inbound_tags=[])

    result = await NodeOperation._start_or_attach_node(
        env.node, db_node, core, [], 1, force_start=True, stop_first=False
    )

    assert result is info
    with pytest.raises(HTTPException) as exc_info:
        await manual
    assert exc_info.value.status_code == 409 and "a Start" in exc_info.value.detail
    operator.update_status.assert_not_awaited()
    assert reconcile._manual == set()


async def test_background_pass_that_does_not_stop_answers_409(env, operator, monkeypatch):  # noqa: F811
    await env.add_user()
    monkeypatch.setattr(env.manager, "cancel_user_reconcile", AsyncMock())  # gave up after its time limit
    monkeypatch.setattr(env.manager, "user_reconcile_running", lambda node_id: True)
    reconcile._states[1] = before = settled_state()
    window = before.last_success_at

    error = await sync_error(operator)

    assert error.status_code == 409 and "still running" in error.detail
    assert env.state.deltas == [] and env.state.snapshots == []
    assert node_state().last_success_at == window
    assert reconcile._manual == set()


async def test_cancelled_request_frees_the_node_for_the_next_sync(env, operator):  # noqa: F811
    user_id = await env.add_user()
    env.state.gate = asyncio.Event()
    first = asyncio.create_task(sync(operator))
    await asyncio.wait_for(env.state.delta_started.wait(), 5)

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert reconcile._manual == set()

    env.state.gate.set()
    assert await sync(operator) is operator.db_node
    assert str(user_id) in env.state.users


async def test_node_turning_unhealthy_mid_pass_answers_409(env, operator, monkeypatch):  # noqa: F811
    monkeypatch.setattr(reconcile, "CHUNK_SIZE", 2)
    ids = [await env.add_user() for _ in range(6)]
    send_chunk = env.manager.reconcile_user_chunk

    async def chunk_then_break(*args, **kwargs):
        result = await send_chunk(*args, **kwargs)
        await env.node.set_health(Health.BROKEN)
        return result

    monkeypatch.setattr(env.manager, "reconcile_user_chunk", chunk_then_break)

    error = await sync_error(operator)

    assert error.status_code == 409 and "not healthy" in error.detail
    assert env.state.sent() == [str(user_id) for user_id in ids[:2]]
    operator.update_status.assert_not_awaited()
    assert reconcile._manual == set()


async def test_fence_held_elsewhere_answers_409_and_sends_nothing(env, operator):  # noqa: F811
    await env.add_user()
    async with env.node.full_sync_fence():
        error = await sync_error(operator)
    assert error.status_code == 409
    assert env.state.deltas == [] and env.state.snapshots == []
    operator.update_status.assert_not_awaited()


# --------------------------------------------------------------------------------- failures
async def test_rejected_users_are_not_a_success_and_keep_the_background_window(env, operator, monkeypatch):  # noqa: F811
    monkeypatch.setattr(reconcile, "BATCH_SIZE", 1)
    ids = [await env.add_user() for _ in range(4)]
    bad = str(ids[1])
    env.state.answer = lambda users: (
        FailedUsers(users, rejected=True, detail="failed to update users: bad")
        if any(u.email == bad for u in users)
        else None
    )
    reconcile._states[1] = before = settled_state()
    window, swept = before.last_success_at, before.last_sweep_at

    error = await sync_error(operator)

    assert error.status_code == 502
    assert "rejected 1 user(s)" in error.detail and "full=true" in error.detail
    assert set(env.state.users) == {str(user_id) for user_id in ids} - {bad}  # the others were sent
    assert node_state().last_success_at == window and node_state().last_sweep_at == swept
    operator.update_status.assert_not_awaited()
    assert reconcile._manual == set()


async def test_unreadable_user_is_not_a_success(env, operator, monkeypatch):  # noqa: F811
    ids = [await env.add_user() for _ in range(3)]
    bad = str(ids[0])
    refresh = reconcile.refresh_node_users

    async def refresh_or_fail(node_id, emails):
        if bad in emails:
            raise ValueError("broken settings")
        return await refresh(node_id, emails)

    monkeypatch.setattr(reconcile, "refresh_node_users", refresh_or_fail)

    error = await sync_error(operator)

    assert error.status_code == 500 and "1 user(s) could not be read" in error.detail
    assert set(env.state.users) == {str(user_id) for user_id in ids[1:]}


async def test_transport_error_answers_502_and_keeps_the_node_status(env, operator):  # noqa: F811
    await env.add_user()
    env.state.answer = lambda users: FailedUsers(users, rejected=False, detail="UNAVAILABLE")

    error = await sync_error(operator)

    assert error.status_code == 502 and "UNAVAILABLE" in error.detail
    operator.update_status.assert_not_awaited()
    assert env.state.snapshots == []
    assert reconcile._manual == set()


async def test_node_not_connected_answers_406(env, operator):  # noqa: F811
    operator.db_node.status = NodeStatus.error
    error = await sync_error(operator)
    assert error.status_code == 406
    assert env.state.deltas == [] and env.state.snapshots == []


# ------------------------------------------------------------------- the background job's state
async def test_successful_sync_moves_the_background_state(env, operator):  # noqa: F811
    await env.add_user()
    reconcile._states[1] = state = reconcile._NodeState(next_due=0.0, connected_at=time.monotonic())
    state.after_connect = state.sweep_after_connect = True
    before = datetime.now(UTC)

    await sync(operator)

    assert node_state().last_success_at >= before
    assert node_state().last_sweep_at is not None and not node_state().sweep_after_connect
    assert not node_state().after_connect
    assert node_state().next_due > time.monotonic() + 1800 - 60
    assert await reconcile.reconcile_node_users() is None  # nothing due right after


async def test_sync_on_a_process_without_background_state_adds_none(env, operator):  # noqa: F811
    await env.add_user()

    await sync(operator)

    # An entry made here would skip the pass after connect once this process leads the job.
    assert 1 not in reconcile._states


@pytest.mark.parametrize("leader", [True, False])
async def test_sync_works_with_the_job_off_and_on_any_worker(env, operator, monkeypatch, leader):  # noqa: F811
    monkeypatch.setattr(reconcile.job_settings, "node_user_reconcile_interval", 0)
    monkeypatch.setattr(reconcile, "CHUNK_SIZE", 2)
    env.leader["value"] = leader
    ids = [await env.add_user() for _ in range(5)]

    await sync(operator)

    assert set(env.state.users) == {str(user_id) for user_id in ids}
    assert env.state.snapshots == []


async def test_sync_does_not_wait_out_the_background_pauses(env, operator, monkeypatch):  # noqa: F811
    monkeypatch.setattr(reconcile, "CHUNK_GAP_MIN", 1.0)
    monkeypatch.setattr(reconcile, "CHUNK_GAP_MAX", 5.0)
    monkeypatch.setattr(reconcile, "BATCH_PAUSE", 0.2)
    ids = [await env.add_user() for _ in range(1000)]
    pauses = []
    send_chunk = env.manager.reconcile_user_chunk

    async def record_pause(*args, **kwargs):
        pauses.append(kwargs["pause"])
        return await send_chunk(*args, **kwargs)

    pause = reconcile._pause_between_chunks
    gaps = []

    async def timed_gap(node, **kwargs):
        started = time.monotonic()
        await pause(node, **kwargs)
        gaps.append(time.monotonic() - started)

    monkeypatch.setattr(env.manager, "reconcile_user_chunk", record_pause)
    monkeypatch.setattr(reconcile, "_pause_between_chunks", timed_gap)

    await sync(operator)

    assert pauses and set(pauses) == {0.0}
    assert len(gaps) == 1 and gaps[0] < 0.5  # nothing queued: no gap, though the background one is 1 s
    assert len(env.state.users) == len(ids)


async def test_edit_queued_during_the_sync_goes_out_between_chunks(env, operator, monkeypatch):  # noqa: F811
    monkeypatch.setattr(reconcile, "CHUNK_SIZE", 2)
    env.node._sync_poll_interval = 1.0  # as in production: the queue worker sleeps while a fence is up
    for _ in range(4):
        await env.add_user()
    send_chunk = env.manager.reconcile_user_chunk
    bought = []
    delivered_before_next_chunk = []

    async def chunk(node_id, node, emails, read, **kwargs):
        if bought:
            delivered_before_next_chunk.append(bought[0] in env.state.users)
            return await send_chunk(node_id, node, emails, read, **kwargs)

        async def read_then_buy(batch):
            users = await read(batch)
            if not bought:  # a purchase while the chunk holds the fence: its user is queued
                bought.append(str(await env.add_user()))
                await env.node.update_user(ProtoUser(email=bought[0], inbounds=[INBOUND]))
                await asyncio.sleep(0.05)  # the queue worker finds the fence up and sleeps
            return users

        return await send_chunk(node_id, node, emails, read_then_buy, **kwargs)

    monkeypatch.setattr(env.manager, "reconcile_user_chunk", chunk)

    await sync(operator)

    assert delivered_before_next_chunk == [True]  # not held back until the whole pass ended
    assert bought[0] in env.state.users


# --------------------------------------------------------------------------- other paths in
async def test_api_process_forwards_the_mode_to_the_node_worker(monkeypatch):
    operator = NodeOperation(operator_type=OperatorType.API)
    publish = AsyncMock()
    monkeypatch.setattr(operation_node.node_nats_client, "publish", publish)
    monkeypatch.setattr(operator, "get_validated_node", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(operation_node, "NodeResponse", SimpleNamespace(model_validate=lambda node: node))

    await operator._sync_node_users_remote(object(), 3, True, full=True)
    await operator._sync_node_users_remote(object(), 3, True)

    assert [call.args[1] for call in publish.await_args_list] == [
        {"node_id": 3, "flush_users": True, "full": True},
        {"node_id": 3, "flush_users": True, "full": False},
    ]


@pytest.mark.parametrize(("data", "full"), [({"full": True}, True), ({}, False)])
async def test_node_worker_passes_the_mode_on(monkeypatch, data, full):
    worker = object.__new__(worker_module.NodeWorkerService)
    worker._node_operator = SimpleNamespace(sync_node_users=AsyncMock())
    monkeypatch.setattr(worker_module.core_manager, "_reload_from_cache", AsyncMock())

    class _Db:
        async def __aenter__(self):
            return "db"

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(worker_module, "GetDB", _Db)

    await worker._sync_node_users({"node_id": 4, "flush_users": True, **data})

    worker._node_operator.sync_node_users.assert_awaited_once_with("db", node_id=4, flush_users=True, full=full)

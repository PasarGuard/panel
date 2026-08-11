import asyncio
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from PasarGuardNodeBridge import Health, NodeAPIError
from PasarGuardNodeBridge.common import service_pb2 as service
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser
from PasarGuardNodeBridge.rest import Node as RestBridgeNode
from PasarGuardNodeBridge.storage import LifecycleOperation, LifecycleStatus, NodeLifecycleState
from sqlalchemy.dialects import mysql

import app.node as node_module
from app.db.models import NodeConnectionType, NodeStatus
from app.models.core import CoreType
from app.models.node import BulkNodeSelection, NodeLifecycleRecovery
from app.nats.node_rpc import encode_node_command
from app.node import NodeManager, sync as node_sync_module, worker as node_worker_module
from app.node.user import _serialize_user_for_node
from app.operation import OperatorType
from app.operation.node import NodeOperation
from role import Role


def _healthy_runtime_node() -> AsyncMock:
    node = AsyncMock()
    node.get_health.return_value = Health.HEALTHY
    node._supports_chunked_sync.return_value = (True, "0.2.0")
    node.sync_users_chunked.return_value = []
    node.begin_user_revocation = AsyncMock(
        side_effect=lambda user_keys, _revocation_id: SimpleNamespace(
            active_user_keys=tuple(user_keys),
            finalized_user_keys=(),
        )
    )
    node.abort_user_revocation = AsyncMock()
    node.finalize_user_revocation = AsyncMock()
    return node


def _db_node(node_id: int = 1, bridge_id: str = "bridge-1") -> SimpleNamespace:
    return SimpleNamespace(
        id=node_id,
        bridge_id=bridge_id,
        connection_type=NodeConnectionType.rest,
        address="127.0.0.1",
        port=62050,
        api_port=62051,
        server_ca="ca",
        api_key="key",
        name=f"node-{node_id}",
        default_timeout=10,
        internal_timeout=10,
        proxy_url=None,
        usage_coefficient=1.0,
    )


@pytest.mark.asyncio
async def test_new_node_start_requires_epoch_capability_and_reconciles_snapshot():
    pg_node = AsyncMock()
    pg_node._user_sync_store = None
    pg_node.get_lifecycle_state.return_value = None
    pg_node.info.return_value = service.BaseInfoResponse(
        started=False,
        user_sync_epoch_supported=True,
    )
    started = service.BaseInfoResponse(
        started=True,
        node_version="0.4.0",
        core_version="1.0.0",
        user_sync_epoch_supported=True,
        user_sync_epoch=7,
    )
    pg_node.start.return_value = started
    db_node = SimpleNamespace(name="node-1", keep_alive=30)
    core = SimpleNamespace(type=CoreType.xray, to_str=lambda: "{}", exclude_inbound_tags=[])
    users = [ProtoUser(email="42")]

    result = await NodeOperation._start_or_attach_node(
        pg_node,
        db_node,
        core,
        users,
        service.BackendType.XRAY,
    )

    assert result is started
    pg_node.start.assert_awaited_once_with(
        config="{}",
        backend_type=service.BackendType.XRAY,
        users=users,
        keep_alive=30,
        reconcile_user_sync=True,
        exclude_inbounds=[],
    )


@pytest.mark.asyncio
async def test_new_node_start_rejects_legacy_node_before_transport():
    pg_node = AsyncMock()
    pg_node._user_sync_store = None
    pg_node.get_lifecycle_state.return_value = None
    pg_node.info.return_value = service.BaseInfoResponse(started=False)
    db_node = SimpleNamespace(name="node-1", keep_alive=30)
    core = SimpleNamespace(type=CoreType.wg, to_str=lambda: "{}")

    with pytest.raises(NodeAPIError, match="monotonic user-sync epoch fencing"):
        await NodeOperation._start_or_attach_node(
            pg_node,
            db_node,
            core,
            [],
            service.BackendType.WIREGUARD,
        )
    pg_node.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_lifecycle_is_not_auto_reconciled_from_racy_probe():
    pg_node = AsyncMock()
    pg_node._user_sync_store = None
    pg_node.get_lifecycle_state.return_value = NodeLifecycleState(
        operation=LifecycleOperation.START,
        observed=LifecycleStatus.STARTING,
    )
    pg_node.info.return_value = service.BaseInfoResponse(
        started=True,
        user_sync_epoch_supported=True,
    )

    with pytest.raises(NodeAPIError, match="explicit reconciliation is required"):
        await NodeOperation._start_or_attach_node(
            pg_node,
            SimpleNamespace(name="node-1", keep_alive=30),
            SimpleNamespace(type=CoreType.wg, to_str=lambda: "{}"),
            [],
            service.BackendType.WIREGUARD,
        )
    pg_node.reconcile_lifecycle.assert_not_awaited()
    pg_node.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_connect_409_reconciles_authoritative_users_before_connected(monkeypatch):
    pg_node = AsyncMock()
    users = [ProtoUser(email="42")]
    info = service.BaseInfoResponse(node_version="0.4.0", core_version="1.0.0")
    monkeypatch.setattr(
        NodeOperation,
        "_start_or_attach_node",
        AsyncMock(side_effect=NodeAPIError(409, "lease held")),
    )
    monkeypatch.setattr(NodeOperation, "_attach_if_running", AsyncMock(return_value=info))
    monkeypatch.setattr(node_module.node_manager, "get_node", AsyncMock(return_value=pg_node))

    result = await NodeOperation.connect_node(
        SimpleNamespace(id=1, name="node-1", status="connecting"),
        SimpleNamespace(type=CoreType.wg),
        users,
        {"42"},
    )

    assert result["status"].value == "connected"
    pg_node.reconcile_users.assert_awaited_once_with(users)


@pytest.mark.asyncio
async def test_bb503_reconcile_stale_epoch_retry_reuses_db_locked_authorization():
    from app.nats.kv_cas import MemoryCasKv
    from app.node.nats_memory import NatsUserSyncStore

    store = NatsUserSyncStore(MemoryCasKv())
    pg_node = object.__new__(RestBridgeNode)
    pg_node.node_id = "node-namespace"
    pg_node.worker_id = "worker-a"
    pg_node._user_sync_store = store
    pg_node._sync_lease_seconds = 30
    pg_node._default_timeout = 10
    pg_node._node_lock = asyncio.Lock()
    pg_node._user_sync_epoch_supported = True
    pg_node._user_sync_epoch_capability_probed = True
    epochs: list[int] = []

    async def _request(**kwargs):
        epochs.append(kwargs["proto_message"].user_sync_epoch)
        if len(epochs) == 1:
            raise NodeAPIError(412, "known stale epoch")
        return service.Empty()

    pg_node._make_request = _request
    users = [ProtoUser(email="user-sync-id")]
    async with NodeOperation._authoritative_user_reconciliation_scope(pg_node, {"user-sync-id"}):
        await pg_node.reconcile_users(users)

    assert len(epochs) == 2
    assert epochs[1] > epochs[0]


@pytest.mark.asyncio
async def test_failed_reconcile_scope_does_not_leak_unlocked_authorization():
    from app.nats.kv_cas import MemoryCasKv
    from app.node.nats_memory import NatsUserSyncStore, UserSyncLeaseLostError

    store = NatsUserSyncStore(MemoryCasKv())
    pg_node = SimpleNamespace(
        node_id="node-namespace",
        worker_id="worker-a",
        _user_sync_store=store,
    )

    with pytest.raises(RuntimeError, match="before acquire"):
        async with NodeOperation._authoritative_user_reconciliation_scope(pg_node, {"user-sync-id"}):
            raise RuntimeError("failed before acquire")

    with pytest.raises(UserSyncLeaseLostError, match="was not supplied"):
        await store.acquire_user_sync_reconciliation_lease("node-namespace", "worker-a", ["user-sync-id"], 30)


@pytest.mark.asyncio
async def test_cancelled_reconcile_scope_does_not_leak_unlocked_authorization():
    from app.nats.kv_cas import MemoryCasKv
    from app.node.nats_memory import NatsUserSyncStore, UserSyncLeaseLostError

    store = NatsUserSyncStore(MemoryCasKv())
    pg_node = SimpleNamespace(
        node_id="node-namespace",
        worker_id="worker-a",
        _user_sync_store=store,
    )
    current = asyncio.current_task()
    assert current is not None

    with pytest.raises(asyncio.CancelledError):
        async with NodeOperation._authoritative_user_reconciliation_scope(pg_node, {"user-sync-id"}):
            asyncio.get_running_loop().call_soon(current.cancel)
            await asyncio.Future()

    with pytest.raises(UserSyncLeaseLostError, match="was not supplied"):
        await store.acquire_user_sync_reconciliation_lease("node-namespace", "worker-a", ["user-sync-id"], 30)


@pytest.mark.asyncio
async def test_ambiguous_commit_fresh_membership_splits_abort_and_finalize(monkeypatch):
    removal = (ProtoUser(email="1"), ProtoUser(email="2"))
    originals = (ProtoUser(email="1", inbounds=["in"]), ProtoUser(email="2", inbounds=["in"]))
    revocation = node_sync_module.UserRevocation("delete-1-2", removal, originals)

    class Result:
        @staticmethod
        def scalars():
            return SimpleNamespace(all=lambda: ["1"])

    class DB:
        async def execute(self, _query):
            return Result()

    class DBContext:
        async def __aenter__(self):
            return DB()

        async def __aexit__(self, *_args):
            return False

    abort = AsyncMock()
    finalize = AsyncMock()
    monkeypatch.setattr(node_sync_module, "GetDB", DBContext)
    monkeypatch.setattr(node_sync_module, "_dispatch_abort_with_topology_retry", abort)
    monkeypatch.setattr(node_sync_module, "_dispatch_finalize_with_topology_retry", finalize)
    failed_db = SimpleNamespace(rollback=AsyncMock())

    await node_sync_module.resolve_user_removal_after_db_error(revocation, failed_db)

    failed_db.rollback.assert_awaited_once()
    assert [user.email for user in abort.await_args.args[0].removal_users] == ["1"]
    assert [user.email for user in finalize.await_args.args[0].removal_users] == ["2"]


@pytest.mark.asyncio
async def test_ambiguous_commit_unknown_membership_stays_fenced_for_retry(monkeypatch):
    revocation = node_sync_module.UserRevocation(
        "delete-1",
        (ProtoUser(email="1"),),
        (ProtoUser(email="1", inbounds=["in"]),),
    )

    class FailingDBContext:
        async def __aenter__(self):
            raise RuntimeError("database unavailable")

        async def __aexit__(self, *_args):
            return False

    scheduled = []
    monkeypatch.setattr(node_sync_module, "GetDB", FailingDBContext)
    monkeypatch.setattr(node_sync_module, "_schedule_resolution_retry", scheduled.append)
    abort = AsyncMock()
    finalize = AsyncMock()
    monkeypatch.setattr(node_sync_module, "_dispatch_abort_with_topology_retry", abort)
    monkeypatch.setattr(node_sync_module, "_dispatch_finalize_with_topology_retry", finalize)

    await node_sync_module.resolve_user_removal_after_db_error(revocation)

    assert scheduled == [revocation]
    abort.assert_not_awaited()
    finalize.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_lifecycle_recovery_requires_probe_match_and_expired_lease(monkeypatch):
    operation = NodeOperation(OperatorType.API)
    pg_node = AsyncMock()
    pg_node.get_lifecycle_state.return_value = NodeLifecycleState(
        operation=LifecycleOperation.START,
        observed=LifecycleStatus.STARTING,
    )
    pg_node.info.return_value = service.BaseInfoResponse(started=True, node_version="0.4.0", core_version="1.0.0")
    pg_node.reconcile_lifecycle.side_effect = NodeAPIError(409, "still active")
    monkeypatch.setattr(node_module.node_manager, "get_node", AsyncMock(return_value=pg_node))
    recovery = NodeLifecycleRecovery(observed=LifecycleStatus.HEALTHY, acknowledge_expired_operation=True)

    with pytest.raises(NodeAPIError, match="still active"):
        await operation._recover_node_lifecycle_local(1, recovery)

    pg_node.reconcile_lifecycle.assert_awaited_once_with(LifecycleStatus.HEALTHY)


@pytest.mark.asyncio
async def test_explicit_lifecycle_recovery_rejects_operator_state_mismatch(monkeypatch):
    operation = NodeOperation(OperatorType.API)
    pg_node = AsyncMock()
    pg_node.get_lifecycle_state.return_value = NodeLifecycleState(
        operation=LifecycleOperation.STOP,
        observed=LifecycleStatus.STOPPING,
    )
    pg_node.info.return_value = service.BaseInfoResponse(started=True, node_version="0.4.0", core_version="1.0.0")
    monkeypatch.setattr(node_module.node_manager, "get_node", AsyncMock(return_value=pg_node))
    recovery = NodeLifecycleRecovery(observed=LifecycleStatus.STOPPED, acknowledge_expired_operation=True)

    with pytest.raises(Exception, match="Observed node state is healthy, not stopped"):
        await operation._recover_node_lifecycle_local(1, recovery)

    pg_node.reconcile_lifecycle.assert_not_awaited()


@pytest.fixture(autouse=True)
def _use_local_revocation_store_by_default(monkeypatch: pytest.MonkeyPatch):
    """Keep local NodeManager tests independent from the deployment environment."""
    monkeypatch.setattr(node_module, "needs_shared_bridge_memory", lambda: False)
    monkeypatch.setattr(
        node_module,
        "ensure_bridge_memory",
        AsyncMock(return_value=(None, None)),
    )
    monkeypatch.setattr(
        node_module,
        "get_bridge_memory",
        lambda: (None, None, "test-worker"),
    )


@pytest.mark.asyncio
async def test_required_shared_store_fails_closed_instead_of_creating_hybrid_manager(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(node_module, "needs_shared_bridge_memory", lambda: True)
    manager = NodeManager()
    db_node = SimpleNamespace(
        id=7,
        connection_type=NodeConnectionType.rest,
        address="127.0.0.1",
        port=62050,
        api_port=62051,
        server_ca="ca",
        api_key="key",
        name="node-7",
        default_timeout=10,
        internal_timeout=10,
        proxy_url=None,
        usage_coefficient=1.0,
    )
    monkeypatch.setattr(node_module, "get_bridge_memory", lambda: (None, None, "worker-a"))
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock(return_value=(None, None)))

    with pytest.raises(NodeAPIError, match="shared node bridge memory is unavailable"):
        manager._create_node_kwargs(db_node)

    old_runtime = _healthy_runtime_node()
    manager._nodes = {7: old_runtime}
    with pytest.raises(NodeAPIError, match="shared node bridge memory is unavailable"):
        await manager.update_node(db_node)
    assert manager._nodes == {7: old_runtime}
    assert manager._retiring_nodes == {}
    old_runtime.stop.assert_not_awaited()

    store = object()
    coordinator = object()
    monkeypatch.setattr(
        node_module,
        "get_bridge_memory",
        lambda: (store, coordinator, "worker-a"),
    )
    kwargs = manager._create_node_kwargs(db_node)
    assert kwargs["user_sync_store"] is store
    assert kwargs["lifecycle_coordinator"] is coordinator
    assert manager.uses_shared_revocation_store is True

    db_node.bridge_id = "9d7eb13c-a227-4a0c-a94c-76f15bcb624a"
    first_worker = manager._create_node_kwargs(db_node)
    second_worker = NodeManager()._create_node_kwargs(db_node)
    assert first_worker["node_id"] == db_node.bridge_id
    assert second_worker["node_id"] == db_node.bridge_id


@pytest.mark.asyncio
async def test_revocation_uses_current_locking_reads_for_users_and_node_topology(
    monkeypatch: pytest.MonkeyPatch,
):
    statements = []
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [7]))
    session = AsyncMock()
    session.execute.side_effect = lambda statement: (statements.append(statement), result)[1]
    user = SimpleNamespace(id=73)
    monkeypatch.setattr(node_sync_module, "async_object_session", lambda _user: session)

    expected_node_ids = await node_sync_module._lock_users_for_revocation([user])

    compiled = [str(statement.compile(dialect=mysql.dialect())).upper() for statement in statements]
    assert expected_node_ids == {7}
    assert len(compiled) == 2
    assert all(" FOR UPDATE" in statement for statement in compiled)


def test_node_update_users_nats_chunks_respect_payload_limit(monkeypatch: pytest.MonkeyPatch):
    users = [{"email": f"user-{index}", "payload": "x" * 600} for index in range(5)]
    max_payload = len(encode_node_command("update_users", {"users": users[:2]}))

    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 100)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_command_max_payload_bytes", max_payload)

    chunks = node_sync_module._chunk_serialized_users_for_nats(users)

    assert [len(chunk) for chunk in chunks] == [2, 2, 1]
    assert all(len(encode_node_command("update_users", {"users": chunk})) <= max_payload for chunk in chunks)


def test_revocation_chunks_measure_removal_and_original_payload(monkeypatch: pytest.MonkeyPatch):
    removals = [{"email": f"user-{index}"} for index in range(3)]
    originals = [{"email": f"user-{index}", "inbounds": ["x" * 1200]} for index in range(3)]
    revocation_id = "r" * 32
    max_payload = len(
        encode_node_command(
            "revoke_users",
            {
                "users": removals[:1],
                "original_users": originals[:1],
                "revocation_id": revocation_id,
            },
        )
    )
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 100)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_command_max_payload_bytes", max_payload)

    chunks = node_sync_module._chunk_serialized_revocations_for_nats(removals, originals, revocation_id)

    assert [len(users) for users, _ in chunks] == [1, 1, 1]
    for users, original_users in chunks:
        payload = {"users": users, "original_users": original_users, "revocation_id": revocation_id}
        assert len(encode_node_command("revoke_users", payload)) <= max_payload


@pytest.mark.asyncio
async def test_unhealthy_node_blocks_revocation_before_any_node_mutation(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    healthy = _healthy_runtime_node()
    broken = _healthy_runtime_node()
    broken.get_health.return_value = Health.BROKEN
    manager._nodes = {1: healthy, 2: broken}
    sync_batch = AsyncMock(return_value=0)
    monkeypatch.setattr(manager, "_sync_user_batch_to_node", sync_batch)

    with pytest.raises(node_sync_module.NodeRevocationError, match="node ids: 2"):
        await manager.revoke_users_and_wait(
            [ProtoUser(email="error-node-user")],
            "error-node-operation",
            [ProtoUser(email="error-node-user", inbounds=["vless-in"])],
        )

    healthy.begin_user_revocation.assert_not_awaited()
    broken.begin_user_revocation.assert_not_awaited()
    sync_batch.assert_not_awaited()
    assert manager._deleted_user_keys == set()


@pytest.mark.asyncio
async def test_partial_revocation_restores_exact_original_before_releasing_fence(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    first = _healthy_runtime_node()
    second = _healthy_runtime_node()
    manager._nodes = {1: first, 2: second}
    calls: list[tuple[int, tuple[str, ...], tuple[str, ...]]] = []

    async def sync_batch(node, users, *, revocation_id=None):
        node_id = 1 if node is first else 2
        calls.append((node_id, tuple(user.email for user in users), tuple(users[0].inbounds)))
        assert revocation_id == "partial-operation"
        if node is second and not users[0].inbounds:
            return len(users)
        return 0

    monkeypatch.setattr(manager, "_sync_user_batch_to_node", sync_batch)
    removal = ProtoUser(email="partial-user")
    original = ProtoUser(email="partial-user", inbounds=["vless-in"])

    with pytest.raises(node_sync_module.NodeRevocationError, match="failed to sync users to 1/2 nodes"):
        await manager.revoke_users_and_wait([removal], "partial-operation", [original])

    assert (1, ("partial-user",), ("vless-in",)) in calls
    assert (2, ("partial-user",), ("vless-in",)) in calls
    first.abort_user_revocation.assert_awaited_once_with(["partial-user"], "partial-operation")
    second.abort_user_revocation.assert_awaited_once_with(["partial-user"], "partial-operation")
    first.update_users.assert_awaited_once()
    second.update_users.assert_awaited_once()
    assert first.update_users.await_args.args[0][0].inbounds == ["vless-in"]
    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_revocation_skips_node_keys_already_finalized_by_an_earlier_attempt(
    monkeypatch: pytest.MonkeyPatch,
):
    manager = NodeManager()
    active_node = _healthy_runtime_node()
    finalized_node = _healthy_runtime_node()
    finalized_node.begin_user_revocation.side_effect = lambda user_keys, _revocation_id: SimpleNamespace(
        active_user_keys=(),
        finalized_user_keys=tuple(user_keys),
    )
    manager._nodes = {1: active_node, 2: finalized_node}
    sync_batch = AsyncMock(return_value=0)
    monkeypatch.setattr(manager, "_sync_user_batch_to_node", sync_batch)
    removal = ProtoUser(email="already-finalized")

    await manager.revoke_users_and_wait([removal], "retry-operation", [removal])
    await manager.finalize_user_revocations([removal], "retry-operation")

    sync_batch.assert_awaited_once_with(
        active_node,
        [removal],
        revocation_id="retry-operation",
    )
    active_node.finalize_user_revocation.assert_awaited_once_with(
        ["already-finalized"],
        "retry-operation",
    )
    finalized_node.finalize_user_revocation.assert_not_awaited()


@pytest.mark.asyncio
async def test_separate_rpc_chunks_with_same_revocation_id_close_only_their_own_keys(
    monkeypatch: pytest.MonkeyPatch,
):
    manager = NodeManager()
    node = _healthy_runtime_node()
    manager._nodes = {1: node}
    sync_batch = AsyncMock(return_value=0)
    monkeypatch.setattr(manager, "_sync_user_batch_to_node", sync_batch)
    first_removal = ProtoUser(email="chunk-a")
    first_original = ProtoUser(email="chunk-a", inbounds=["in-a"])
    second_removal = ProtoUser(email="chunk-b")
    second_original = ProtoUser(email="chunk-b", inbounds=["in-b"])

    await manager.revoke_users_and_wait(
        [first_removal],
        "shared-operation",
        [first_original],
    )
    await manager.revoke_users_and_wait(
        [second_removal],
        "shared-operation",
        [second_original],
    )

    await manager.abort_user_revocations(
        [first_removal],
        "shared-operation",
        [first_original],
    )
    assert manager._revocation_nodes["shared-operation"][0][2] == frozenset({"chunk-b"})
    node.abort_user_revocation.assert_awaited_once_with(["chunk-a"], "shared-operation")

    await manager.finalize_user_revocations([second_removal], "shared-operation")
    assert "shared-operation" not in manager._revocation_nodes
    node.finalize_user_revocation.assert_awaited_once_with(["chunk-b"], "shared-operation")


@pytest.mark.asyncio
async def test_close_chunk_falls_back_when_same_operation_record_contains_only_other_keys():
    manager = NodeManager()
    node = _healthy_runtime_node()
    manager._nodes = {7: node}
    manager._revocation_nodes = {"shared-operation": [(7, node, frozenset({"chunk-a"}))]}

    await manager.finalize_user_revocations(
        [ProtoUser(email="chunk-b")],
        "shared-operation",
        expected_node_ids={7},
    )

    node.finalize_user_revocation.assert_awaited_once_with(["chunk-b"], "shared-operation")
    assert manager._revocation_nodes == {"shared-operation": [(7, node, frozenset({"chunk-a"}))]}


@pytest.mark.asyncio
async def test_transient_finalize_failure_retains_operation_state_for_retry(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    node = _healthy_runtime_node()
    node.finalize_user_revocation.side_effect = [RuntimeError("temporary close failure"), None]
    manager._nodes = {7: node}
    monkeypatch.setattr(manager, "_sync_user_batch_to_node", AsyncMock(return_value=0))
    user = ProtoUser(email="73")

    await manager.revoke_users_and_wait([user], "delete-73", [user], expected_node_ids={7})
    with pytest.raises(node_sync_module.NodeRevocationError, match="failed to finalize"):
        await manager.finalize_user_revocations([user], "delete-73", expected_node_ids={7})

    assert manager._revocation_nodes["delete-73"][0][2] == frozenset({"73"})
    assert manager._deletion_fence_owners == {"73": {"delete-73"}}
    assert not manager._revocations_idle.is_set()

    await manager.finalize_user_revocations([user], "delete-73", expected_node_ids={7})

    assert manager._revocation_nodes == {}
    assert manager._deletion_fence_owners == {}
    assert manager._deleted_user_keys == {"73"}
    assert manager._revocations_idle.is_set()


def test_deletion_fence_uses_the_real_serialized_panel_user_key():
    proto_user = _serialize_user_for_node(73, {})

    assert "id" not in proto_user.DESCRIPTOR.fields_by_name
    assert NodeManager._user_key(proto_user) == "73"


@pytest.mark.asyncio
async def test_node_startup_waits_until_provisional_revocation_is_resolved():
    manager = NodeManager()
    manager._acquire_deletion_fences({"73"}, "delete-73")

    startup = asyncio.create_task(manager.wait_for_user_revocations())
    await asyncio.sleep(0)
    assert not startup.done()

    manager._release_deletion_fences({"73"}, "delete-73")
    await asyncio.wait_for(startup, timeout=1)


def test_node_startup_filters_permanent_tombstones_from_old_db_snapshot():
    manager = NodeManager()
    manager._acquire_deletion_fences({"73"}, "delete-73")
    manager._finalize_deletion_fences({"73"}, "delete-73")
    users = [ProtoUser(email="73", inbounds=["stale"]), ProtoUser(email="74", inbounds=["active"])]

    assert manager.filter_permanently_deleted_users(users) == [users[1]]


@pytest.mark.asyncio
async def test_revocation_never_uses_full_replacement_sync_on_legacy_node():
    manager = NodeManager()
    node = _healthy_runtime_node()
    node._supports_chunked_sync.return_value = (False, "legacy")

    with pytest.raises(node_sync_module.NodeRevocationError, match="partial chunked sync"):
        await manager._sync_user_batch_to_node(
            node,
            [ProtoUser(email="73")],
            revocation_id="delete-73",
        )

    node.sync_users.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_old_runtime_stop_remains_in_revocation_preflight():
    manager = NodeManager()
    active = _healthy_runtime_node()
    retiring = _healthy_runtime_node()
    retiring.stop.side_effect = RuntimeError("stop failed")
    retiring.get_health.return_value = Health.INVALID
    manager._nodes = {1: active}
    manager._retiring_nodes = {1: [retiring]}

    await manager._finish_retiring_node(1, retiring)

    assert manager._retiring_nodes == {1: [retiring]}
    with pytest.raises(node_sync_module.NodeRevocationError, match="node ids: 1"):
        await manager.revoke_users_and_wait(
            [ProtoUser(email="73")],
            "delete-73",
            [ProtoUser(email="73", inbounds=["active"])],
        )
    active.begin_user_revocation.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_old_runtime_stop_removes_it_from_revocation_topology():
    manager = NodeManager()
    retiring = _healthy_runtime_node()
    manager._retiring_nodes = {1: [retiring]}

    await manager._finish_retiring_node(1, retiring)

    assert manager._retiring_nodes == {}
    retiring.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_node_waits_for_confirmed_stop_before_forgetting_runtime():
    manager = NodeManager()
    node = _healthy_runtime_node()
    manager._nodes = {1: node}
    manager._user_sync_locks = {1: asyncio.Lock()}

    await manager.remove_node(1)

    node.stop.assert_awaited_once()
    assert manager._nodes == {}
    assert manager._retiring_nodes == {}
    assert manager._user_sync_locks == {}


@pytest.mark.asyncio
async def test_stale_remove_namespace_cannot_remove_recreated_numeric_id():
    manager = NodeManager()
    replacement = _healthy_runtime_node()
    replacement.node_id = "new-bridge-id"
    manager._nodes = {1: replacement}

    await manager.remove_node(1, expected_bridge_namespace="old-bridge-id")

    assert manager._nodes == {1: replacement}
    assert manager._retiring_nodes == {}
    replacement.stop.assert_not_awaited()
    replacement.disconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_periodic_orphan_recovery_runs_inside_fresh_db_transaction(monkeypatch):
    from app.jobs import node_checker

    transaction_active = False
    recovered: list[int] = []

    class DBContext:
        async def __aenter__(self):
            nonlocal transaction_active
            transaction_active = True
            return self

        async def __aexit__(self, *_args):
            nonlocal transaction_active
            transaction_active = False
            return False

    async def _recover(_db, db_node):
        assert transaction_active
        recovered.append(db_node.id)

    monkeypatch.setattr(node_checker.runtime_settings, "role", Role.NODE)
    monkeypatch.setattr(node_checker.node_manager, "get_nodes", AsyncMock(return_value={7: object()}))
    monkeypatch.setattr(node_checker, "GetDB", DBContext)
    monkeypatch.setattr(node_checker, "get_node_by_id", AsyncMock(return_value=SimpleNamespace(id=7)))
    monkeypatch.setattr(node_checker.node_operator, "reconcile_orphaned_user_sync", _recover)

    await node_checker.reconcile_orphaned_user_sync()

    assert recovered == [7]
    assert transaction_active is False


@pytest.mark.asyncio
async def test_remove_node_failed_stop_retains_runtime_and_fails_closed():
    manager = NodeManager()
    node = _healthy_runtime_node()
    node.stop.side_effect = RuntimeError("unknown stop outcome")
    manager._nodes = {1: node}
    manager._user_sync_locks = {1: asyncio.Lock()}

    with pytest.raises(NodeAPIError, match="cannot confirm node 1 runtime shutdown"):
        await manager.remove_node(1)

    assert manager._retiring_nodes == {1: [node]}
    assert 1 in manager._user_sync_locks
    assert manager._removing_node_ids == {1}


@pytest.mark.asyncio
async def test_remove_node_stop_failure_does_not_purge_shared_memory(monkeypatch):
    operation = NodeOperation(OperatorType.API)
    remove = AsyncMock(side_effect=NodeAPIError(503, "ambiguous stop"))
    clear = AsyncMock()
    monkeypatch.setattr(node_module.node_manager, "remove_node", remove)
    monkeypatch.setattr("app.operation.node.clear_bridge_memory_for_node", clear)

    with pytest.raises(NodeAPIError, match="ambiguous stop"):
        await operation._remove_node_local(7)

    clear.assert_not_awaited()


@pytest.mark.asyncio
async def test_lost_delete_broadcast_still_fences_and_quiesces_sibling(monkeypatch):
    from app.nats.kv_cas import MemoryCasKv
    from app.node.nats_memory import NatsNodeLifecycleCoordinator

    coordinator = NatsNodeLifecycleCoordinator(MemoryCasKv())
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(
        node_module,
        "get_bridge_memory",
        lambda: (object(), coordinator, "worker"),
    )
    origin = NodeManager()
    sibling = NodeManager()
    origin._uses_shared_revocation_store = True
    sibling._uses_shared_revocation_store = True
    origin_runtime = _healthy_runtime_node()
    origin_runtime.node_id = "bridge-old"
    sibling_runtime = _healthy_runtime_node()
    sibling_runtime.node_id = "bridge-old"
    origin._nodes = {1: origin_runtime}
    sibling._nodes = {1: sibling_runtime}

    await origin.remove_node(
        1,
        expected_bridge_namespace="bridge-old",
        permanent_delete=True,
    )

    # The sibling deliberately receives no broadcast. Its next DB-driven
    # registration observes durable shared state and only disconnects locally.
    with pytest.raises(NodeAPIError, match="permanently deleted"):
        await sibling.update_node(_db_node(1, "bridge-old"))
    sibling_runtime.disconnect.assert_awaited_once()
    sibling_runtime.stop.assert_not_awaited()
    assert sibling._nodes == {}

    # Reuse of the public numeric id is safe because the new row has a new
    # stable Bridge namespace.
    replacement = _healthy_runtime_node()
    replacement.node_id = "bridge-new"
    monkeypatch.setattr(node_module, "create_node", lambda **_kwargs: replacement)
    assert await sibling.update_node(_db_node(1, "bridge-new")) is replacement


@pytest.mark.asyncio
async def test_temporary_disconnect_allows_same_incarnation_to_restart(monkeypatch):
    from app.nats.kv_cas import MemoryCasKv
    from app.node.nats_memory import NatsNodeLifecycleCoordinator

    coordinator = NatsNodeLifecycleCoordinator(MemoryCasKv())
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(
        node_module,
        "get_bridge_memory",
        lambda: (object(), coordinator, "worker"),
    )
    manager = NodeManager()
    manager._uses_shared_revocation_store = True
    old = _healthy_runtime_node()
    old.node_id = "bridge-enabled"
    manager._nodes = {1: old}

    await manager.remove_node(1, expected_bridge_namespace="bridge-enabled")

    assert await coordinator.is_deleted("bridge-enabled") is False
    restarted = _healthy_runtime_node()
    restarted.node_id = "bridge-enabled"
    monkeypatch.setattr(node_module, "create_node", lambda **_kwargs: restarted)
    assert await manager.update_node(_db_node(1, "bridge-enabled")) is restarted


@pytest.mark.asyncio
async def test_default_delete_failure_retains_row_runtime_fence_and_tombstone(monkeypatch):
    from app.nats.kv_cas import MemoryCasKv
    from app.node.nats_memory import NatsNodeLifecycleCoordinator

    coordinator = NatsNodeLifecycleCoordinator(MemoryCasKv())
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(
        node_module,
        "get_bridge_memory",
        lambda: (object(), coordinator, "worker"),
    )
    manager = NodeManager()
    manager._uses_shared_revocation_store = True
    runtime = _healthy_runtime_node()
    runtime.node_id = "bridge-offline"
    runtime.stop.side_effect = RuntimeError("offline")
    manager._nodes = {1: runtime}

    with pytest.raises(NodeAPIError, match="cannot confirm"):
        await manager.remove_node(
            1,
            expected_bridge_namespace="bridge-offline",
            permanent_delete=True,
        )

    assert await coordinator.is_deleted("bridge-offline") is True
    assert manager._retiring_nodes == {1: [runtime]}
    assert manager._removing_node_ids == {1}


@pytest.mark.asyncio
async def test_bulk_delete_reports_partial_failure_and_commits_each_success(monkeypatch):
    operation = NodeOperation(OperatorType.API)
    nodes = {
        1: SimpleNamespace(id=1, bridge_id="bridge-1", name="node-1"),
        2: SimpleNamespace(id=2, bridge_id="bridge-2", name="node-2"),
    }
    monkeypatch.setattr(
        operation,
        "get_validated_node",
        AsyncMock(side_effect=lambda _db, node_id: nodes[node_id]),
    )
    operation._remove_node_impl = AsyncMock(side_effect=[None, NodeAPIError(503, "offline stop outcome")])
    committed_remove = AsyncMock()
    monkeypatch.setattr("app.operation.node.remove_node", committed_remove)
    monkeypatch.setattr(
        "app.operation.node.NodeResponse.model_validate",
        lambda node: SimpleNamespace(id=node.id, name=node.name),
    )
    monkeypatch.setattr("app.operation.node.notification.remove_node", AsyncMock())
    admin = SimpleNamespace(username="operator")

    result = await operation.bulk_remove_nodes(
        object(),
        BulkNodeSelection(ids={1, 2}),
        admin,
    )

    assert result.nodes == ["node-1"]
    assert result.count == 1
    assert result.failed == {2: "offline stop outcome"}
    committed_remove.assert_awaited_once_with(ANY, nodes[1])


@pytest.mark.asyncio
async def test_single_node_delete_commit_ack_loss_is_resolved_from_fresh_db(monkeypatch):
    operation = NodeOperation(OperatorType.API)
    db_node = SimpleNamespace(id=1, bridge_id="bridge-1", name="node-1")
    failed_db = SimpleNamespace(rollback=AsyncMock())
    monkeypatch.setattr(operation, "get_validated_node", AsyncMock(return_value=db_node))
    operation._remove_node_impl = AsyncMock()
    monkeypatch.setattr(
        "app.operation.node.NodeResponse.model_validate",
        lambda node: SimpleNamespace(id=node.id, name=node.name),
    )
    monkeypatch.setattr(
        "app.operation.node.remove_node",
        AsyncMock(side_effect=RuntimeError("commit acknowledgement lost")),
    )
    monkeypatch.setattr("app.operation.node.notification.remove_node", AsyncMock())

    class _FreshDB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def scalar(self, _query):
            return None

    monkeypatch.setattr("app.operation.node.GetDB", _FreshDB)

    await operation.remove_node(
        failed_db,
        1,
        SimpleNamespace(username="operator"),
    )

    failed_db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_node_delete_commit_ack_loss_counts_committed_row(monkeypatch):
    operation = NodeOperation(OperatorType.API)
    db_node = SimpleNamespace(id=1, bridge_id="bridge-1", name="node-1")
    failed_db = SimpleNamespace(rollback=AsyncMock())
    monkeypatch.setattr(operation, "get_validated_node", AsyncMock(return_value=db_node))
    operation._remove_node_impl = AsyncMock()
    monkeypatch.setattr(
        "app.operation.node.NodeResponse.model_validate",
        lambda node: SimpleNamespace(id=node.id, name=node.name),
    )
    monkeypatch.setattr(
        "app.operation.node.remove_node",
        AsyncMock(side_effect=RuntimeError("commit acknowledgement lost")),
    )
    monkeypatch.setattr("app.operation.node.notification.remove_node", AsyncMock())

    class _FreshDB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def scalar(self, _query):
            return None

    monkeypatch.setattr("app.operation.node.GetDB", _FreshDB)

    result = await operation.bulk_remove_nodes(
        failed_db,
        BulkNodeSelection(ids={1}),
        SimpleNamespace(username="operator"),
    )

    assert result.nodes == ["node-1"]
    assert result.count == 1
    assert result.failed == {}
    failed_db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_completing_after_delete_tombstone_is_stopped(monkeypatch):
    from app.nats.kv_cas import MemoryCasKv
    from app.node.nats_memory import NatsNodeLifecycleCoordinator

    coordinator = NatsNodeLifecycleCoordinator(MemoryCasKv())
    pg_node = AsyncMock()
    pg_node.node_id = "bridge-race"
    pg_node.worker_id = "worker-a"
    pg_node._user_sync_store = None
    pg_node._lifecycle_coordinator = coordinator
    pg_node.get_lifecycle_state.return_value = None
    pg_node.info.return_value = service.BaseInfoResponse(user_sync_epoch_supported=True)

    async def _start(**_kwargs):
        await coordinator.mark_deleted("bridge-race")
        return service.BaseInfoResponse(started=True, node_version="0.4.0", core_version="1.0.0")

    pg_node.start.side_effect = _start
    core = SimpleNamespace(type=CoreType.wg, to_str=lambda: "{}")

    with pytest.raises(NodeAPIError, match="permanently deleted"):
        await NodeOperation._start_or_attach_node(
            pg_node,
            SimpleNamespace(name="node-race", keep_alive=30),
            core,
            [],
            service.BackendType.WIREGUARD,
        )
    pg_node.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_replacement_paused_during_delete_cannot_install_after_tombstone(monkeypatch):
    from app.nats.kv_cas import MemoryCasKv
    from app.node.nats_memory import NatsNodeLifecycleCoordinator

    coordinator = NatsNodeLifecycleCoordinator(MemoryCasKv())
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(
        node_module,
        "get_bridge_memory",
        lambda: (object(), coordinator, "worker"),
    )
    manager = NodeManager()
    manager._uses_shared_revocation_store = True
    old = _healthy_runtime_node()
    old.node_id = "bridge-old"
    stop_started = asyncio.Event()
    allow_stop = asyncio.Event()

    async def _stop():
        stop_started.set()
        await allow_stop.wait()

    old.stop.side_effect = _stop
    manager._nodes = {1: old}
    replacement = _healthy_runtime_node()
    replacement.node_id = "bridge-old"
    monkeypatch.setattr(node_module, "create_node", lambda **_kwargs: replacement)
    update = asyncio.create_task(manager.update_node(_db_node(1, "bridge-old")))
    await stop_started.wait()
    await coordinator.mark_deleted("bridge-old")
    allow_stop.set()

    with pytest.raises(NodeAPIError, match="permanently deleted"):
        await update
    assert manager._nodes == {}
    assert manager._removing_node_ids == set()
    assert manager._replacing_node_ids == set()
    replacement.disconnect.assert_awaited_once()

    new_incarnation = _healthy_runtime_node()
    new_incarnation.node_id = "bridge-new"
    monkeypatch.setattr(node_module, "create_node", lambda **_kwargs: new_incarnation)
    assert await manager.update_node(_db_node(1, "bridge-new")) is new_incarnation


@pytest.mark.asyncio
async def test_local_replacement_paused_during_delete_cannot_install_after_tombstone(monkeypatch):
    manager = NodeManager()
    old = _healthy_runtime_node()
    old.node_id = "bridge-local-old"
    first_stop_started = asyncio.Event()
    allow_first_stop = asyncio.Event()
    stop_calls = 0

    async def _stop():
        nonlocal stop_calls
        stop_calls += 1
        if stop_calls == 1:
            first_stop_started.set()
            await allow_first_stop.wait()

    old.stop.side_effect = _stop
    manager._nodes = {1: old}
    replacement = _healthy_runtime_node()
    replacement.node_id = "bridge-local-old"
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(node_module, "create_node", lambda **_kwargs: replacement)

    update = asyncio.create_task(manager.update_node(_db_node(1, "bridge-local-old")))
    await first_stop_started.wait()
    await manager.remove_node(
        1,
        expected_bridge_namespace="bridge-local-old",
        permanent_delete=True,
    )
    allow_first_stop.set()

    with pytest.raises(NodeAPIError, match="permanently deleted"):
        await update
    assert stop_calls == 2
    assert manager._nodes == {}
    replacement.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_replacement_waits_for_all_old_runtimes_and_retries_failure(monkeypatch):
    manager = NodeManager()
    old = _healthy_runtime_node()
    old.stop.side_effect = [RuntimeError("ambiguous stop"), None]
    manager._nodes = {1: old}
    first_new = _healthy_runtime_node()
    second_new = _healthy_runtime_node()
    created = iter((first_new, second_new))
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(node_module, "create_node", lambda **_kwargs: next(created))

    with pytest.raises(NodeAPIError, match="cannot confirm old node"):
        await manager.update_node(_db_node())
    assert manager._nodes == {}
    assert manager._retiring_nodes == {1: [old]}
    assert manager._replacing_node_ids == {1}

    assert await manager.update_node(_db_node()) is second_new
    assert manager._nodes == {1: second_new}
    assert manager._retiring_nodes == {}
    assert old.stop.await_count == 2


@pytest.mark.asyncio
async def test_cancelled_replacement_keeps_shielded_retiree_cleanup(monkeypatch):
    manager = NodeManager()
    old = _healthy_runtime_node()
    stop_started = asyncio.Event()
    allow_stop = asyncio.Event()

    async def _stop():
        stop_started.set()
        await allow_stop.wait()

    old.stop.side_effect = _stop
    manager._nodes = {1: old}
    replacement = _healthy_runtime_node()
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(node_module, "create_node", lambda **_kwargs: replacement)
    task = asyncio.create_task(manager.update_node(_db_node()))
    await stop_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert manager._nodes == {}
    allow_stop.set()
    for _ in range(20):
        if manager._nodes.get(1) is replacement:
            break
        await asyncio.sleep(0)
    assert manager._nodes == {1: replacement}
    assert manager._retiring_nodes == {}


@pytest.mark.asyncio
async def test_health_pass_repairs_missed_runtime_configuration_upsert(monkeypatch):
    from app.jobs import node_checker

    db_node = _db_node()
    runtime = _healthy_runtime_node()
    runtime.node_id = db_node.bridge_id
    runtime._extra = {"config_signature": "stale-signature"}
    update = AsyncMock()
    monkeypatch.setattr(node_checker, "get_bridge_memory", lambda: (None, None, "worker"))
    monkeypatch.setattr(node_checker.node_manager, "update_node", update)

    await node_checker.process_node_health_check(db_node, runtime)

    update.assert_awaited_once_with(db_node)


@pytest.mark.asyncio
async def test_health_pass_repairs_missing_runtime(monkeypatch):
    from app.jobs import node_checker

    db_node = _db_node()
    connect = AsyncMock()

    class _DB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(node_checker, "get_bridge_memory", lambda: (None, None, "worker"))
    monkeypatch.setattr(node_checker, "GetDB", lambda: _DB())
    monkeypatch.setattr(node_checker.node_operator, "connect_single_node", connect)

    await node_checker.process_node_health_check(db_node, None)

    connect.assert_awaited_once_with(ANY, db_node.id)


@pytest.mark.asyncio
async def test_health_pass_uses_uuid_namespace_for_active_lifecycle_lease(monkeypatch):
    from app.jobs import node_checker

    db_node = _db_node(4, "uuid-bridge-4")
    db_node.status = NodeStatus.connected
    runtime = _healthy_runtime_node()
    runtime.node_id = db_node.bridge_id
    runtime._extra = {}
    runtime.requires_hard_reset = lambda: False
    runtime.get_lifecycle_state.return_value = NodeLifecycleState(observed=LifecycleStatus.HEALTHY)
    seen: list[str] = []

    class _Coordinator:
        async def is_deleted(self, _node_id):
            return False

        async def has_active_lease(self, node_id):
            seen.append(node_id)
            return True

    monkeypatch.setattr(
        node_checker,
        "get_bridge_memory",
        lambda: (None, _Coordinator(), "worker"),
    )
    monkeypatch.setattr(
        node_checker,
        "verify_node_backend_health",
        AsyncMock(return_value=(Health.NOT_CONNECTED, None, None)),
    )
    monkeypatch.setattr(NodeOperation, "_attach_if_running", AsyncMock(return_value=None))
    reconnect = AsyncMock()
    monkeypatch.setattr(node_checker.node_operator, "connect_single_node", reconnect)

    await node_checker.process_node_health_check(db_node, runtime)

    assert seen == ["uuid-bridge-4"]
    reconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_with_incomplete_runtime_topology_cannot_commit_revocation():
    authoritative_worker = NodeManager()
    node = _healthy_runtime_node()
    authoritative_worker._nodes = {7: node}
    lagging_worker = NodeManager()

    with pytest.raises(node_sync_module.NodeRevocationError, match="missing node ids: 7"):
        await lagging_worker.revoke_users_and_wait(
            [ProtoUser(email="73")],
            "delete-73",
            [ProtoUser(email="73", inbounds=["active"])],
            expected_node_ids={7},
        )

    node.begin_user_revocation.assert_not_awaited()
    node.sync_users_chunked.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_store_close_on_another_worker_has_no_process_local_gate(monkeypatch: pytest.MonkeyPatch):
    begin_worker = NodeManager()
    close_worker = NodeManager()
    begin_worker._uses_shared_revocation_store = True
    close_worker._uses_shared_revocation_store = True
    begin_node = _healthy_runtime_node()
    close_node = _healthy_runtime_node()
    begin_worker._nodes = {7: begin_node}
    close_worker._nodes = {7: close_node}
    monkeypatch.setattr(begin_worker, "_sync_user_batch_to_node", AsyncMock(return_value=0))
    user = ProtoUser(email="73")

    await begin_worker.revoke_users_and_wait([user], "delete-73", [user], expected_node_ids={7})
    await close_worker.finalize_user_revocations([user], "delete-73", expected_node_ids={7})

    close_node.finalize_user_revocation.assert_awaited_once_with(["73"], "delete-73")
    assert begin_worker._revocation_nodes == {}
    assert begin_worker._deletion_fence_owners == {}
    assert begin_worker._deleted_user_keys == set()
    assert begin_worker._revocations_idle.is_set()


@pytest.mark.asyncio
async def test_shared_store_abort_on_another_worker_restores_payload_without_local_owner(
    monkeypatch: pytest.MonkeyPatch,
):
    close_worker = NodeManager()
    close_worker._uses_shared_revocation_store = True
    close_node = _healthy_runtime_node()
    close_worker._nodes = {7: close_node}
    restored = []

    async def sync_batch(_node, users, *, revocation_id=None):
        restored.extend(users)
        assert revocation_id == "delete-73"
        return 0

    monkeypatch.setattr(close_worker, "_sync_user_batch_to_node", sync_batch)
    removal = ProtoUser(email="73")
    original = ProtoUser(email="73", inbounds=["active"])

    await close_worker.abort_user_revocations(
        [removal],
        "delete-73",
        [original],
        expected_node_ids={7},
    )

    assert restored == [original]
    close_node.abort_user_revocation.assert_awaited_once_with(["73"], "delete-73")


@pytest.mark.asyncio
@pytest.mark.parametrize("close_action", ["abort", "finalize"])
async def test_close_uses_recorded_runtime_after_confirmed_node_removal(
    monkeypatch: pytest.MonkeyPatch,
    close_action: str,
):
    manager = NodeManager()
    node = _healthy_runtime_node()
    manager._nodes = {7: node}
    monkeypatch.setattr(manager, "_sync_user_batch_to_node", AsyncMock(return_value=0))
    removal = ProtoUser(email="73")
    original = ProtoUser(email="73", inbounds=["active"])

    await manager.revoke_users_and_wait(
        [removal],
        "delete-73",
        [original],
        expected_node_ids={7},
    )
    manager._nodes.pop(7)

    if close_action == "abort":
        await manager.abort_user_revocations(
            [removal],
            "delete-73",
            [original],
            expected_node_ids={7},
        )
        node.abort_user_revocation.assert_awaited_once_with(["73"], "delete-73")
        assert manager._deleted_user_keys == set()
    else:
        await manager.finalize_user_revocations(
            [removal],
            "delete-73",
            expected_node_ids={7},
        )
        node.finalize_user_revocation.assert_awaited_once_with(["73"], "delete-73")
        assert manager._deleted_user_keys == {"73"}

    assert manager._deletion_fence_owners == {}
    assert manager._revocations_idle.is_set()


@pytest.mark.asyncio
async def test_removal_waits_for_node_worker_rpc_ack(monkeypatch: pytest.MonkeyPatch):
    request = AsyncMock()
    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", request)
    removal = ProtoUser(email="user-1")
    original = ProtoUser(email="user-1", inbounds=["vless-in"])

    await node_sync_module._dispatch_users_removal([removal], [original], {7})

    payload = request.await_args.args[1]
    assert request.await_args.args[0] == "revoke_users"
    assert payload["revocation_id"] is not None
    assert payload["users"][0]["email"] == "user-1"
    assert payload["original_users"][0]["email"] == "user-1"
    assert payload["original_users"][0]["inbounds"] == ["vless-in"]
    assert payload["expected_node_ids"] == [7]


@pytest.mark.asyncio
async def test_single_removal_waits_for_node_worker_rpc_ack(monkeypatch: pytest.MonkeyPatch):
    request = AsyncMock()
    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", request)

    await node_sync_module._dispatch_user_removal(
        ProtoUser(email="user-1"), ProtoUser(email="user-1", inbounds=["vless-in"])
    )

    payload = request.await_args.args[1]
    assert request.await_args.args[0] == "revoke_user"
    assert payload["user"]["email"] == "user-1"
    assert payload["original_user"]["inbounds"] == ["vless-in"]
    assert payload["revocation_id"] is not None


@pytest.mark.asyncio
async def test_single_local_removal_waits_for_runtime_ack(monkeypatch: pytest.MonkeyPatch):
    revoke_users_and_wait = AsyncMock()
    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.ALL_IN_ONE)
    monkeypatch.setattr(node_sync_module.node_manager, "revoke_users_and_wait", revoke_users_and_wait)
    proto_user = object()
    original_user = object()

    await node_sync_module._dispatch_user_removal(proto_user, original_user)

    revoke_users_and_wait.assert_awaited_once_with(
        [proto_user],
        ANY,
        [original_user],
        expected_node_ids=None,
    )


@pytest.mark.asyncio
async def test_remote_removal_failure_is_retryable(monkeypatch: pytest.MonkeyPatch):
    request = AsyncMock(side_effect=RuntimeError("NATS is not available"))
    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", request)

    with pytest.raises(node_sync_module.NodeRevocationError, match="cannot confirm user revocation"):
        await node_sync_module._dispatch_user_removal(
            ProtoUser(email="user-1"), ProtoUser(email="user-1", inbounds=["vless-in"])
        )


@pytest.mark.asyncio
async def test_remote_removal_abort_waits_for_node_worker_ack(monkeypatch: pytest.MonkeyPatch):
    request = AsyncMock()
    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", request)

    await node_sync_module._dispatch_users_removal_abort(
        [ProtoUser(email="7")],
        [ProtoUser(email="7", inbounds=["vless-in"])],
        "operation-7",
        frozenset({7}),
    )

    payload = request.await_args.args[1]
    assert request.await_args.args[0] == "abort_revoke_users"
    assert payload["users"][0]["email"] == "7"
    assert payload["original_users"][0]["inbounds"] == ["vless-in"]
    assert payload["revocation_id"] == "operation-7"
    assert payload["expected_node_ids"] == [7]


@pytest.mark.asyncio
async def test_abort_refreshes_topology_only_after_stale_snapshot_is_rejected(monkeypatch: pytest.MonkeyPatch):
    calls = []

    async def dispatch(_users, _originals, _revocation_id, expected_node_ids):
        calls.append(expected_node_ids)
        if len(calls) == 1:
            raise node_sync_module.NodeRevocationError(
                "runtime topology is incomplete for user revocation (missing node ids: 7)"
            )

    monkeypatch.setattr(node_sync_module, "_dispatch_users_removal_abort", dispatch)
    monkeypatch.setattr(node_sync_module, "_refresh_expected_node_ids", AsyncMock(return_value=frozenset()))
    revocation = node_sync_module.UserRevocation(
        "operation-7",
        (ProtoUser(email="7"),),
        (ProtoUser(email="7", inbounds=["active"]),),
        frozenset({7}),
    )

    await node_sync_module.abort_user_removal(revocation)

    assert calls == [frozenset({7}), frozenset()]
    node_sync_module._refresh_expected_node_ids.assert_awaited_once()


@pytest.mark.asyncio
async def test_remote_abort_refreshes_topology_through_nested_rpc_error(monkeypatch: pytest.MonkeyPatch):
    request = AsyncMock(
        side_effect=[
            RuntimeError("runtime topology is incomplete for user revocation (missing node ids: 7)"),
            {},
        ]
    )
    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", request)
    monkeypatch.setattr(node_sync_module, "_refresh_expected_node_ids", AsyncMock(return_value=frozenset()))
    revocation = node_sync_module.UserRevocation(
        "operation-remote-refresh",
        (ProtoUser(email="7"),),
        (ProtoUser(email="7", inbounds=["active"]),),
        frozenset({7}),
    )

    await node_sync_module.abort_user_removal(revocation)

    assert request.await_count == 2
    assert request.await_args_list[0].args[1]["expected_node_ids"] == [7]
    assert "expected_node_ids" in request.await_args_list[1].args[1]
    assert request.await_args_list[1].args[1]["expected_node_ids"] == []
    node_sync_module._refresh_expected_node_ids.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_transient_failure_is_retried_until_acknowledged(monkeypatch: pytest.MonkeyPatch):
    completed = asyncio.Event()
    attempts = 0

    async def finalize(_users, _revocation_id, _expected_node_ids):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise node_sync_module.NodeRevocationError("temporary finalize failure")
        completed.set()

    monkeypatch.setattr(node_sync_module, "_dispatch_users_removal_finalize", finalize)
    revocation = node_sync_module.UserRevocation(
        "operation-retry",
        (ProtoUser(email="7"),),
        (ProtoUser(email="7", inbounds=["active"]),),
        frozenset({7}),
    )

    await node_sync_module.finalize_user_removal(revocation)
    retry_task = node_sync_module._finalize_retry_tasks["operation-retry"]
    await asyncio.wait_for(completed.wait(), timeout=1)
    await asyncio.wait_for(retry_task, timeout=1)

    assert attempts == 2
    assert "operation-retry" not in node_sync_module._finalize_retry_tasks


@pytest.mark.asyncio
async def test_abort_transient_failure_keeps_retrying_after_api_failure(monkeypatch: pytest.MonkeyPatch):
    completed = asyncio.Event()
    attempts = 0

    async def abort(_users, _originals, _revocation_id, _expected_node_ids):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise node_sync_module.NodeRevocationError("temporary abort failure")
        completed.set()

    monkeypatch.setattr(node_sync_module, "_dispatch_users_removal_abort", abort)
    revocation = node_sync_module.UserRevocation(
        "operation-abort-retry",
        (ProtoUser(email="7"),),
        (ProtoUser(email="7", inbounds=["active"]),),
        frozenset({7}),
    )

    with pytest.raises(node_sync_module.NodeRevocationError, match="temporary abort failure"):
        await node_sync_module.abort_user_removal(revocation)
    retry_task = node_sync_module._abort_retry_tasks["operation-abort-retry"]
    await asyncio.wait_for(completed.wait(), timeout=1)
    await asyncio.wait_for(retry_task, timeout=1)

    assert attempts == 2
    assert "operation-abort-retry" not in node_sync_module._abort_retry_tasks


@pytest.mark.asyncio
async def test_finalize_cancellation_after_commit_schedules_retry(monkeypatch: pytest.MonkeyPatch):
    first_started = asyncio.Event()
    retry_completed = asyncio.Event()
    attempts = 0

    async def finalize(_users, _revocation_id, _expected_node_ids):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            first_started.set()
            await asyncio.Future()
        retry_completed.set()

    monkeypatch.setattr(node_sync_module, "_dispatch_users_removal_finalize", finalize)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_rpc_timeout", 0.01)
    revocation = node_sync_module.UserRevocation(
        "operation-cancelled-finalize",
        (ProtoUser(email="7"),),
        (ProtoUser(email="7", inbounds=["active"]),),
        frozenset({7}),
    )

    task = asyncio.create_task(node_sync_module.finalize_user_removal(revocation))
    await first_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    retry_task = node_sync_module._finalize_retry_tasks["operation-cancelled-finalize"]
    await asyncio.wait_for(retry_completed.wait(), timeout=1)
    await asyncio.wait_for(retry_task, timeout=1)
    assert attempts == 2


@pytest.mark.asyncio
async def test_remote_multi_chunk_abort_has_a_fresh_timeout_for_every_chunk(monkeypatch: pytest.MonkeyPatch):
    completed: list[str] = []

    async def request(_action, payload):
        await asyncio.sleep(0.03)
        completed.append(payload["users"][0]["email"])
        return {}

    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 1)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_rpc_timeout", 0.05)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", request)

    await node_sync_module._dispatch_users_removal_abort(
        [ProtoUser(email="1"), ProtoUser(email="2")],
        [ProtoUser(email="1", inbounds=["a"]), ProtoUser(email="2", inbounds=["b"])],
        "operation-7",
    )

    assert completed == ["1", "2"]


@pytest.mark.asyncio
async def test_remote_chunk_failure_aborts_every_possibly_applied_chunk(monkeypatch: pytest.MonkeyPatch):
    request = AsyncMock(side_effect=[{}, RuntimeError("second chunk failed"), {}, {}])
    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 1)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", request)
    removals = [ProtoUser(email="1"), ProtoUser(email="2")]
    originals = [ProtoUser(email="1", inbounds=["a"]), ProtoUser(email="2", inbounds=["b"])]

    with pytest.raises(node_sync_module.NodeRevocationError, match="second chunk failed"):
        await node_sync_module._dispatch_users_removal(removals, originals, {7})

    revocation_id = request.await_args_list[0].args[1]["revocation_id"]
    assert [item.args[0] for item in request.await_args_list] == [
        "revoke_users",
        "revoke_users",
        "abort_revoke_users",
        "abort_revoke_users",
    ]
    assert [item.args[1]["users"][0]["email"] for item in request.await_args_list] == ["1", "2", "1", "2"]
    assert all(item.args[1]["revocation_id"] == revocation_id for item in request.await_args_list)
    assert all(item.args[1]["expected_node_ids"] == [7] for item in request.await_args_list)
    assert [item.args[1]["original_users"][0]["email"] for item in request.await_args_list] == [
        "1",
        "2",
        "1",
        "2",
    ]


@pytest.mark.asyncio
async def test_remote_single_cancellation_aborts_ambiguous_applied_revoke(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    user = ProtoUser(email="single-cancel")
    revoke_started = asyncio.Event()
    calls = []

    async def request(action, payload):
        calls.append((action, payload))
        users = [user]
        if action == "revoke_user":
            manager._acquire_deletion_fences({user.email}, payload["revocation_id"])
            revoke_started.set()
            await asyncio.Future()
        else:
            await manager.abort_user_revocations(
                users,
                payload["revocation_id"],
                [ProtoUser(email=item["email"], inbounds=["active"]) for item in payload["original_users"]],
            )
        return {}

    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", request)

    task = asyncio.create_task(
        node_sync_module._dispatch_user_removal(user, ProtoUser(email=user.email, inbounds=["active"]))
    )
    await revoke_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert [action for action, _ in calls] == ["revoke_user", "abort_revoke_users"]
    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_remote_bulk_cancellation_aborts_acknowledged_and_inflight_chunks(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    second_started = asyncio.Event()
    calls = []

    async def request(action, payload):
        calls.append((action, payload))
        users = [ProtoUser(email=item["email"]) for item in payload["users"]]
        if action == "revoke_users":
            manager._acquire_deletion_fences({user.email for user in users}, payload["revocation_id"])
            if users[0].email == "bulk-2":
                second_started.set()
                await asyncio.Future()
        else:
            await manager.abort_user_revocations(
                users,
                payload["revocation_id"],
                [ProtoUser(email=item["email"], inbounds=["active"]) for item in payload["original_users"]],
            )
        return {}

    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 1)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", request)

    task = asyncio.create_task(
        node_sync_module._dispatch_users_removal(
            [ProtoUser(email="bulk-1"), ProtoUser(email="bulk-2")],
            [
                ProtoUser(email="bulk-1", inbounds=["active"]),
                ProtoUser(email="bulk-2", inbounds=["active"]),
            ],
        )
    )
    await second_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert [action for action, _ in calls] == [
        "revoke_users",
        "revoke_users",
        "abort_revoke_users",
        "abort_revoke_users",
    ]
    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_remote_bulk_lost_reply_aborts_applied_inflight_chunk(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()

    async def request(action, payload):
        users = [ProtoUser(email=item["email"]) for item in payload["users"]]
        if action == "revoke_users":
            manager._acquire_deletion_fences({user.email for user in users}, payload["revocation_id"])
            if users[0].email == "lost-reply-2":
                raise TimeoutError("reply was lost")
        else:
            await manager.abort_user_revocations(
                users,
                payload["revocation_id"],
                [ProtoUser(email=item["email"], inbounds=["active"]) for item in payload["original_users"]],
            )
        return {}

    monkeypatch.setattr(node_sync_module.runtime_settings, "role", Role.BACKEND)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 1)
    monkeypatch.setattr(node_sync_module.node_nats_client, "request", request)

    with pytest.raises(node_sync_module.NodeRevocationError, match="reply was lost"):
        await node_sync_module._dispatch_users_removal(
            [ProtoUser(email="lost-reply-1"), ProtoUser(email="lost-reply-2")],
            [
                ProtoUser(email="lost-reply-1", inbounds=["active"]),
                ProtoUser(email="lost-reply-2", inbounds=["active"]),
            ],
        )

    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_removal_without_an_active_runtime_node_is_a_noop():
    manager = NodeManager()

    await manager.revoke_users_and_wait([ProtoUser(email="1")])


@pytest.mark.asyncio
async def test_failed_permanent_removal_releases_the_update_fence(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    failed_update = AsyncMock(side_effect=RuntimeError("node unavailable"))
    monkeypatch.setattr(manager, "_update_users", failed_update)

    with pytest.raises(RuntimeError, match="node unavailable"):
        await manager.revoke_users_and_wait([ProtoUser(email="7")])

    assert "7" not in manager._deleted_user_keys


@pytest.mark.asyncio
async def test_child_cancelled_node_revocation_is_failure_and_releases_fences(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    manager._nodes = {1: _healthy_runtime_node(), 2: _healthy_runtime_node()}
    visited_nodes: set[int] = set()

    async def sync_node(node_id, _node, _users, **_kwargs):
        visited_nodes.add(node_id)
        if node_id == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(manager, "_sync_users_to_node", sync_node)

    with pytest.raises(node_sync_module.NodeRevocationError, match="failed to sync users to 1/2 nodes"):
        await manager.revoke_users_and_wait([ProtoUser(email="child-cancel")], "child-cancel-operation")

    assert visited_nodes == {1, 2}
    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_caller_cancelled_two_node_revocation_cancels_children_and_releases_fences(
    monkeypatch: pytest.MonkeyPatch,
):
    manager = NodeManager()
    manager._nodes = {1: _healthy_runtime_node(), 2: _healthy_runtime_node()}
    both_started = asyncio.Event()
    started_nodes: set[int] = set()
    cancelled_nodes: set[int] = set()

    async def sync_node(node_id, _node, _users, **_kwargs):
        started_nodes.add(node_id)
        if len(started_nodes) == 2:
            both_started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled_nodes.add(node_id)

    monkeypatch.setattr(manager, "_sync_users_to_node", sync_node)
    task = asyncio.create_task(
        manager.revoke_users_and_wait([ProtoUser(email="caller-cancel")], "caller-cancel-operation")
    )
    await both_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancelled_nodes == {1, 2}
    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("user_count", [1, 2])
async def test_cancelled_local_revocation_releases_single_and_bulk_fences(monkeypatch, user_count):
    manager = NodeManager()
    revocation_started = asyncio.Event()

    async def wait_forever(*_args, **_kwargs):
        revocation_started.set()
        await asyncio.Future()

    monkeypatch.setattr(manager, "_update_users", wait_forever)
    users = [ProtoUser(email=f"local-cancel-{index}") for index in range(user_count)]
    task = asyncio.create_task(manager.revoke_users_and_wait(users, "cancelled-operation"))
    await revocation_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_explicit_abort_releases_fence_and_allows_subsequent_sync():
    manager = NodeManager()
    removed_user = ProtoUser(email="8")
    revocation_id = await manager.revoke_users_and_wait([removed_user])
    assert "8" in manager._deleted_user_keys

    await manager.abort_user_revocations([removed_user], revocation_id, [removed_user])
    node = AsyncMock()
    manager._nodes[1] = node
    await manager.update_user(ProtoUser(email="8", inbounds=["active-inbound"]))

    assert "8" not in manager._deleted_user_keys
    node.update_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_concurrent_revocation_releases_only_its_own_fence(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    successful_revocation_started = asyncio.Event()
    allow_success = asyncio.Event()
    calls = 0

    async def interleaved_update(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            successful_revocation_started.set()
            await allow_success.wait()
            return
        raise RuntimeError("concurrent node failure")

    monkeypatch.setattr(manager, "_update_users", interleaved_update)
    user = ProtoUser(email="23")
    successful = asyncio.create_task(manager.revoke_users_and_wait([user], "successful-operation"))
    await successful_revocation_started.wait()

    with pytest.raises(RuntimeError, match="concurrent node failure"):
        await manager.revoke_users_and_wait([user], "failed-operation")
    allow_success.set()
    await successful

    assert manager._deletion_fence_owners == {"23": {"successful-operation"}}
    assert manager._deleted_user_keys == {"23"}
    await manager.abort_user_revocations([user], "failed-operation", [user])
    assert manager._deleted_user_keys == {"23"}


@pytest.mark.asyncio
async def test_concurrent_database_abort_releases_only_matching_revocation():
    manager = NodeManager()
    user = ProtoUser(email="24")

    await asyncio.gather(
        manager.revoke_users_and_wait([user], "committed-operation"),
        manager.revoke_users_and_wait([user], "rolled-back-operation"),
    )
    await manager.abort_user_revocations([user], "rolled-back-operation", [user])

    assert manager._deletion_fence_owners == {"24": {"committed-operation"}}
    assert manager._deleted_user_keys == {"24"}


@pytest.mark.asyncio
async def test_successful_finalize_clears_all_operation_owners_but_keeps_tombstone():
    manager = NodeManager()
    user = ProtoUser(email="25")

    await asyncio.gather(
        manager.revoke_users_and_wait([user], "committed-operation"),
        manager.revoke_users_and_wait([user], "rolled-back-operation"),
    )
    await manager.finalize_user_revocations([user], "committed-operation")
    await manager.abort_user_revocations([user], "rolled-back-operation", [user])

    assert manager._deleted_user_keys == {"25"}
    assert manager._deletion_fence_owners == {}

    await manager.revoke_users_and_wait([user], "stale-duplicate")
    await manager.abort_user_revocations([user], "stale-duplicate", [user])
    assert manager._deleted_user_keys == {"25"}
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_legacy_revoke_and_abort_without_id_use_same_deterministic_owner():
    manager = NodeManager()
    users = [ProtoUser(email="legacy-2"), ProtoUser(email="legacy-1")]

    revocation_id = await manager.revoke_users_and_wait(users)
    assert revocation_id == manager._resolve_revocation_id(list(reversed(users)), None)
    assert revocation_id.startswith("legacy:")

    await manager.abort_user_revocations(list(reversed(users)), restore_users=list(reversed(users)))
    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_legacy_worker_revoke_and_abort_without_id_pair(monkeypatch):
    manager = NodeManager()
    service = node_worker_module.NodeWorkerService.__new__(node_worker_module.NodeWorkerService)
    monkeypatch.setattr(node_worker_module, "node_manager", manager)
    payload = {
        "users": [{"email": "legacy-worker"}],
        "original_users": [{"email": "legacy-worker", "inbounds": ["active"]}],
    }

    await service._rpc_revoke_users(payload)
    assert manager._deleted_user_keys == {"legacy-worker"}
    await service._rpc_abort_revoke_users(payload)

    assert manager._deleted_user_keys == set()
    assert manager._deletion_fence_owners == {}


@pytest.mark.asyncio
async def test_permanent_removal_fences_a_concurrent_single_update(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    node = _healthy_runtime_node()
    stale_update_reached_snapshot = asyncio.Event()
    allow_stale_update_to_continue = asyncio.Event()
    snapshot_calls = 0

    async def snapshot_nodes():
        nonlocal snapshot_calls
        snapshot_calls += 1
        if snapshot_calls == 1:
            stale_update_reached_snapshot.set()
            await allow_stale_update_to_continue.wait()
        return [(1, node)]

    removal_batches = AsyncMock(return_value=0)
    monkeypatch.setattr(manager, "_snapshot_node_items", snapshot_nodes)
    monkeypatch.setattr(manager, "_sync_user_batch_to_node", removal_batches)
    active_user = ProtoUser(email="41", inbounds=["active-inbound"])
    removed_user = ProtoUser(email="41")
    revocation_id = manager._resolve_revocation_id([removed_user], None)

    stale_update = asyncio.create_task(manager.update_user(active_user))
    await stale_update_reached_snapshot.wait()
    await manager.revoke_users_and_wait([removed_user])
    assert "41" in manager._deleted_user_keys
    allow_stale_update_to_continue.set()
    await stale_update

    node.update_user.assert_not_awaited()
    removal_batches.assert_awaited_once_with(
        node,
        [removed_user],
        revocation_id=revocation_id,
    )


@pytest.mark.asyncio
async def test_permanent_removal_fences_a_concurrent_bulk_update(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    node = _healthy_runtime_node()
    stale_update_reached_snapshot = asyncio.Event()
    allow_stale_update_to_continue = asyncio.Event()
    snapshot_calls = 0

    async def snapshot_nodes():
        nonlocal snapshot_calls
        snapshot_calls += 1
        if snapshot_calls == 1:
            stale_update_reached_snapshot.set()
            await allow_stale_update_to_continue.wait()
        return [(1, node)]

    sync_batches = AsyncMock(return_value=0)
    monkeypatch.setattr(manager, "_snapshot_node_items", snapshot_nodes)
    monkeypatch.setattr(manager, "_sync_user_batch_to_node", sync_batches)
    active_user = ProtoUser(email="52", inbounds=["active-inbound"])
    removed_user = ProtoUser(email="52")
    revocation_id = manager._resolve_revocation_id([removed_user], None)

    stale_update = asyncio.create_task(manager._update_users([active_user]))
    await stale_update_reached_snapshot.wait()
    await manager.revoke_users_and_wait([removed_user])
    allow_stale_update_to_continue.set()
    await stale_update

    sync_batches.assert_awaited_once_with(
        node,
        [removed_user],
        revocation_id=revocation_id,
    )

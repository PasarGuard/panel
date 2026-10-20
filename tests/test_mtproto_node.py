from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from PasarGuardNodeBridge import Health, NodeAPIError
from PasarGuardNodeBridge.common import service_pb2 as service

from app.db.models import CoreType, NodeStatus
from app.models.protocol import ProxyProtocol
from app.node import user as node_user_module
from app.operation import OperatorType, node as node_operation_module
from app.operation.node import NodeOperation

SECRET = "00112233445566778899aabbccddeeff"
MTPROTO_ONLY = frozenset({ProxyProtocol.mtproto})
INFO = SimpleNamespace(node_version="0.5.4", core_version="3.5.14")


def _serialize(settings: dict):
    return node_user_module._serialize_user_for_node(7, settings, ["mtp"], MTPROTO_ONLY)


def test_serializer_skips_user_without_valid_secret():
    for settings in (
        {},
        {"mtproto": {}},
        {"mtproto": {"secret": None}},
        {"mtproto": {"secret": ""}},
        {"mtproto": {"secret": "zz"}},
        {"mtproto": "x"},
    ):
        proto = _serialize(settings)
        assert not proto.proxies.HasField("mtproto"), settings
        assert proto.email == "7"
        assert list(proto.inbounds) == ["mtp"]


def test_serializer_sanitizes_policy_fields():
    proto = _serialize(
        {
            "mtproto": {
                "secret": SECRET.upper(),
                "user_ad_tag": "nothex",
                "max_tcp_conns": True,
                "max_unique_ips": 4294967296,
            }
        }
    )
    assert proto.proxies.mtproto.secret == SECRET
    assert proto.proxies.mtproto.user_ad_tag == ""
    assert proto.proxies.mtproto.max_tcp_conns == 0
    assert proto.proxies.mtproto.max_unique_ips == 0

    proto = _serialize(
        {"mtproto": {"secret": SECRET, "user_ad_tag": "AB" * 16, "max_tcp_conns": 5, "max_unique_ips": 2}}
    )
    assert proto.proxies.mtproto.secret == SECRET
    assert proto.proxies.mtproto.user_ad_tag == "ab" * 16
    assert proto.proxies.mtproto.max_tcp_conns == 5
    assert proto.proxies.mtproto.max_unique_ips == 2


def test_node_email_is_numeric_user_id():
    proto = node_user_module._serialize_user_for_node(123, {}, [], None)
    assert proto.email == "123"
    assert not proto.email.startswith("pgm_")


def test_backend_type_for_core():
    backend_type_for_core = node_operation_module.backend_type_for_core
    assert backend_type_for_core(None) == service.BackendType.XRAY
    assert backend_type_for_core(CoreType.xray) == service.BackendType.XRAY
    assert backend_type_for_core(CoreType.wg) == service.BackendType.WIREGUARD
    assert backend_type_for_core(CoreType.mtproto) == service.BackendType.MTPROTO == 2
    assert backend_type_for_core(CoreType.singbox) is None


def _not_connected_bridge_node():
    return SimpleNamespace(get_health=AsyncMock(return_value=Health.NOT_CONNECTED))


def _patch_connect(monkeypatch: pytest.MonkeyPatch, start_or_attach: AsyncMock, attach: AsyncMock | None = None):
    pg_node = _not_connected_bridge_node()
    monkeypatch.setattr(node_operation_module.node_manager, "get_node", AsyncMock(return_value=pg_node))
    monkeypatch.setattr(NodeOperation, "_start_or_attach_node", start_or_attach)
    monkeypatch.setattr(NodeOperation, "_attach_if_running", attach or AsyncMock(return_value=None))
    return pg_node


@pytest.mark.asyncio
async def test_connect_node_rejects_unknown_core_type(monkeypatch: pytest.MonkeyPatch):
    start_or_attach = AsyncMock(return_value=INFO)
    _patch_connect(monkeypatch, start_or_attach)
    db_node = SimpleNamespace(id=5, name="singbox-node", status=NodeStatus.connecting)

    result = await NodeOperation.connect_node(db_node, SimpleNamespace(type=CoreType.singbox), [])

    assert result["status"] == NodeStatus.error
    assert "singbox" in result["message"]
    start_or_attach.assert_not_awaited()
    assert 5 not in NodeOperation._in_flight_connects


@pytest.mark.asyncio
async def test_mtproto_start_uses_long_timeout():
    async def start(core_type, default_timeout: int, backend_type) -> dict:
        pg_node = SimpleNamespace(start=AsyncMock(return_value=INFO), stop=AsyncMock())
        db_node = SimpleNamespace(name="n", keep_alive=60, default_timeout=default_timeout)
        core = SimpleNamespace(type=core_type, to_str=lambda: "{}", exclude_inbound_tags=[])
        await NodeOperation._start_or_attach_node(pg_node, db_node, core, [], backend_type, force_start=True)
        return pg_node.start.await_args.kwargs

    assert (await start(CoreType.mtproto, 10, service.BackendType.MTPROTO))["timeout"] == 100
    assert (await start(CoreType.mtproto, 300, service.BackendType.MTPROTO))["timeout"] == 300
    assert "timeout" not in await start(CoreType.xray, 10, service.BackendType.XRAY)


@pytest.mark.asyncio
async def test_first_mtproto_start_timeout_is_retried_not_failed(monkeypatch: pytest.MonkeyPatch):
    start_or_attach = AsyncMock(side_effect=NodeAPIError(-1, "Request timed out"))
    attach = AsyncMock(return_value=None)
    _patch_connect(monkeypatch, start_or_attach, attach)
    db_node = SimpleNamespace(id=41, name="mtproto-node", status=NodeStatus.connected)
    core = SimpleNamespace(type=CoreType.mtproto)

    try:
        assert await NodeOperation.connect_node(db_node, core, []) is None
        assert attach.await_count == 1

        second = await NodeOperation.connect_node(db_node, core, [])
        assert second["status"] == NodeStatus.error
        assert second["message"] == "Request timed out"
        assert 41 not in NodeOperation._mtproto_start_timeouts

        assert await NodeOperation.connect_node(db_node, core, []) is None
        start_or_attach.side_effect = None
        start_or_attach.return_value = INFO
        connected = await NodeOperation.connect_node(db_node, core, [])
        assert connected["status"] == NodeStatus.connected
        assert 41 not in NodeOperation._mtproto_start_timeouts
    finally:
        NodeOperation._mtproto_start_timeouts.clear()


@pytest.mark.asyncio
async def test_forced_mtproto_start_timeout_gets_its_own_retry(monkeypatch: pytest.MonkeyPatch):
    _patch_connect(monkeypatch, AsyncMock(side_effect=NodeAPIError(-1, "Request timed out")))
    db_node = SimpleNamespace(id=44, name="mtproto-node", status=NodeStatus.connected)
    core = SimpleNamespace(type=CoreType.mtproto)

    try:
        # A count left over from a start that later attached outside connect_node.
        NodeOperation._mtproto_start_timeouts[44] = 1
        assert await NodeOperation.connect_node(db_node, core, [], force_start=True) is None
        assert NodeOperation._mtproto_start_timeouts[44] == 1
    finally:
        NodeOperation._mtproto_start_timeouts.clear()


@pytest.mark.asyncio
async def test_xray_start_timeout_still_reports_error(monkeypatch: pytest.MonkeyPatch):
    _patch_connect(monkeypatch, AsyncMock(side_effect=NodeAPIError(-1, "Request timed out")))
    db_node = SimpleNamespace(id=42, name="xray-node", status=NodeStatus.connected)

    try:
        result = await NodeOperation.connect_node(db_node, SimpleNamespace(type=CoreType.xray), [])
        assert result["status"] == NodeStatus.error
        assert result["message"] == "Request timed out"
        assert 42 not in NodeOperation._mtproto_start_timeouts
    finally:
        NodeOperation._mtproto_start_timeouts.clear()


@pytest.mark.asyncio
async def test_old_node_invalid_backend_type_message(monkeypatch: pytest.MonkeyPatch):
    _patch_connect(monkeypatch, AsyncMock(side_effect=NodeAPIError(500, "invalid backend type")))
    db_node = SimpleNamespace(id=43, name="old-node", status=NodeStatus.connecting)

    result = await NodeOperation.connect_node(db_node, SimpleNamespace(type=CoreType.mtproto), [])

    assert result["status"] == NodeStatus.error
    assert result["message"] == node_operation_module.MTPROTO_UNSUPPORTED_NODE_MESSAGE
    assert "next node release" in result["message"]


@pytest.mark.asyncio
async def test_bulk_connect_continues_after_old_mtproto_node(monkeypatch: pytest.MonkeyPatch):
    xray_core = SimpleNamespace(type=CoreType.xray)
    mtproto_core = SimpleNamespace(type=CoreType.mtproto)
    nodes = [
        SimpleNamespace(id=1, name="xray-node", status=NodeStatus.connecting, core_config_id=1),
        SimpleNamespace(id=2, name="old-mtproto-node", status=NodeStatus.connecting, core_config_id=2),
    ]
    bridge_nodes = {node.id: _not_connected_bridge_node() for node in nodes}

    async def start_or_attach(pg_node, db_node, core, users, backend_type, *, force_start=False):
        if core is mtproto_core:
            raise NodeAPIError(500, "invalid backend type")
        return INFO

    monkeypatch.setattr(node_operation_module.node_manager, "update_node", AsyncMock())
    monkeypatch.setattr(
        node_operation_module.node_manager, "get_node", AsyncMock(side_effect=lambda node_id: bridge_nodes[node_id])
    )
    monkeypatch.setattr(
        NodeOperation,
        "_get_core_users_map",
        AsyncMock(return_value=({1: xray_core, 2: mtproto_core}, {1: [], 2: []})),
    )
    monkeypatch.setattr(NodeOperation, "_start_or_attach_node", AsyncMock(side_effect=start_or_attach))
    monkeypatch.setattr(NodeOperation, "_attach_if_running", AsyncMock(return_value=None))
    bulk_update = AsyncMock()
    monkeypatch.setattr(node_operation_module, "bulk_update_node_status", bulk_update)
    monkeypatch.setattr(node_operation_module.notification, "connect_node", AsyncMock())
    monkeypatch.setattr(node_operation_module.notification, "error_node", AsyncMock())

    await NodeOperation.__new__(NodeOperation)._connect_nodes_bulk_local(object(), nodes)

    bulk_update.assert_awaited_once()
    results = {result["node_id"]: result for result in bulk_update.await_args.args[1]}
    assert len(results) == 2
    assert results[1]["status"] == NodeStatus.connected
    assert results[2]["status"] == NodeStatus.error
    assert results[2]["message"] == node_operation_module.MTPROTO_UNSUPPORTED_NODE_MESSAGE


@pytest.mark.asyncio
async def test_manual_mtproto_sync_still_applying_is_not_node_error(monkeypatch: pytest.MonkeyPatch):
    error = NodeAPIError(500, "failed to update users: the users are still being applied: context deadline exceeded")
    db_node = SimpleNamespace(id=7, name="mtproto-node", status=NodeStatus.connected, core_config_id=3)

    async def sync(core_type):
        core = SimpleNamespace(type=core_type)
        operation = NodeOperation(OperatorType.API)
        update_status = AsyncMock()
        monkeypatch.setattr(operation, "get_validated_node", AsyncMock(return_value=db_node))
        monkeypatch.setattr(node_operation_module.node_manager, "get_node", AsyncMock(return_value=object()))
        monkeypatch.setattr(node_operation_module.node_manager, "sync_full", AsyncMock(side_effect=error))
        monkeypatch.setattr(node_operation_module.core_manager, "get_core", AsyncMock(return_value=core))
        monkeypatch.setattr(NodeOperation, "_get_core_users_map", AsyncMock(return_value=({3: core}, {3: []})))
        monkeypatch.setattr(node_operation_module, "update_node_status", update_status)
        with pytest.raises(HTTPException) as exc_info:
            await operation._sync_node_users_local(object(), 7, False)
        return exc_info.value, update_status

    exc, update_status = await sync(CoreType.mtproto)
    assert exc.status_code == 409
    assert exc.detail == node_operation_module.MTPROTO_SYNC_PENDING_MESSAGE
    update_status.assert_not_awaited()

    exc, update_status = await sync(CoreType.xray)
    assert exc.status_code == 500
    assert exc.detail == error.detail
    update_status.assert_awaited_once()


def test_is_mtproto_retry_later_error():
    is_retry_later = node_operation_module.is_mtproto_retry_later_error
    assert is_retry_later(NodeAPIError(-1, "Request timed out"))
    assert is_retry_later(NodeAPIError(-1, "Timeout error: "))
    assert is_retry_later(NodeAPIError(504, "x"))
    assert is_retry_later(NodeAPIError(500, "failed to update users: the users are still being applied"))
    assert is_retry_later(NodeAPIError(500, "context deadline exceeded"))
    assert not is_retry_later(NodeAPIError(-1, "Channel initialization failed: x"))
    assert not is_retry_later(NodeAPIError(500, "invalid backend type"))

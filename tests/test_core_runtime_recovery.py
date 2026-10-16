import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from PasarGuardNodeBridge import Health, NodeAPIError
from PasarGuardNodeBridge.common import service_pb2 as service
from sqlalchemy import delete, update
from sqlalchemy.exc import OperationalError, TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.manager as cm
import app.operation.node as no
from app.db.models import CoreConfig, CoreType, NodeStatus
from app.nats.kv_cas import MemoryCasKv
from app.operation import OperatorType
from app.utils.crypto import generate_wireguard_keypair


def xray_config(port=20001):
    return {
        "inbounds": [
            {"tag": "vless-in", "port": port, "protocol": "vless", "settings": {"clients": [], "decryption": "none"}}
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
    }


def snapshot_kv():
    kv = MemoryCasKv()

    async def put(key, value):
        if key in kv._data:
            return await kv.update(key, value)
        return await kv.create(key, value)

    kv.put = put
    return kv


@pytest.mark.asyncio
@pytest.mark.parametrize("alpn", [[], ["h2"], ["h2", "http/1.1"]])
async def test_tls_defaults_reach_subscription_and_host_overrides_win(manager, monkeypatch, alpn):
    from app.core import hosts
    from app.models.host import BaseHost
    from app.subscription.links import StandardLinks
    from app.subscription.xray import XrayConfiguration

    config = xray_config()
    config["inbounds"][0]["streamSettings"] = {
        "security": "tls",
        "network": "tcp",
        "tlsSettings": {"fingerprint": "chrome", "alpn": alpn, "serverName": "example.com", "certificates": []},
    }
    manager._cores = {1: manager.validate_core(config, type=CoreType.xray)}
    await manager.update_inbounds()
    monkeypatch.setattr(hosts, "core_manager", manager)
    default = await hosts._prepare_subscription_inbound_data(
        BaseHost(remark="tls", inbound_tag="vless-in", address={"example.com"}, priority=0)
    )
    assert default.tls_config.fingerprint == "chrome"
    assert default.tls_config.alpn_list == alpn
    payload = {}
    StandardLinks()._apply_tls_settings(payload, default.tls_config)
    assert payload["fp"] == "chrome"
    assert payload.get("alpn") == (",".join(alpn) if alpn else None)
    xray_tls = XrayConfiguration()._apply_tls(default.tls_config, "tls")
    assert xray_tls["fingerprint"] == "chrome"
    assert xray_tls.get("alpn") == (alpn if alpn else None)
    overridden = await hosts._prepare_subscription_inbound_data(
        BaseHost(
            remark="tls",
            inbound_tag="vless-in",
            address={"example.com"},
            priority=0,
            fingerprint="firefox",
            alpn=["h3"],
        )
    )
    assert overridden.tls_config.fingerprint == "firefox"
    assert overridden.tls_config.alpn_list == ["h3"]


@pytest_asyncio.fixture
async def dbs():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(CoreConfig.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    key, _ = generate_wireguard_keypair()
    async with sessions() as db:
        db.add(CoreConfig(name="xray", config=xray_config(), type=CoreType.xray))
        db.add(
            CoreConfig(
                name="wg",
                type=CoreType.wg,
                config={
                    "interface_name": "wg0",
                    "private_key": key,
                    "listen_port": 51820,
                    "address": ["10.0.0.1/24"],
                },
            )
        )
        await db.commit()
    yield sessions
    await engine.dispose()


@pytest.fixture
def manager(monkeypatch):
    result = cm.CoreManager()
    result._nats_enabled = False
    monkeypatch.setattr(no, "core_manager", result)
    monkeypatch.setattr(cm.router, "register_handler", lambda *args: None)
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot", ["stale", "partial", "malformed"])
async def test_startup_uses_db_even_with_unusable_or_outdated_kv(dbs, manager, monkeypatch, snapshot):
    stale = manager.validate_core(xray_config(10001), type=CoreType.xray)
    state = {"cores": {"1": stale.to_json()}, "inbounds": ["obsolete"], "inbounds_by_tag": {}}
    if snapshot == "partial":
        state["cores"] = {}
    raw = b"not-json" if snapshot == "malformed" else json.dumps(state).encode()
    kv = snapshot_kv()
    await kv.create("state", raw)
    get = AsyncMock(wraps=kv.get)
    kv.get = get
    manager._nats_enabled = True
    monkeypatch.setattr(cm, "setup_nats_kv", AsyncMock(return_value=(None, None, kv)))
    async with dbs() as db:
        await manager.initialize(db)
    get.assert_not_awaited()
    cores = await manager.get_cores()
    assert set(cores) == {1, 2}
    assert cores[1]["inbounds"][0]["port"] == 20001
    assert cores[2].type == CoreType.wg
    assert set(await manager.get_inbounds()) == {"vless-in", "wg0"}


@pytest.mark.asyncio
@pytest.mark.parametrize("core_id,backend", [(1, service.BackendType.XRAY), (2, service.BackendType.WIREGUARD)])
@pytest.mark.parametrize("bulk", [False, True])
async def test_restart_reads_committed_core_and_correct_users(dbs, manager, monkeypatch, core_id, backend, bulk):
    manager._cores = {1: manager.validate_core(xray_config(10001), type=CoreType.xray)}
    db_node = SimpleNamespace(id=91, name="node", status=NodeStatus.connected, core_config_id=core_id, keep_alive=60)
    info = SimpleNamespace(started=True, node_version="0.5.4", core_version="test")
    node = SimpleNamespace(
        get_health=AsyncMock(return_value=Health.HEALTHY), start=AsyncMock(return_value=info), stop=AsyncMock()
    )
    monkeypatch.setattr(no, "get_node_by_id", AsyncMock(return_value=db_node))
    monkeypatch.setattr(no.node_manager, "update_node", AsyncMock(return_value=node))
    monkeypatch.setattr(no.node_manager, "get_node", AsyncMock(return_value=node))
    users = AsyncMock(return_value=[])
    monkeypatch.setattr(no, "core_users", users)
    monkeypatch.setattr(no, "update_node_status", AsyncMock())
    monkeypatch.setattr(no, "bulk_update_node_status", AsyncMock())
    operator = no.NodeOperation.__new__(no.NodeOperation)
    async with dbs() as db:
        if bulk:
            await operator._connect_nodes_bulk_local(db, [db_node], force_start=True)
        else:
            await operator._connect_single_node_local(db, 91, force_start=True)
    node.stop.assert_awaited_once()
    node.start.assert_awaited_once()
    args = node.start.await_args.kwargs
    assert args["backend_type"] == backend
    config = json.loads(args["config"])
    assert config["inbounds"][0]["port"] == 20001 if core_id == 1 else config["interface_name"] == "wg0"
    assert users.await_args.kwargs["inbound_tags"] == (["vless-in"] if core_id == 1 else ["wg0"])


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [False, True])
async def test_missing_or_invalid_core_never_starts_default_or_flushes_users(dbs, manager, monkeypatch, invalid):
    async with dbs() as db:
        await manager.initialize(db)
        if invalid:
            await db.execute(update(CoreConfig).where(CoreConfig.id == 2).values(config={"invalid": True}))
        else:
            await db.execute(delete(CoreConfig).where(CoreConfig.id == 2))
        await db.commit()
        cores, users = await no.NodeOperation._get_core_users_map(db, {2}, lazy=True)
        assert cores[2] is None
        with pytest.raises(NodeAPIError) as exc:
            await users[2]()
        assert exc.value.code == 409
    node = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(no.node_manager, "get_node", AsyncMock(return_value=node))
    db_node = SimpleNamespace(id=91, status=NodeStatus.connected, core_config_id=2)
    result = await no.NodeOperation.connect_node(db_node, None, users[2], force_start=True)
    assert result["status"] == NodeStatus.error
    assert result["message"] == "Core config 2 is missing or invalid"
    node.start.assert_not_awaited()
    node.stop.assert_not_awaited()
    assert await manager.get_core(2) is None
    assert await manager.get_core(1) is not None
    assert await manager.get_inbounds() == ["vless-in"]


@pytest.mark.asyncio
async def test_missing_core_sync_does_not_send_empty_snapshot(dbs, manager, monkeypatch):
    node = SimpleNamespace(sync_users=AsyncMock())
    db_node = SimpleNamespace(id=91, status=NodeStatus.connected, core_config_id=999)
    operator = no.NodeOperation(operator_type=OperatorType.API)
    monkeypatch.setattr(operator, "get_validated_node", AsyncMock(return_value=db_node))
    monkeypatch.setattr(no.node_manager, "get_node", AsyncMock(return_value=node))

    async def sync_full(node_id, users, **kwargs):
        await node.sync_users(await users())

    monkeypatch.setattr(no.node_manager, "sync_full", sync_full)
    monkeypatch.setattr(no, "update_node_status", AsyncMock())
    from fastapi import HTTPException

    async with dbs() as db:
        with pytest.raises(HTTPException) as exc:
            await operator._sync_node_users_local(db, 91, True)
    assert exc.value.status_code == 409
    node.sync_users.assert_not_awaited()


@pytest.mark.asyncio
async def test_identity_map_is_refreshed_without_new_session(dbs, manager):
    async with dbs() as reader:
        row = await reader.get(CoreConfig, 1)
        assert row.config["inbounds"][0]["port"] == 20001
        async with dbs() as writer:
            await writer.execute(update(CoreConfig).where(CoreConfig.id == 1).values(config=xray_config(30001)))
            await writer.commit()
        cores = await manager.get_cores({1}, db=reader)
        assert cores[1]["inbounds"][0]["port"] == 30001
        assert row.config["inbounds"][0]["port"] == 30001


@pytest.mark.asyncio
async def test_delayed_update_and_remove_messages_use_current_db(dbs, manager, monkeypatch):
    monkeypatch.setattr(cm, "GetDB", dbs)
    await manager.reload()
    delayed_payload = {"id": 1, "type": "xray", "config": xray_config(10001)}
    await manager._handle_core_message({"action": "update", "core": delayed_payload})
    assert (await manager.get_core(1))["inbounds"][0]["port"] == 20001
    await manager._handle_core_message({"action": "remove", "core_id": 1})
    assert await manager.get_core(1) is not None
    async with dbs() as db:
        await db.execute(delete(CoreConfig).where(CoreConfig.id == 2))
        await db.commit()
    await manager._handle_core_message({"action": "update", "core": {"id": 2, "config": {"old": True}}})
    assert await manager.get_core(2) is None
    assert set(await manager.get_inbounds()) == {"vless-in"}


@pytest.mark.asyncio
async def test_database_failure_preserves_cached_state_and_blocks_restart(dbs, manager, monkeypatch):
    async with dbs() as db:
        await manager.initialize(db)
    before = await manager.get_cores()
    failing_db = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("database unavailable")))
    with pytest.raises(RuntimeError, match="database unavailable"):
        await no.NodeOperation._get_core_users_map(failing_db, {2}, lazy=True)
    assert await manager.get_cores() == before


@pytest.mark.asyncio
async def test_empty_selection_does_not_query_or_drop_other_cores(dbs, manager):
    async with dbs() as db:
        await manager.initialize(db)
    empty_db = SimpleNamespace(execute=AsyncMock())
    assert await manager.get_cores(set(), db=empty_db) == {}
    empty_db.execute.assert_not_awaited()
    assert set(await manager.get_cores()) == {1, 2}


@pytest.mark.asyncio
async def test_default_core_is_used_only_for_unassigned_nodes(dbs, manager, monkeypatch):
    db_node = SimpleNamespace(id=91, name="node", status=NodeStatus.connected, core_config_id=None, keep_alive=60)
    info = SimpleNamespace(started=True, node_version="0.5.4", core_version="test")
    node = SimpleNamespace(start=AsyncMock(return_value=info), stop=AsyncMock())
    monkeypatch.setattr(no, "get_node_by_id", AsyncMock(return_value=db_node))
    monkeypatch.setattr(no.node_manager, "update_node", AsyncMock(return_value=node))
    monkeypatch.setattr(no.node_manager, "get_node", AsyncMock(return_value=node))
    monkeypatch.setattr(no, "core_users", AsyncMock(return_value=[]))
    monkeypatch.setattr(no, "update_node_status", AsyncMock())
    operator = no.NodeOperation.__new__(no.NodeOperation)
    async with dbs() as db:
        await operator._connect_single_node_local(db, 91, force_start=True)
    assert node.start.await_args.kwargs["backend_type"] == service.BackendType.XRAY


@pytest.mark.asyncio
async def test_host_startup_rebuilds_old_tls_snapshot(dbs, manager, monkeypatch):
    from app.core import hosts
    from app.models.host import BaseHost

    config = xray_config()
    config["inbounds"][0]["streamSettings"] = {
        "security": "tls",
        "network": "tcp",
        "tlsSettings": {"fingerprint": "chrome", "alpn": ["h2"], "certificates": []},
    }
    manager._cores = {1: manager.validate_core(config, type=CoreType.xray)}
    await manager.update_inbounds()
    monkeypatch.setattr(hosts, "core_manager", manager)
    host = BaseHost(id=91, remark="tls", inbound_tag="vless-in", address={"example.com"}, priority=0)
    old_data = (await hosts._prepare_subscription_inbound_data(host)).model_dump()
    old_data["tls_config"]["fingerprint"] = ""
    old_data["tls_config"]["alpn_list"] = []
    kv = snapshot_kv()
    await kv.create("state", json.dumps({"91": old_data}).encode())
    host_manager = hosts.HostManager()
    host_manager._nats_enabled = True
    monkeypatch.setattr(hosts, "setup_nats_kv", AsyncMock(return_value=(None, None, kv)))
    monkeypatch.setattr(hosts, "get_hosts", AsyncMock(return_value=[host]))
    monkeypatch.setattr(hosts, "upsert_inbounds", AsyncMock())
    async with dbs() as db:
        await host_manager.setup(db)
    corrected = await host_manager.get_host(91)
    assert corrected["tls_config"]["fingerprint"] == "chrome"
    assert corrected["tls_config"]["alpn_list"] == ["h2"]
    assert json.loads((await kv.get("state_v2")).value)["91"]["tls_config"]["fingerprint"] == "chrome"


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
@pytest.mark.parametrize("force_start", [False, True])
@pytest.mark.parametrize("error_kind", ["connection", "pool_timeout", "query_timeout"])
async def test_transient_db_failure_never_interrupts_healthy_nodes(
    dbs, manager, monkeypatch, bulk, force_start, error_kind
):
    async with dbs() as db:
        await manager.initialize(db)
    previous_cores = await manager.get_cores()
    previous_index = await manager.get_inbounds_by_tag()
    errors = {
        "connection": OperationalError("select", {}, RuntimeError("offline")),
        "pool_timeout": PoolTimeoutError("pool exhausted"),
        "query_timeout": TimeoutError("query timed out"),
    }
    error = errors[error_kind]
    failing_db = SimpleNamespace(execute=AsyncMock(side_effect=error))
    db_node = SimpleNamespace(id=91, name="healthy", status=NodeStatus.connected, core_config_id=2)
    node = SimpleNamespace(start=AsyncMock(), stop=AsyncMock(), sync_users=AsyncMock())
    monkeypatch.setattr(no, "get_node_by_id", AsyncMock(return_value=db_node))
    update_node = AsyncMock(return_value=node)
    monkeypatch.setattr(no.node_manager, "update_node", update_node)
    monkeypatch.setattr(no.node_manager, "get_node", AsyncMock(return_value=node))
    update_status = AsyncMock()
    bulk_update_status = AsyncMock()
    monkeypatch.setattr(no, "update_node_status", update_status)
    monkeypatch.setattr(no, "bulk_update_node_status", bulk_update_status)
    operator = no.NodeOperation.__new__(no.NodeOperation)
    with pytest.raises(type(error)):
        if bulk:
            await operator._connect_nodes_bulk_local(failing_db, [db_node], force_start=force_start)
        else:
            await operator._connect_single_node_local(failing_db, 91, force_start=force_start)
    update_node.assert_not_awaited()
    update_status.assert_not_awaited()
    bulk_update_status.assert_not_awaited()
    node.start.assert_not_awaited()
    node.stop.assert_not_awaited()
    node.sync_users.assert_not_awaited()
    assert db_node.status == NodeStatus.connected
    assert await manager.get_cores() == previous_cores
    assert await manager.get_inbounds_by_tag() == previous_index


@pytest.mark.asyncio
async def test_missing_core_error_is_persisted_without_restarting_node(dbs, manager, monkeypatch):
    db_node = SimpleNamespace(id=91, name="node", status=NodeStatus.connected, core_config_id=999)
    node = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(no, "get_node_by_id", AsyncMock(return_value=db_node))
    monkeypatch.setattr(no.node_manager, "update_node", AsyncMock(return_value=node))
    monkeypatch.setattr(no.node_manager, "get_node", AsyncMock(return_value=node))
    update_status = AsyncMock()
    monkeypatch.setattr(no, "update_node_status", update_status)
    notify = AsyncMock()
    monkeypatch.setattr(no.notification, "error_node", notify)
    operator = no.NodeOperation.__new__(no.NodeOperation)
    async with dbs() as db:
        assert await operator._connect_single_node_local(db, 91, force_start=True)
    assert update_status.await_args.kwargs["status"] == NodeStatus.error
    assert update_status.await_args.kwargs["message"] == "Core config 999 is missing or invalid"
    node.start.assert_not_awaited()
    node.stop.assert_not_awaited()
    await asyncio.sleep(0)
    assert notify.await_args.args[0].message == "Core config 999 is missing or invalid"

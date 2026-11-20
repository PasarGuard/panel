"""After a NATS reconnect a worker rebuilds the state whose worker_sync messages it may have missed."""

import asyncio
import json
from copy import deepcopy

import pytest
from fastapi import status

from app.core import hosts as hosts_module
from app.core.hosts import HostManager, host_manager
from app.core.manager import core_manager
from app.db.models import CoreConfig, Node, NodeStatus, ProxyHost
from app.models.host import BaseHost
from app.nats.kv_cas import MemoryCasKv
from app.nats.message import MessageTopic
from app.nats.router import router
from tests.api import GetTestDB, client
from tests.api.helpers import auth_headers, create_core, delete_core, get_inbounds, unique_name
from tests.api.sample_data import XRAY_CONFIG


@pytest.fixture
def fast_router(monkeypatch: pytest.MonkeyPatch):
    # Only what a test registers takes part in the resync
    monkeypatch.setattr(router, "_resync_handlers", {})
    monkeypatch.setattr(router, "_handlers", dict(router._handlers))
    monkeypatch.setattr(router, "_dispatch_locks", {})
    monkeypatch.setattr(router, "RESYNC_DELAY", 0)
    monkeypatch.setattr(router, "RESYNC_JITTER", 0)
    monkeypatch.setattr("app.core.hosts.GetDB", GetTestDB)
    return router


async def _reconnect():
    await router._on_reconnected()
    await router._resync_task


async def _host_manager_setup():
    # Startup path, which also registers the host resync; NATS stays off (see test_host_download_host)
    nats_enabled = host_manager._nats_enabled
    host_manager._nats_enabled = False
    try:
        async with GetTestDB() as db:
            await host_manager.setup(db)
    finally:
        host_manager._nats_enabled = nats_enabled


async def _change_behind_the_managers_back(changed_id: int, remark: str, deleted_id: int):
    # What another worker did while this one was cut off from NATS: only the database knows
    async with GetTestDB() as db:
        (await db.get(ProxyHost, changed_id)).remark = remark
        await db.delete(await db.get(ProxyHost, deleted_id))
        await db.commit()


def test_reconnect_serves_hosts_changed_and_deleted_during_the_outage(access_token, fast_router):
    headers = auth_headers(access_token)
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    host_ids = []
    try:
        for name in ("kept", "dropped"):
            response = client.post(
                "/api/host",
                headers=headers,
                json={
                    "remark": unique_name(name),
                    "address": ["127.0.0.1"],
                    "port": 443,
                    "inbound_tag": inbound,
                    "priority": 1,
                },
            )
            assert response.status_code == status.HTTP_201_CREATED, response.text
            host_ids.append(response.json()["id"])
        kept_id, dropped_id = host_ids
        asyncio.run(_host_manager_setup())

        new_remark = unique_name("changed")
        asyncio.run(_change_behind_the_managers_back(kept_id, new_remark, dropped_id))
        assert asyncio.run(host_manager.get_host(kept_id))["remark"] != new_remark
        assert asyncio.run(host_manager.get_host(dropped_id)) is not None

        asyncio.run(_reconnect())

        assert asyncio.run(host_manager.get_host(kept_id))["remark"] == new_remark
        assert asyncio.run(host_manager.get_host(dropped_id)) is None
        assert dropped_id not in asyncio.run(host_manager.get_hosts())
    finally:
        for host_id in host_ids:
            client.delete(f"/api/host/{host_id}", headers=headers)
        delete_core(access_token, core["id"])


def _create_hosts(access_token: str, inbound: str, *names: str) -> list[int]:
    host_ids = []
    for name in names:
        response = client.post(
            "/api/host",
            headers=auth_headers(access_token),
            json={
                "remark": unique_name(name),
                "address": ["127.0.0.1"],
                "port": 443,
                "inbound_tag": inbound,
                "priority": 1,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text
        host_ids.append(response.json()["id"])
    return host_ids


class _SnapshotKv(MemoryCasKv):
    async def put(self, key: str, value: bytes) -> int:
        self._rev += 1
        self._data[key] = (value, self._rev)
        return self._rev

    def remark(self, host_id: int) -> str | None:
        value, _ = self._data[HostManager.STATE_CACHE_KEY]
        return (json.loads(value).get(str(host_id)) or {}).get("remark")


def test_reconnect_does_not_overwrite_a_newer_kv_snapshot(access_token, fast_router, monkeypatch):
    # A starting worker loads the KV snapshot before the database: a stale one would be served everywhere
    core = create_core(access_token)
    (host_id,) = _create_hosts(access_token, get_inbounds(access_token)[0], "snapshot")
    worker = HostManager()
    worker._kv = _SnapshotKv()
    real_get_hosts = hosts_module.get_hosts
    reads = []

    async def _get_hosts(db):
        rows = await real_get_hosts(db)
        reads.append(1)
        if len(reads) > 1:
            return rows
        # This worker read the database just before an admin on another worker renamed the host;
        # that worker then wrote its snapshot to KV before this one finished
        stale = [BaseHost.model_validate(row) for row in rows]
        async with GetTestDB() as other_db:
            (await other_db.get(ProxyHost, host_id)).remark = "renamed elsewhere"
            await other_db.commit()
        other = HostManager()
        async with GetTestDB() as other_db:
            await other._add_hosts_local(other_db, [await other_db.get(ProxyHost, host_id)])
        other._kv = worker._kv
        await other._persist_state()
        return [h.model_copy(update={"remark": "before rename"}) if h.id == host_id else h for h in stale]

    monkeypatch.setattr("app.core.hosts.get_hosts", _get_hosts)
    router.register_resync_handler(MessageTopic.HOST, worker.resync_from_db)
    try:
        asyncio.run(_reconnect())

        # The newer snapshot is not replaced by the stale read; the database is read again instead
        assert worker._kv.remark(host_id) == "renamed elsewhere"
        assert asyncio.run(worker.get_host(host_id))["remark"] == "renamed elsewhere"
        assert len(reads) == 2
    finally:
        client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_reconnect_writes_the_kv_snapshot_when_nothing_changed_meanwhile(access_token, fast_router):
    core = create_core(access_token)
    (host_id,) = _create_hosts(access_token, get_inbounds(access_token)[0], "snapshot")
    worker = HostManager()
    worker._kv = _SnapshotKv()
    router.register_resync_handler(MessageTopic.HOST, worker.resync_from_db)
    try:
        asyncio.run(_reconnect())

        assert worker._kv.remark(host_id) == asyncio.run(worker.get_host(host_id))["remark"]
    finally:
        client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_reconnect_reloads_cores_from_the_database(access_token, fast_router, monkeypatch):
    core = create_core(access_token)
    added_tag = unique_name("added")
    try:
        # Another worker added an inbound to the core while this one was disconnected
        async def _add_inbound():
            async with GetTestDB() as db:
                row = await db.get(CoreConfig, core["id"])
                config = deepcopy(row.config)
                config["inbounds"].append({**deepcopy(XRAY_CONFIG["inbounds"][0]), "tag": added_tag})
                row.config = config
                await db.commit()

        asyncio.run(_add_inbound())
        assert added_tag not in asyncio.run(core_manager.get_inbounds())

        monkeypatch.setattr("app.core.manager.GetDB", GetTestDB)
        router.register_resync_handler(MessageTopic.CORE, core_manager.resync_from_db)
        asyncio.run(_reconnect())

        assert added_tag in asyncio.run(core_manager.get_inbounds())
    finally:
        delete_core(access_token, core["id"])


class _Attached:
    """node_manager without connections: which nodes this worker has attached."""

    def __init__(self, monkeypatch, manager_sync, node_ids):
        self.nodes = dict.fromkeys(node_ids)
        self.removed, self.updated, self.connected = [], [], []
        monkeypatch.setattr(manager_sync.node_manager, "get_nodes", self._get_nodes)
        monkeypatch.setattr(manager_sync.node_manager, "remove_node", self._remove)
        monkeypatch.setattr(manager_sync.node_manager, "update_node", self._update)
        monkeypatch.setattr(manager_sync, "handle_node_message", self._handle)

    async def _get_nodes(self):
        return dict(self.nodes)

    async def _remove(self, node_id, *, remote_stop=True):
        self.removed.append((node_id, remote_stop))
        self.nodes.pop(node_id, None)

    async def _update(self, db_node):
        self.updated.append((db_node.id, db_node.status))

    async def _handle(self, data):
        self.connected.append((data["action"], data["node_id"]))


async def _add_nodes(*statuses: NodeStatus) -> list[int]:
    async with GetTestDB() as db:
        nodes = [
            Node(
                name=unique_name("resync_node"),
                address="127.0.0.1",
                port=8080,
                api_port=62051,
                server_ca="ca",
                api_key="key",
                core_config_id=None,
                status=node_status,
            )
            for node_status in statuses
        ]
        db.add_all(nodes)
        await db.commit()
        return [node.id for node in nodes]


async def _set_node_status(node_id: int, node_status: NodeStatus):
    async with GetTestDB() as db:
        (await db.get(Node, node_id)).status = node_status
        await db.commit()


async def _drop_nodes(node_ids: list[int]):
    async with GetTestDB() as db:
        for node_id in node_ids:
            if node := await db.get(Node, node_id):
                await db.delete(node)
        await db.commit()


async def test_reconnect_reattaches_nodes_to_match_the_database(monkeypatch, fast_router):
    from app.node import manager_sync

    kept, disabled_elsewhere, added_elsewhere = await _add_nodes(
        NodeStatus.connected, NodeStatus.disabled, NodeStatus.connecting
    )
    ids = [kept, disabled_elsewhere, added_elsewhere]
    attached = _Attached(monkeypatch, manager_sync, [kept, disabled_elsewhere])
    monkeypatch.setattr(manager_sync, "GetDB", GetTestDB)
    manager_sync.register_node_sync_handler()
    try:
        await _reconnect()
    finally:
        await _drop_nodes(ids)

    assert [r for r in attached.removed if r[0] in ids] == [(disabled_elsewhere, False)]
    assert [u for u in attached.updated if u[0] in ids] == [(kept, NodeStatus.connected)]
    assert [c for c in attached.connected if c[1] in ids] == [("connect", added_elsewhere)]


async def test_node_changed_on_this_worker_during_the_resync_is_left_alone(monkeypatch, fast_router):
    from app.node import manager_sync

    enabled_here, disabled_here = await _add_nodes(NodeStatus.disabled, NodeStatus.connected)
    ids = [enabled_here, disabled_here]
    attached = _Attached(monkeypatch, manager_sync, [disabled_here])
    real_get_nodes = manager_sync.get_nodes

    async def _get_nodes(**kwargs):
        result = await real_get_nodes(**kwargs)
        # Right after the list is read, an admin on this worker enables one node and disables the other
        await _set_node_status(enabled_here, NodeStatus.connecting)
        attached.nodes[enabled_here] = None
        await _set_node_status(disabled_here, NodeStatus.disabled)
        return result

    monkeypatch.setattr(manager_sync, "GetDB", GetTestDB)
    monkeypatch.setattr(manager_sync, "get_nodes", _get_nodes)
    manager_sync.register_node_sync_handler()
    try:
        await _reconnect()
    finally:
        await _drop_nodes(ids)

    # The node just attached here is not dropped as missing from the older list
    assert enabled_here in attached.nodes
    assert not [r for r in attached.removed if r[0] in ids]
    # The node just disabled is not rebuilt from the older list (its "disconnect" message drops it)
    assert not [u for u in attached.updated if u[0] in ids]
    assert not [c for c in attached.connected if c[1] in ids]


async def test_one_failing_node_does_not_stop_the_rest(monkeypatch, fast_router):
    from app.node import manager_sync

    (added,) = await _add_nodes(NodeStatus.connected)
    attached = _Attached(monkeypatch, manager_sync, [-1, -2])

    async def _remove(node_id, *, remote_stop=True):
        attached.removed.append((node_id, remote_stop))
        if node_id == -1:
            raise RuntimeError("node is gone")

    monkeypatch.setattr(manager_sync.node_manager, "remove_node", _remove)
    monkeypatch.setattr(manager_sync, "GetDB", GetTestDB)
    manager_sync.register_node_sync_handler()
    try:
        await manager_sync.resync_nodes()
    finally:
        await _drop_nodes([added])

    assert sorted(r[0] for r in attached.removed if r[0] < 0) == [-2, -1]
    assert ("connect", added) in attached.connected


async def test_reconnect_refreshes_settings_and_client_templates(monkeypatch, fast_router):
    from app import app_factory

    calls = []

    async def _settings(data):
        calls.append(("settings", data))

    async def _templates(data):
        calls.append(("templates", data))

    monkeypatch.setattr(app_factory, "handle_settings_message", _settings)
    monkeypatch.setattr(app_factory, "handle_client_template_message", _templates)
    monkeypatch.setattr(app_factory, "on_startup", lambda fn: fn)
    monkeypatch.setattr(app_factory, "on_shutdown", lambda fn: fn)
    app_factory._register_nats_handlers(True, True, True)

    await _reconnect()

    assert calls == [("settings", {}), ("templates", {})]
    assert set(router._resync_handlers) == {MessageTopic.SETTING, MessageTopic.CLIENT_TEMPLATE}

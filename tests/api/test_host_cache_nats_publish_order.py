import asyncio

import pytest
from fastapi import status

from app.core.hosts import HostManager, host_manager
from app.models.admin import AdminDetails, AdminRoleData
from app.models.host import BulkHostSelection
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.nats.router import router
from app.operation import OperatorType
from app.operation.host import HostOperation
from tests.api import GetTestDB, client
from tests.api.helpers import auth_headers, create_core, delete_core, get_inbounds, unique_name

OWNER = AdminDetails(id=None, username="owner", role=AdminRoleData(id=1, name="owner", is_owner=True))


def _create_host(access_token: str, inbound: str, address: str) -> int:
    response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": unique_name("publish_order"),
            "address": [address],
            "port": 443,
            "inbound_tag": inbound,
            "priority": 1,
            "is_disabled": True,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()["id"]


def _db_host(access_token: str, host_id: int) -> dict | None:
    response = client.get(f"/api/host/{host_id}", headers=auth_headers(access_token))
    if response.status_code == status.HTTP_404_NOT_FOUND:
        return None
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def _edit_address(access_token: str, host_id: int, address: str) -> None:
    payload = _db_host(access_token, host_id)
    payload["address"] = [address]
    response = client.put(f"/api/host/{host_id}", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_200_OK, response.text


@pytest.mark.parametrize("change", ["edit", "delete"])
def test_an_older_refresh_is_not_published_after_a_newer_change_of_the_same_host(access_token, monkeypatch, change):
    core = create_core(access_token, name=unique_name("publish_order_core"))
    inbound = get_inbounds(access_token)[0]
    changed = _create_host(access_token, inbound, "old.example.com")
    other = _create_host(access_token, inbound, "other.example.com")
    host_ids = [changed, other]
    published: list[dict] = []

    async def capture(topic, data):
        published.append(data)

    monkeypatch.setattr(router, "publish", capture)
    monkeypatch.setattr(host_manager, "_add_hosts_impl", host_manager._add_hosts_nats)
    monkeypatch.setattr(host_manager, "_remove_host_impl", host_manager._remove_host_nats)

    async def scenario():
        paused = asyncio.Event()
        resume = asyncio.Event()
        armed = [True]
        real = host_manager._prepare_host_entry

        async def gated(*args, **kwargs):
            if armed[0]:
                armed[0] = False
                paused.set()
                await resume.wait()
            return await real(*args, **kwargs)

        monkeypatch.setattr(host_manager, "_prepare_host_entry", gated)

        async def bulk_enable():
            async with GetTestDB() as db:
                await HostOperation(operator_type=OperatorType.API).bulk_set_hosts_disabled(
                    db, BulkHostSelection(ids=host_ids), OWNER, is_disabled=False
                )

        bulk = asyncio.create_task(bulk_enable())
        await asyncio.wait_for(paused.wait(), 10)
        if change == "edit":
            _edit_address(access_token, changed, "new.example.com")
        else:
            response = client.delete(f"/api/host/{changed}", headers=auth_headers(access_token))
            assert response.status_code == status.HTTP_204_NO_CONTENT, response.text
        resume.set()
        await asyncio.wait_for(bulk, 10)

        other_worker = HostManager()
        for message in published:
            await other_worker._handle_host_message(message)
        return other_worker

    try:
        other_worker = asyncio.run(scenario())
        monkeypatch.undo()
        stored = _db_host(access_token, changed)
        remote = other_worker._hosts.get(changed)
        if change == "edit":
            assert stored["address"] == ["new.example.com"]
            assert remote is not None and remote.address == ["new.example.com"], (remote, published)
        else:
            assert stored is None
            assert remote is None, (remote, published)
        assert other in other_worker._hosts
    finally:
        monkeypatch.undo()
        for host_id in host_ids:
            client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def _entry(address: str) -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="order",
        inbound_tag="order",
        protocol="vless",
        network="tcp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(),
        address=[address],
    )


def test_a_removal_is_published_after_an_older_refresh_that_is_still_publishing(monkeypatch):
    host_id = 876543

    async def scenario():
        manager = HostManager()
        other_worker = HostManager()
        published: list[dict] = []
        publishing = asyncio.Event()
        release = asyncio.Event()

        async def slow_first_add(topic, data):
            if data.get("action") == "add" and not publishing.is_set():
                publishing.set()
                await release.wait()
            published.append(data)

        async def prepared(db, hosts, stamp):
            return [(host_id, _entry("old.example"))], [], manager._next_stamp()

        monkeypatch.setattr(router, "publish", slow_first_add)
        monkeypatch.setattr(manager, "_prepare_hosts", prepared)

        refresh = asyncio.create_task(manager._add_hosts_nats(None, []))
        await asyncio.wait_for(publishing.wait(), 10)
        removal = asyncio.create_task(manager._remove_host_nats(host_id))
        for _ in range(50):
            await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(asyncio.gather(refresh, removal), 10)

        for message in published:
            await other_worker._handle_host_message(message)
        return manager._hosts.get(host_id), other_worker._hosts.get(host_id), [m["action"] for m in published]

    local, remote, actions = asyncio.run(scenario())
    assert local is None
    assert remote is None, actions

"""xHTTP download hosts: a parent host must keep working when its download host is removed, disabled or deleted."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import status

from app.core import hosts as hosts_module
from app.core.hosts import host_manager
from app.db.crud.host import get_hosts
from app.subscription import config_cache
from tests.api import GetTestDB, client
from tests.api.helpers import auth_headers, create_group, create_user, delete_group, delete_user, unique_name


def _xhttp_inbound(tag: str, port: int, path: str) -> dict:
    return {
        "tag": tag,
        "protocol": "vless",
        "port": port,
        "settings": {"clients": [], "decryption": "none"},
        "streamSettings": {"network": "xhttp", "xhttpSettings": {"path": path, "mode": "auto"}},
    }


def _core_body(name: str, inbounds: list[dict]) -> dict:
    return {
        "config": {"inbounds": inbounds, "outbounds": [{"tag": "direct", "protocol": "freedom"}]},
        "name": name,
        "type": "xray",
        "exclude_inbound_tags": [],
        "fallbacks_inbound_tags": [],
    }


def _download_addresses(subscription_url: str) -> list[str]:
    """Return the downloadSettings address of every xHTTP outbound in the user's Xray subscription."""
    config_cache.clear_sub_config_cache()
    response = client.get(f"{subscription_url}/xray")
    assert response.status_code == status.HTTP_200_OK, response.text
    addresses = []
    for config in response.json():
        for outbound in config.get("outbounds", []):
            xhttp = (outbound.get("streamSettings") or {}).get("xhttpSettings") or {}
            if download := (xhttp.get("extra") or {}).get("downloadSettings"):
                addresses.append(download.get("address"))
    return addresses


async def _full_host_refresh() -> None:
    async with GetTestDB() as db:
        await host_manager.add_hosts(db, await get_hosts(db=db))


async def _host_manager_setup() -> None:
    # Startup path without NATS KV state: HostManager.setup rebuilds every host from the database. NATS stays off
    # for the call: with it, setup would load a KV snapshot instead, and connect from this short-lived loop, leaving
    # the shared manager a client whose loop is gone (every later host change in the session then waits on it).
    nats_enabled = host_manager._nats_enabled
    host_manager._nats_enabled = False
    try:
        async with GetTestDB() as db:
            await host_manager.setup(db)
    finally:
        host_manager._nats_enabled = nats_enabled


@pytest.fixture
def download_pair(access_token):
    """A core with two xHTTP inbounds, a download host on the second and a parent host on the first."""
    headers = auth_headers(access_token)
    up_inbound = _xhttp_inbound(unique_name("xhttp-up"), 18601, "/up")
    down_inbound = _xhttp_inbound(unique_name("xhttp-down"), 18602, "/down")
    core_name = unique_name("core")
    response = client.post("/api/core", headers=headers, json=_core_body(core_name, [up_inbound, down_inbound]))
    assert response.status_code == status.HTTP_201_CREATED, response.text
    core_id = response.json()["id"]
    group = create_group(access_token, inbound_tags=[up_inbound["tag"], down_inbound["tag"]])
    user = create_user(access_token, group_ids=[group["id"]])

    response = client.post(
        "/api/host",
        headers=headers,
        json={
            "remark": unique_name("download"),
            "address": ["download.example.com"],
            "inbound_tag": down_inbound["tag"],
            "priority": 1,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    download_host = response.json()
    response = client.post(
        "/api/host",
        headers=headers,
        json={
            "remark": unique_name("parent"),
            "address": ["parent.example.com"],
            "inbound_tag": up_inbound["tag"],
            "priority": 1,
            "transport_settings": {"xhttp_settings": {"download_settings": download_host["id"]}},
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    parent_host = response.json()

    pair = SimpleNamespace(
        headers=headers,
        core_id=core_id,
        core_name=core_name,
        up_inbound=up_inbound,
        down_inbound=down_inbound,
        user=user,
        download=download_host,
        parent=parent_host,
    )
    assert _download_addresses(user["subscription_url"]) == ["download.example.com"]
    try:
        yield pair
    finally:
        # The parent goes first: a download host cannot be deleted while a host still uses it
        for host_id in (parent_host["id"], download_host["id"]):
            client.delete(f"/api/host/{host_id}", headers=headers)
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        client.delete(f"/api/core/{core_id}", headers=headers)


def test_core_edit_removing_download_host_inbound_keeps_hosts_working(download_pair):
    pair = download_pair
    response = client.put(
        f"/api/core/{pair.core_id}?restart_nodes=false",
        headers=pair.headers,
        json=_core_body(pair.core_name, [pair.up_inbound]),
    )
    assert response.status_code == status.HTTP_200_OK, response.text

    # Neither a full refresh nor the startup rebuild may raise for the parent of a download host without an inbound
    asyncio.run(_full_host_refresh())
    asyncio.run(_host_manager_setup())

    assert pair.download["id"] not in host_manager._hosts
    assert pair.parent["id"] in host_manager._hosts
    # The parent is still served, without the download host
    assert _download_addresses(pair.user["subscription_url"]) == []


def test_full_refresh_skips_a_host_that_cannot_be_prepared(download_pair, monkeypatch):
    pair = download_pair
    prepare = hosts_module._prepare_subscription_inbound_data

    async def broken_parent(host, down_settings=None, **kwargs):
        if host.id == pair.parent["id"]:
            raise ValueError("broken stored settings")
        return await prepare(host, down_settings, **kwargs)

    monkeypatch.setattr(hosts_module, "_prepare_subscription_inbound_data", broken_parent)
    asyncio.run(_full_host_refresh())
    asyncio.run(_host_manager_setup())

    assert pair.parent["id"] not in host_manager._hosts
    assert pair.download["id"] in host_manager._hosts


def test_delete_download_host_in_use_is_refused(download_pair):
    pair = download_pair
    response = client.delete(f"/api/host/{pair.download['id']}", headers=pair.headers)
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert pair.parent["remark"] in response.json()["detail"]

    response = client.post("/api/hosts/bulk/delete", headers=pair.headers, json={"ids": [pair.download["id"]]})
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert pair.parent["remark"] in response.json()["detail"]

    # Nothing changed: the host still exists and the parent still uses it
    response = client.get(f"/api/host/{pair.download['id']}", headers=pair.headers)
    assert response.status_code == status.HTTP_200_OK
    assert _download_addresses(pair.user["subscription_url"]) == ["download.example.com"]


def test_delete_download_host_together_with_its_parent(download_pair):
    pair = download_pair
    response = client.post(
        "/api/hosts/bulk/delete",
        headers=pair.headers,
        json={"ids": [pair.download["id"], pair.parent["id"]]},
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()["count"] == 2


def test_delete_download_host_after_parent_stops_using_it(download_pair):
    pair = download_pair
    parent = {key: value for key, value in pair.parent.items() if key != "id"}
    parent["transport_settings"]["xhttp_settings"]["download_settings"] = None
    response = client.put(f"/api/host/{pair.parent['id']}", headers=pair.headers, json=parent)
    assert response.status_code == status.HTTP_200_OK, response.text

    response = client.delete(f"/api/host/{pair.download['id']}", headers=pair.headers)
    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text
    assert _download_addresses(pair.user["subscription_url"]) == []


def test_bulk_disable_download_host_drops_it_from_parent(download_pair):
    pair = download_pair
    response = client.post("/api/hosts/bulk/disable", headers=pair.headers, json={"ids": [pair.download["id"]]})
    assert response.status_code == status.HTTP_200_OK, response.text
    assert _download_addresses(pair.user["subscription_url"]) == []

    response = client.post("/api/hosts/bulk/enable", headers=pair.headers, json={"ids": [pair.download["id"]]})
    assert response.status_code == status.HTTP_200_OK, response.text
    assert _download_addresses(pair.user["subscription_url"]) == ["download.example.com"]


def test_disable_download_host_by_edit_drops_it_from_parent(download_pair):
    pair = download_pair
    download = {key: value for key, value in pair.download.items() if key != "id"}
    download["is_disabled"] = True
    response = client.put(f"/api/host/{pair.download['id']}", headers=pair.headers, json=download)
    assert response.status_code == status.HTTP_200_OK, response.text
    assert _download_addresses(pair.user["subscription_url"]) == []

    # A full rebuild must not bring the disabled download host back
    asyncio.run(_full_host_refresh())
    assert _download_addresses(pair.user["subscription_url"]) == []


def test_unusable_download_host_does_not_fall_back_to_inbound_download_settings(download_pair):
    pair = download_pair
    # The parent's inbound has its own downloadSettings, which hosts without a download host inherit
    up_inbound = deepcopy(pair.up_inbound)
    up_inbound["streamSettings"]["xhttpSettings"]["extra"] = {
        "downloadSettings": {"address": "inbound-default.example.com", "port": 443, "network": "xhttp"}
    }
    response = client.put(
        f"/api/core/{pair.core_id}?restart_nodes=false",
        headers=pair.headers,
        json=_core_body(pair.core_name, [up_inbound, pair.down_inbound]),
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    asyncio.run(_full_host_refresh())
    assert _download_addresses(pair.user["subscription_url"]) == ["download.example.com"]

    # The parent chose a download host: while that host is disabled the parent is served without one
    response = client.post("/api/hosts/bulk/disable", headers=pair.headers, json={"ids": [pair.download["id"]]})
    assert response.status_code == status.HTTP_200_OK, response.text
    assert _download_addresses(pair.user["subscription_url"]) == []
    asyncio.run(_full_host_refresh())
    asyncio.run(_host_manager_setup())
    assert _download_addresses(pair.user["subscription_url"]) == []

    # A parent without a download host still inherits the inbound's downloadSettings
    parent = {key: value for key, value in pair.parent.items() if key != "id"}
    parent["transport_settings"]["xhttp_settings"]["download_settings"] = None
    response = client.put(f"/api/host/{pair.parent['id']}", headers=pair.headers, json=parent)
    assert response.status_code == status.HTTP_200_OK, response.text
    assert _download_addresses(pair.user["subscription_url"]) == ["inbound-default.example.com"]


class _FakeKV:
    def __init__(self, entries: dict[str, bytes]):
        self.entries = entries

    async def get(self, key: str):
        value = self.entries.get(key)
        return SimpleNamespace(value=value) if value is not None else None


def test_host_snapshot_written_before_the_download_host_checks_is_not_loaded():
    # "state_v3" snapshots can embed a disabled download host, so setup() must rebuild the hosts from the database
    manager = hosts_module.HostManager()
    manager._kv = _FakeKV({"state_v3": b"{}"})
    assert asyncio.run(manager._load_state_from_cache()) is False

    manager._kv = _FakeKV({hosts_module.HostManager.STATE_CACHE_KEY: b"{}"})
    assert asyncio.run(manager._load_state_from_cache()) is True

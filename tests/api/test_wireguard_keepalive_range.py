import asyncio

import pytest
from pydantic import ValidationError

from app.core.hosts import host_manager
from app.db.models import ProxyHost
from app.models.host import BaseHost
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.wireguard import WireGuardConfiguration
from tests.api import GetTestDB, client
from tests.api.helpers import auth_headers, create_core, delete_core, get_inbounds, unique_name

WIREGUARD_MAX_KEEPALIVE = 65535


def _post_host(access_token, keepalive_seconds):
    response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": unique_name("wg_keepalive"),
            "address": ["wg.example.com"],
            "port": 51820,
            "inbound_tag": get_inbounds(access_token)[0],
            "priority": 1,
            "wireguard_overrides": {"keepalive_seconds": keepalive_seconds},
        },
    )
    if response.status_code == 201:
        client.delete(f"/api/host/{response.json()['id']}", headers=auth_headers(access_token))
    return response


def test_host_api_refuses_a_keepalive_wireguard_cannot_take(access_token):
    core = create_core(access_token, name=unique_name("wg_keepalive_core"))
    try:
        for keepalive_seconds, expected in (
            (65536, 422),
            (86400, 422),
            ("86400", 422),
            (86400.0, 422),
            (65535, 201),
            (25, 201),
            (0, 201),
        ):
            response = _post_host(access_token, keepalive_seconds)
            assert response.status_code == expected, (keepalive_seconds, response.text)
    finally:
        delete_core(access_token, core["id"])


def _persistent_keepalive_lines(keepalive) -> list[str]:
    inbound = SubscriptionInboundData(
        remark="wg",
        inbound_tag="wg-in",
        protocol="wireguard",
        address="wg.example.com",
        port=51820,
        network="udp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(path="", host=[]),
        mux_settings=None,
        wireguard_public_key="cHViLWtleS1wdWIta2V5LXB1Yi1rZXktcHViLWtleTA=",
        wireguard_allowed_ips=["0.0.0.0/0"],
        wireguard_keepalive=keepalive,
    )
    conf = WireGuardConfiguration()
    conf.add("wg", inbound.address, inbound, {"private_key": "cHJpdi1rZXk=", "peer_ips": ["10.0.0.2/32"]})
    rendered = "\n".join(content for _, content in conf.configs)
    return [line for line in rendered.splitlines() if line.startswith("PersistentKeepalive")]


def test_the_wireguard_file_never_carries_a_keepalive_outside_what_wg_accepts():
    for keepalive, expected in (
        (86400, ["PersistentKeepalive = 65535"]),
        (65536, ["PersistentKeepalive = 65535"]),
        (65535, ["PersistentKeepalive = 65535"]),
        (25, ["PersistentKeepalive = 25"]),
        (1, ["PersistentKeepalive = 1"]),
        (0, []),
        (-5, []),
        (None, []),
    ):
        assert _persistent_keepalive_lines(keepalive) == expected, keepalive


def _validate_stored_keepalive(keepalive):
    return BaseHost.model_validate(
        {
            "remark": "wg",
            "address": ["wg.example.com"],
            "port": 51820,
            "inbound_tag": "wg-in",
            "priority": 1,
            "wireguard_overrides": {"keepalive_seconds": keepalive},
        }
    )


@pytest.mark.parametrize("stored", [86400, 65536, "86400", " 86400 ", "+86400", "86_400", 86400.0, "86400.0"])
def test_a_stored_keepalive_above_the_maximum_loads_clamped_whatever_its_json_type(stored):
    assert _validate_stored_keepalive(stored).wireguard_overrides.keepalive_seconds == WIREGUARD_MAX_KEEPALIVE


@pytest.mark.parametrize("stored", [25, "25", 25.0, 65535, "65535"])
def test_a_stored_keepalive_within_the_maximum_loads_unchanged(stored):
    assert _validate_stored_keepalive(stored).wireguard_overrides.keepalive_seconds == int(stored)


@pytest.mark.parametrize("stored", ["soon", "1e5", 86400.5, "86400.5", -1, "-86400", [86400]])
def test_a_stored_keepalive_that_is_not_a_whole_number_is_still_rejected(stored):
    with pytest.raises(ValidationError):
        _validate_stored_keepalive(stored)


async def _store_keepalive_bypassing_the_api(host_id: int, keepalive_seconds) -> None:
    async with GetTestDB() as db:
        db_host = await db.get(ProxyHost, host_id)
        db_host.wireguard_overrides = {"keepalive_seconds": keepalive_seconds}
        await db.commit()


async def _load_hosts_from_the_database() -> None:
    async with GetTestDB() as db:
        await host_manager.setup_local(db)


@pytest.mark.parametrize("stored", [86400, "86400", 86400.0])
def test_a_host_stored_with_a_keepalive_above_the_wireguard_maximum_still_loads(access_token, stored):
    core = create_core(access_token, name=unique_name("wg_keepalive_core"))
    response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": unique_name("wg_keepalive_stored"),
            "address": ["wg.example.com"],
            "port": 51820,
            "inbound_tag": get_inbounds(access_token)[0],
            "priority": 1,
            "wireguard_overrides": {"keepalive_seconds": 25},
        },
    )
    assert response.status_code == 201, response.text
    host = response.json()
    try:
        asyncio.run(_store_keepalive_bypassing_the_api(host["id"], stored))

        asyncio.run(_load_hosts_from_the_database())
        assert host["id"] in host_manager._hosts

        loaded = client.get(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        assert loaded.status_code == 200, loaded.text
        assert loaded.json()["wireguard_overrides"]["keepalive_seconds"] == WIREGUARD_MAX_KEEPALIVE

        listed = client.get("/api/hosts", headers=auth_headers(access_token))
        assert listed.status_code == 200, listed.text

        modified = dict(host, wireguard_overrides={"keepalive_seconds": WIREGUARD_MAX_KEEPALIVE + 1})
        refused = client.put(f"/api/host/{host['id']}", headers=auth_headers(access_token), json=modified)
        assert refused.status_code == 422, refused.text
    finally:
        client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])

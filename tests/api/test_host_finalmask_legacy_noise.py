"""Noise items saved with the removed "rand" type must not break host loading."""

import asyncio

from fastapi import status
from sqlalchemy import update

from app.core.hosts import host_manager
from app.db.models import ProxyHost
from app.models.host import FinalMask
from tests.api import GetTestDB, client
from tests.api.helpers import auth_headers, create_core, delete_core, get_inbounds, unique_name

LEGACY_NOISE = [
    {"type": "rand", "packet": "", "rand": "10-20", "randRange": "0-255", "delay": "10-16"},
    {"type": "rand", "packet": "50-100", "delay": "5"},
]


def _noise(final_mask: dict) -> list[dict]:
    return final_mask["udp"][0]["settings"]["noise"]


def test_legacy_rand_noise_items_are_normalized():
    final_mask = FinalMask.model_validate({"udp": [{"type": "noise", "settings": {"noise": LEGACY_NOISE}}]})

    noise = _noise(final_mask.model_dump(exclude_none=True, by_alias=True, mode="json"))

    # Xray has no "rand" packet type: random bytes are an empty packet with a "rand" length
    assert noise == [
        {"rand": "10-20", "randRange": "0-255", "delay": "10-16"},
        {"rand": "50-100", "delay": "5"},
    ]


def test_legacy_rand_header_custom_items_are_normalized():
    final_mask = FinalMask.model_validate(
        {
            "udp": [
                {
                    "type": "header-custom",
                    "settings": {"client": [{"type": "rand", "packet": "16"}, {"type": "rand", "rand": 8}]},
                }
            ]
        }
    )

    settings = final_mask.model_dump(exclude_none=True, by_alias=True, mode="json")["udp"][0]["settings"]

    assert settings["client"] == [{"rand": 16}, {"rand": 8}]


async def _store_raw_final_mask(host_id: int, final_mask: dict) -> None:
    async with GetTestDB() as db:
        await db.execute(update(ProxyHost).where(ProxyHost.id == host_id).values(final_mask_settings=final_mask))
        await db.commit()


async def _host_manager_setup() -> None:
    # Startup rebuild from the database, without NATS KV state (see test_host_download_host.py)
    nats_enabled = host_manager._nats_enabled
    host_manager._nats_enabled = False
    try:
        async with GetTestDB() as db:
            await host_manager.setup(db)
    finally:
        host_manager._nats_enabled = nats_enabled


def test_host_saved_with_legacy_rand_noise_still_loads(access_token):
    core = create_core(access_token)
    headers = auth_headers(access_token)
    host_id = None
    try:
        inbound = get_inbounds(access_token)[0]
        response = client.post(
            "/api/host",
            headers=headers,
            json={
                "remark": unique_name("legacy_rand_noise"),
                "address": ["127.0.0.1"],
                "port": 443,
                "inbound_tag": inbound,
                "priority": 1,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text
        host_id = response.json()["id"]

        # A row saved before "rand" was removed from the noise types
        asyncio.run(_store_raw_final_mask(host_id, {"udp": [{"type": "noise", "settings": {"noise": LEGACY_NOISE}}]}))

        asyncio.run(_host_manager_setup())
        assert host_id in host_manager._hosts

        response = client.get(f"/api/host/{host_id}", headers=headers)
        assert response.status_code == status.HTTP_200_OK, response.text
        assert _noise(response.json()["final_mask_settings"])[0] == {
            "rand": "10-20",
            "randRange": "0-255",
            "delay": "10-16",
        }

        response = client.get("/api/hosts", headers=headers)
        assert response.status_code == status.HTTP_200_OK, response.text

        response = client.delete(f"/api/host/{host_id}", headers=headers)
        assert response.status_code == status.HTTP_204_NO_CONTENT, response.text
        host_id = None
    finally:
        if host_id is not None:
            client.delete(f"/api/host/{host_id}", headers=headers)
        delete_core(access_token, core["id"])

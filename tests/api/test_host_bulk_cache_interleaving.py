import asyncio

import pytest
from fastapi import status

from app.core.hosts import host_manager
from app.models.admin import AdminDetails, AdminRoleData
from app.models.host import BulkHostSelection
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
            "remark": unique_name("race_host"),
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


def _assert_cache_matches_db(access_token: str, host_ids: list[int]) -> None:
    for host_id in host_ids:
        stored = _db_host(access_token, host_id)
        cached = host_manager._hosts.get(host_id)
        if stored is None or stored["is_disabled"]:
            assert cached is None, (host_id, cached)
            continue
        assert cached is not None, host_id
        cached_address = cached.address if isinstance(cached.address, list) else [cached.address]
        assert set(cached_address) == set(stored["address"]), (host_id, cached_address, stored["address"])


@pytest.mark.parametrize("change", ["edit", "delete"])
@pytest.mark.parametrize("pause_at", ["add_hosts", "apply"])
def test_bulk_enable_paused_behind_a_single_host_change_leaves_the_cache_equal_to_the_db(
    access_token, monkeypatch, pause_at, change
):
    core = create_core(access_token, name=unique_name("race_core"))
    inbound = get_inbounds(access_token)[0]
    edited = _create_host(access_token, inbound, "old.example.com")
    other = _create_host(access_token, inbound, "other.example.com")
    host_ids = [edited, other]

    async def scenario():
        paused = asyncio.Event()
        resume = asyncio.Event()
        armed = [True]

        if pause_at == "add_hosts":
            real = host_manager.add_hosts

            async def gated(db, hosts):
                if armed[0]:
                    armed[0] = False
                    paused.set()
                    await resume.wait()
                await real(db, hosts)

            monkeypatch.setattr(host_manager, "add_hosts", gated)
        else:
            real = host_manager._add_prepared_hosts_local

            async def gated(*args, **kwargs):
                if armed[0]:
                    armed[0] = False
                    paused.set()
                    await resume.wait()
                await real(*args, **kwargs)

            monkeypatch.setattr(host_manager, "_add_prepared_hosts_local", gated)

        async def bulk_enable():
            async with GetTestDB() as db:
                await HostOperation(operator_type=OperatorType.API).bulk_set_hosts_disabled(
                    db, BulkHostSelection(ids=host_ids), OWNER, is_disabled=False
                )

        bulk = asyncio.create_task(bulk_enable())
        await asyncio.wait_for(paused.wait(), 10)
        if change == "edit":
            _edit_address(access_token, edited, "new.example.com")
        else:
            response = client.delete(f"/api/host/{edited}", headers=auth_headers(access_token))
            assert response.status_code == status.HTTP_204_NO_CONTENT, response.text
        resume.set()
        await asyncio.wait_for(bulk, 10)

    try:
        asyncio.run(scenario())
        monkeypatch.undo()
        if change == "edit":
            assert _db_host(access_token, edited)["address"] == ["new.example.com"]
        else:
            assert _db_host(access_token, edited) is None
        assert other in host_manager._hosts
        _assert_cache_matches_db(access_token, host_ids)
    finally:
        monkeypatch.undo()
        for host_id in host_ids:
            client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])

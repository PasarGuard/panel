import asyncio

from fastapi import status

from app.core.hosts import host_manager
from app.models.admin import AdminDetails, AdminRoleData
from app.models.host import CreateHost
from app.operation import OperatorType
from app.operation.host import HostOperation
from tests.api import GetTestDB, client
from tests.api.helpers import auth_headers, create_core, delete_core, get_inbound_details, unique_name

OWNER = AdminDetails(id=None, username="owner", role=AdminRoleData(id=1, name="owner", is_owner=True))


def _xhttp_inbound(access_token: str) -> str:
    for inbound in get_inbound_details(access_token):
        if inbound.get("network") in ("xhttp", "splithttp"):
            return inbound["tag"]
    raise AssertionError(get_inbound_details(access_token))


def _post_host(access_token: str, payload: dict) -> dict:
    response = client.post("/api/host", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def _get(access_token: str, host_id: int) -> dict:
    response = client.get(f"/api/host/{host_id}", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def test_parent_edit_paused_behind_download_host_edit_keeps_fresh_download_address(access_token, monkeypatch):
    core = create_core(access_token, name=unique_name("r2_core"))
    inbound = _xhttp_inbound(access_token)
    download = _post_host(
        access_token,
        {
            "remark": unique_name("r2_dl"),
            "address": ["d-old.example.com"],
            "port": 443,
            "inbound_tag": inbound,
            "priority": 1,
        },
    )
    parent = _post_host(
        access_token,
        {
            "remark": unique_name("r2_parent"),
            "address": ["parent.example.com"],
            "port": 443,
            "inbound_tag": inbound,
            "priority": 2,
            "transport_settings": {"xhttp_settings": {"download_settings": download["id"]}},
        },
    )
    host_ids = [parent["id"], download["id"]]

    async def scenario():
        paused = asyncio.Event()
        resume = asyncio.Event()
        armed = [True]
        real = host_manager.add_hosts

        async def gated(db, hosts):
            if armed[0]:
                armed[0] = False
                paused.set()
                await resume.wait()
            await real(db, hosts)

        monkeypatch.setattr(host_manager, "add_hosts", gated)

        payload = _get(access_token, parent["id"])
        payload["remark"] = unique_name("r2_parent_edit")
        payload.pop("id", None)

        async def edit_parent():
            async with GetTestDB() as db:
                await HostOperation(operator_type=OperatorType.API).modify_host(
                    db, parent["id"], CreateHost.model_validate(payload), OWNER
                )

        task = asyncio.create_task(edit_parent())
        await asyncio.wait_for(paused.wait(), 10)
        dl_payload = _get(access_token, download["id"])
        dl_payload["address"] = ["d-new.example.com"]
        response = client.put(f"/api/host/{download['id']}", headers=auth_headers(access_token), json=dl_payload)
        assert response.status_code == status.HTTP_200_OK, response.text
        cached_after_dl_edit = host_manager._hosts[parent["id"]].transport_config.download_settings
        assert cached_after_dl_edit is not None
        resume.set()
        await asyncio.wait_for(task, 10)

    try:
        asyncio.run(scenario())
        monkeypatch.undo()
        assert _get(access_token, download["id"])["address"] == ["d-new.example.com"]
        cached_parent = host_manager._hosts[parent["id"]]
        embedded = cached_parent.transport_config.download_settings
        embedded_address = embedded.address if not isinstance(embedded, dict) else embedded["address"]
        assert embedded_address == ["d-new.example.com"], embedded_address
    finally:
        monkeypatch.undo()
        for cleanup_id in host_ids:
            client.delete(f"/api/host/{cleanup_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])

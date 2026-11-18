import asyncio

from fastapi import status

import app.core.hosts as hosts_module
from app.core.hosts import host_manager
from app.core.manager import core_manager
from app.db.crud.host import get_hosts
from app.models.admin import AdminDetails, AdminRoleData
from app.models.host import BulkHostSelection
from app.operation import OperatorType
from app.operation.host import HostOperation
from tests.api import GetTestDB, client
from tests.api.helpers import auth_headers, create_core, delete_core, get_inbounds, unique_name

OWNER = AdminDetails(id=None, username="owner", role=AdminRoleData(id=1, name="owner", is_owner=True))


def test_bulk_enable_with_stale_inbounds_beats_a_later_applied_core_refresh(access_token, monkeypatch):
    core = create_core(access_token, name=unique_name("r2_inb_core"))
    inbound = get_inbounds(access_token)[0]
    response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": unique_name("r2_inb_host"),
            "address": ["x.example.com"],
            "port": 443,
            "inbound_tag": inbound,
            "priority": 1,
            "is_disabled": True,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    host_id = response.json()["id"]

    async def scenario():
        removed = [False]
        real_get_inbounds = core_manager.get_inbounds

        async def get_inbounds_after_core_edit():
            tags = await real_get_inbounds()
            return [tag for tag in tags if not (removed[0] and tag == inbound)]

        monkeypatch.setattr(core_manager, "get_inbounds", get_inbounds_after_core_edit)

        bulk_paused, bulk_resume = asyncio.Event(), asyncio.Event()
        bulk_armed = [True]
        real_upsert = hosts_module.upsert_inbounds

        async def gated_upsert(db, tags):
            if bulk_armed[0]:
                bulk_armed[0] = False
                bulk_paused.set()
                await bulk_resume.wait()
            return await real_upsert(db, tags)

        monkeypatch.setattr(hosts_module, "upsert_inbounds", gated_upsert)

        async def bulk_enable():
            async with GetTestDB() as db:
                await HostOperation(operator_type=OperatorType.API).bulk_set_hosts_disabled(
                    db, BulkHostSelection(ids=[host_id]), OWNER, is_disabled=False
                )

        bulk = asyncio.create_task(bulk_enable())
        await asyncio.wait_for(bulk_paused.wait(), 10)

        removed[0] = True
        refresh_paused, refresh_resume = asyncio.Event(), asyncio.Event()
        refresh_armed = [True]
        real_apply = host_manager._add_prepared_hosts_local

        async def gated_apply(*args, **kwargs):
            if refresh_armed[0]:
                refresh_armed[0] = False
                refresh_paused.set()
                await refresh_resume.wait()
            await real_apply(*args, **kwargs)

        monkeypatch.setattr(host_manager, "_add_prepared_hosts_local", gated_apply)

        async def core_refresh():
            async with GetTestDB() as db:
                await host_manager.add_hosts(db, await get_hosts(db=db))

        refresh = asyncio.create_task(core_refresh())
        await asyncio.wait_for(refresh_paused.wait(), 10)
        bulk_resume.set()
        await asyncio.wait_for(bulk, 10)
        refresh_resume.set()
        await asyncio.wait_for(refresh, 10)

    try:
        asyncio.run(scenario())
        served = asyncio.run(core_manager.get_inbounds())
        assert inbound not in served
        assert host_id not in host_manager._hosts, "host of an unserved inbound is still cached"
    finally:
        monkeypatch.undo()
        for cleanup_id in [host_id]:
            client.delete(f"/api/host/{cleanup_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import status
from sqlalchemy import func, select, update

from app.db.crud.node import create_node as db_create_node
from app.db.crud.node import remove_node as db_remove_node
from app.db.models import Admin, AdminUsageLogs, Node
from app.models.node import NodeCreate
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_core,
    create_group,
    create_hosts_for_inbounds,
    create_user,
    create_user_template,
    delete_admin,
    delete_core,
    delete_group,
    delete_user_template,
    unique_name,
)

VALID_CERTIFICATE = """-----BEGIN CERTIFICATE-----
MIIBvTCCAWOgAwIBAgIRAIY9Lzn0T3VFedUnT9idYkEwCgYIKoZIzj0EAwIwJjER
MA8GA1UEChMIWHJheSBJbmMxETAPBgNVBAMTCFhyYXkgSW5jMB4XDTIzMDUyMTA4
NDUxMVoXDTMzMDMyOTA5NDUxMVowJjERMA8GA1UEChMIWHJheSBJbmMxETAPBgNV
BAMTCFhyYXkgSW5jMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEGAmB8CILK7Q1
FG47g5VXg/oX3EFQqlW8B0aZAftYpHGLm4hEYVA4MasoGSxRuborhGu3lDvlt0cZ
aQTLvO/IK6NyMHAwDgYDVR0PAQH/BAQDAgWgMBMGA1UdJQQMMAoGCCsGAQUFBwMB
MAwGA1UdEwEB/wQCMAAwOwYDVR0RBDQwMoILZ3N0YXRpYy5jb22CDSouZ3N0YXRp
Yy5jb22CFCoubWV0cmljLmdzdGF0aWMuY29tMAoGCCqGSM49BAMCA0gAMEUCIQC1
XMIz1XwJrcu3BSZQFlNteutyepHrIttrtsfdd05YsQIgAtCg53wGUSSOYGL8921d
KuUcpBWSPkvH6y3Ak+YsTMg=
-----END CERTIFICATE-----"""


def node_create_payload(name: str, core_config_id: int) -> dict:
    return {
        "name": name,
        "address": "node.example.com",
        "port": 62050,
        "api_port": 62051,
        "usage_coefficient": 1.0,
        "server_ca": VALID_CERTIFICATE,
        "connection_type": "grpc",
        "keep_alive": 60,
        "core_config_id": core_config_id,
        "api_key": str(uuid4()),
        "data_limit": 0,
        "data_limit_reset_strategy": "no_reset",
        "reset_time": -1,
        "default_timeout": 10,
        "internal_timeout": 15,
    }


def create_db_node(*, core_config_id: int, name: str | None = None) -> int:
    async def _create():
        async with TestSession() as session:
            db_node = await db_create_node(
                session,
                NodeCreate(**node_create_payload(name or unique_name("bulk_node"), core_config_id)),
            )
            return db_node.id

    return asyncio.run(_create())


def delete_db_node(node_id: int) -> None:
    async def _delete():
        async with TestSession() as session:
            db_node = await session.get(Node, node_id)
            if db_node:
                await db_remove_node(session, db_node)

    asyncio.run(_delete())


def set_admin_used_traffic(username: str, used_traffic: int) -> None:
    async def _set():
        async with TestSession() as session:
            await session.execute(update(Admin).where(Admin.username == username).values(used_traffic=used_traffic))
            await session.commit()

    asyncio.run(_set())


def count_admin_usage_logs(admin_id: int) -> int:
    async def _count():
        async with TestSession() as session:
            result = await session.execute(
                select(func.count()).select_from(AdminUsageLogs).where(AdminUsageLogs.admin_id == admin_id)
            )
            return result.scalar_one()

    return asyncio.run(_count())


def get_admin_details(access_token: str, username: str) -> dict:
    response = client.get(
        "/api/admins",
        headers=auth_headers(access_token),
        params={"username": username},
    )
    assert response.status_code == status.HTTP_200_OK
    return next(admin for admin in response.json()["admins"] if admin["username"] == username)


def delete_host_if_present(access_token: str, host_id: int) -> None:
    response = client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
    assert response.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND)


def delete_user_if_present(access_token: str, username: str) -> None:
    response = client.delete(f"/api/user/{username}", headers=auth_headers(access_token))
    assert response.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND)


def valid_group_name(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:8]}"


def test_bulk_disable_and_enable_groups(access_token):
    core = create_core(access_token, name=unique_name("bulk_groups_core"))
    group_one = create_group(access_token, name=valid_group_name("bulkgroupone"))
    group_two = create_group(access_token, name=valid_group_name("bulkgrouptwo"))
    try:
        response = client.post(
            "/api/groups/bulk/disable",
            headers=auth_headers(access_token),
            json={"ids": [group_one["id"], group_two["id"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 2

        for group_id in (group_one["id"], group_two["id"]):
            group_response = client.get(f"/api/group/{group_id}", headers=auth_headers(access_token))
            assert group_response.status_code == status.HTTP_200_OK
            assert group_response.json()["is_disabled"] is True

        response = client.post(
            "/api/groups/bulk/enable",
            headers=auth_headers(access_token),
            json={"ids": [group_one["id"], group_two["id"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 2

        for group_id in (group_one["id"], group_two["id"]):
            group_response = client.get(f"/api/group/{group_id}", headers=auth_headers(access_token))
            assert group_response.status_code == status.HTTP_200_OK
            assert group_response.json()["is_disabled"] is False
    finally:
        delete_group(access_token, group_one["id"])
        delete_group(access_token, group_two["id"])
        delete_core(access_token, core["id"])


def test_bulk_disable_and_enable_hosts(access_token):
    core = create_core(access_token, name=unique_name("bulk_hosts_core"))
    hosts = create_hosts_for_inbounds(access_token)[:2]
    try:
        response = client.post(
            "/api/hosts/bulk/disable",
            headers=auth_headers(access_token),
            json={"ids": [host["id"] for host in hosts]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == len(hosts)

        for host in hosts:
            host_response = client.get(f"/api/host/{host['id']}", headers=auth_headers(access_token))
            assert host_response.status_code == status.HTTP_200_OK
            assert host_response.json()["is_disabled"] is True

        response = client.post(
            "/api/hosts/bulk/enable",
            headers=auth_headers(access_token),
            json={"ids": [host["id"] for host in hosts]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == len(hosts)

        for host in hosts:
            host_response = client.get(f"/api/host/{host['id']}", headers=auth_headers(access_token))
            assert host_response.status_code == status.HTTP_200_OK
            assert host_response.json()["is_disabled"] is False
    finally:
        for host in hosts:
            delete_host_if_present(access_token, host["id"])
        delete_core(access_token, core["id"])


def test_bulk_disable_and_enable_user_templates(access_token):
    core = create_core(access_token, name=unique_name("bulk_templates_core"))
    group = create_group(access_token, name=valid_group_name("bulktemplategroup"))
    template = create_user_template(
        access_token,
        name=unique_name("bulk_template"),
        group_ids=[group["id"]],
    )
    try:
        response = client.post(
            "/api/user_templates/bulk/disable",
            headers=auth_headers(access_token),
            json={"ids": [template["id"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1

        template_response = client.get(f"/api/user_template/{template['id']}", headers=auth_headers(access_token))
        assert template_response.status_code == status.HTTP_200_OK
        assert template_response.json()["is_disabled"] is True

        response = client.post(
            "/api/user_templates/bulk/enable",
            headers=auth_headers(access_token),
            json={"ids": [template["id"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1

        template_response = client.get(f"/api/user_template/{template['id']}", headers=auth_headers(access_token))
        assert template_response.status_code == status.HTTP_200_OK
        assert template_response.json()["is_disabled"] is False
    finally:
        delete_user_template(access_token, template["id"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_bulk_disable_enable_reset_update_and_reconnect_nodes(access_token, monkeypatch):
    from app.routers import node as node_router

    update_node_impl = AsyncMock()
    connect_single_impl = AsyncMock()
    disconnect_single_impl = AsyncMock()
    connect_bulk_impl = AsyncMock()
    update_node_api_impl = AsyncMock(return_value={"detail": "ok"})

    monkeypatch.setattr(node_router.node_operator, "_update_node_impl", update_node_impl)
    monkeypatch.setattr(node_router.node_operator, "_connect_single_impl", connect_single_impl)
    monkeypatch.setattr(node_router.node_operator, "_disconnect_single_impl", disconnect_single_impl)
    monkeypatch.setattr(node_router.node_operator, "_connect_bulk_impl", connect_bulk_impl)
    monkeypatch.setattr(node_router.node_operator, "_update_node_api_impl", update_node_api_impl)

    core = create_core(access_token, name=unique_name("bulk_nodes_core"))
    node_id = create_db_node(core_config_id=core["id"], name=unique_name("bulk_node"))
    try:
        response = client.post(
            "/api/nodes/bulk/disable",
            headers=auth_headers(access_token),
            json={"ids": [node_id]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        node_response = client.get(f"/api/node/{node_id}", headers=auth_headers(access_token))
        assert node_response.status_code == status.HTTP_200_OK
        assert node_response.json()["status"] == "disabled"
        assert disconnect_single_impl.await_count == 1

        response = client.post(
            "/api/nodes/bulk/enable",
            headers=auth_headers(access_token),
            json={"ids": [node_id]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        node_response = client.get(f"/api/node/{node_id}", headers=auth_headers(access_token))
        assert node_response.status_code == status.HTTP_200_OK
        assert node_response.json()["status"] == "connecting"
        assert update_node_impl.await_count >= 1
        assert connect_single_impl.await_count == 1

        async def _seed_usage():
            async with TestSession() as session:
                db_node = await session.get(Node, node_id)
                db_node.uplink = 2048
                db_node.downlink = 4096
                await session.commit()

        asyncio.run(_seed_usage())

        response = client.post(
            "/api/nodes/bulk/reset",
            headers=auth_headers(access_token),
            json={"ids": [node_id]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        node_response = client.get(f"/api/node/{node_id}", headers=auth_headers(access_token))
        assert node_response.status_code == status.HTTP_200_OK
        assert node_response.json()["uplink"] == 0
        assert node_response.json()["downlink"] == 0

        response = client.post(
            "/api/nodes/bulk/update",
            headers=auth_headers(access_token),
            json={"ids": [node_id]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        assert update_node_api_impl.await_count == 1

        response = client.post(
            "/api/nodes/bulk/reconnect",
            headers=auth_headers(access_token),
            json={"ids": [node_id]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        assert connect_bulk_impl.await_count == 1
    finally:
        delete_db_node(node_id)
        delete_core(access_token, core["id"])


def test_bulk_disable_enable_and_reset_admins(access_token):
    admin = create_admin(access_token, is_sudo=False)
    try:
        set_admin_used_traffic(admin["username"], 8192)

        response = client.post(
            "/api/admins/bulk/reset",
            headers=auth_headers(access_token),
            json={"usernames": [admin["username"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        assert get_admin_details(access_token, admin["username"])["used_traffic"] == 0
        assert count_admin_usage_logs(admin["id"]) == 1

        response = client.post(
            "/api/admins/bulk/disable",
            headers=auth_headers(access_token),
            json={"usernames": [admin["username"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        assert get_admin_details(access_token, admin["username"])["is_disabled"] is True

        response = client.post(
            "/api/admins/bulk/enable",
            headers=auth_headers(access_token),
            json={"usernames": [admin["username"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        assert get_admin_details(access_token, admin["username"])["is_disabled"] is False
    finally:
        delete_admin(access_token, admin["username"])


def test_bulk_admin_user_actions(access_token):
    admin = create_admin(access_token, is_sudo=False)
    active_user = create_user(access_token, payload={"username": unique_name("bulk_admin_active")})
    disabled_user = create_user(access_token, payload={"username": unique_name("bulk_admin_disabled")})

    try:
        for user in (active_user, disabled_user):
            response = client.put(
                f"/api/user/{user['username']}/set_owner",
                headers=auth_headers(access_token),
                params={"admin_username": admin["username"]},
            )
            assert response.status_code == status.HTTP_200_OK

        response = client.put(
            f"/api/user/{disabled_user['username']}",
            headers=auth_headers(access_token),
            json={"status": "disabled"},
        )
        assert response.status_code == status.HTTP_200_OK

        response = client.post(
            "/api/admins/bulk/users/disable",
            headers=auth_headers(access_token),
            json={"usernames": [admin["username"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1

        active_user_response = client.get(f"/api/user/{active_user['username']}", headers=auth_headers(access_token))
        disabled_user_response = client.get(
            f"/api/user/{disabled_user['username']}",
            headers=auth_headers(access_token),
        )
        assert active_user_response.status_code == status.HTTP_200_OK
        assert disabled_user_response.status_code == status.HTTP_200_OK
        assert active_user_response.json()["status"] == "disabled"
        assert disabled_user_response.json()["status"] == "disabled"

        response = client.post(
            "/api/admins/bulk/users/activate",
            headers=auth_headers(access_token),
            json={"usernames": [admin["username"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1

        active_user_response = client.get(f"/api/user/{active_user['username']}", headers=auth_headers(access_token))
        disabled_user_response = client.get(
            f"/api/user/{disabled_user['username']}",
            headers=auth_headers(access_token),
        )
        assert active_user_response.status_code == status.HTTP_200_OK
        assert disabled_user_response.status_code == status.HTTP_200_OK
        assert active_user_response.json()["status"] == "active"
        assert disabled_user_response.json()["status"] == "active"

        response = client.request(
            "DELETE",
            "/api/admins/bulk/users",
            headers=auth_headers(access_token),
            json={"usernames": [admin["username"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1

        for username in (active_user["username"], disabled_user["username"]):
            lookup = client.get(f"/api/user/{username}", headers=auth_headers(access_token))
            assert lookup.status_code == status.HTTP_404_NOT_FOUND
    finally:
        delete_user_if_present(access_token, active_user["username"])
        delete_user_if_present(access_token, disabled_user["username"])
        delete_admin(access_token, admin["username"])

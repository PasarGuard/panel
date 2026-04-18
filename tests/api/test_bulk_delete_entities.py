import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import status
from sqlalchemy import func, select, update

from app.db.crud.node import create_node as db_create_node
from app.db.crud.node import remove_node as db_remove_node
from app.db.models import (
    Admin,
    AdminUsageLogs,
    NextPlan,
    Node,
    NodeStat,
    NodeUsage,
    NodeUsageResetLogs,
    NodeUserUsage,
    User,
    inbounds_groups_association,
    template_group_association,
    users_groups_association,
)
from app.models.node import NodeCreate
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_client_template,
    create_core,
    create_group,
    create_user,
    create_user_template,
    delete_admin,
    delete_user,
    delete_user_template,
    get_inbounds,
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


def set_admin_sudo(username: str, is_sudo: bool) -> None:
    async def _set_flag():
        async with TestSession() as session:
            await session.execute(update(Admin).where(Admin.username == username).values(is_sudo=is_sudo))
            await session.commit()

    asyncio.run(_set_flag())


def seed_admin_usage_log(admin_id: int, used_traffic: int = 1024) -> None:
    async def _seed():
        async with TestSession() as session:
            session.add(AdminUsageLogs(admin_id=admin_id, used_traffic_at_reset=used_traffic))
            await session.commit()

    asyncio.run(_seed())


def get_user_admin_id(username: str) -> int | None:
    async def _get():
        async with TestSession() as session:
            result = await session.execute(select(User.admin_id).where(User.username == username))
            return result.scalar_one()

    return asyncio.run(_get())


def delete_admin_if_present(access_token: str, username: str) -> None:
    response = client.delete(f"/api/admin/{username}", headers=auth_headers(access_token))
    assert response.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


def delete_core_if_present(access_token: str, core_id: int) -> None:
    response = client.delete(f"/api/core/{core_id}", headers=auth_headers(access_token))
    assert response.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


def delete_group_if_present(access_token: str, group_id: int) -> None:
    response = client.delete(f"/api/group/{group_id}", headers=auth_headers(access_token))
    assert response.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND)


def delete_user_template_if_present(access_token: str, template_id: int) -> None:
    response = client.delete(f"/api/user_template/{template_id}", headers=auth_headers(access_token))
    assert response.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND)


def count_admin_usage_logs(admin_id: int) -> int:
    async def _count():
        async with TestSession() as session:
            result = await session.execute(
                select(func.count()).select_from(AdminUsageLogs).where(AdminUsageLogs.admin_id == admin_id)
            )
            return result.scalar_one()

    return asyncio.run(_count())


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


def get_node_core_config_id(node_id: int) -> int | None:
    async def _get():
        async with TestSession() as session:
            result = await session.execute(select(Node.core_config_id).where(Node.id == node_id))
            return result.scalar_one_or_none()

    return asyncio.run(_get())


def seed_node_usage_rows(node_id: int, user_id: int) -> None:
    async def _seed():
        async with TestSession() as session:
            now = datetime.now(timezone.utc)
            session.add_all(
                [
                    NodeUserUsage(user_id=user_id, node_id=node_id, created_at=now, used_traffic=1),
                    NodeUsage(node_id=node_id, created_at=now + timedelta(minutes=1), uplink=2, downlink=3),
                    NodeUsageResetLogs(node_id=node_id, uplink=4, downlink=5),
                    NodeStat(
                        node_id=node_id,
                        mem_total=4096,
                        mem_used=1024,
                        cpu_cores=4,
                        cpu_usage=50,
                        incoming_bandwidth_speed=100,
                        outgoing_bandwidth_speed=200,
                    ),
                ]
            )
            await session.commit()

    asyncio.run(_seed())


def get_node_related_counts(node_id: int) -> dict[str, int]:
    async def _counts():
        async with TestSession() as session:
            return {
                "nodes": (
                    await session.execute(select(func.count()).select_from(Node).where(Node.id == node_id))
                ).scalar_one(),
                "user_usages": (
                    await session.execute(
                        select(func.count()).select_from(NodeUserUsage).where(NodeUserUsage.node_id == node_id)
                    )
                ).scalar_one(),
                "usages": (
                    await session.execute(
                        select(func.count()).select_from(NodeUsage).where(NodeUsage.node_id == node_id)
                    )
                ).scalar_one(),
                "usage_logs": (
                    await session.execute(
                        select(func.count())
                        .select_from(NodeUsageResetLogs)
                        .where(NodeUsageResetLogs.node_id == node_id)
                    )
                ).scalar_one(),
                "stats": (
                    await session.execute(select(func.count()).select_from(NodeStat).where(NodeStat.node_id == node_id))
                ).scalar_one(),
            }

    return asyncio.run(_counts())


def get_group_association_counts(group_id: int) -> dict[str, int]:
    async def _counts():
        async with TestSession() as session:
            return {
                "users": (
                    await session.execute(
                        select(func.count())
                        .select_from(users_groups_association)
                        .where(users_groups_association.c.groups_id == group_id)
                    )
                ).scalar_one(),
                "templates": (
                    await session.execute(
                        select(func.count())
                        .select_from(template_group_association)
                        .where(template_group_association.c.group_id == group_id)
                    )
                ).scalar_one(),
                "inbounds": (
                    await session.execute(
                        select(func.count())
                        .select_from(inbounds_groups_association)
                        .where(inbounds_groups_association.c.group_id == group_id)
                    )
                ).scalar_one(),
            }

    return asyncio.run(_counts())


def create_next_plan(user_id: int, user_template_id: int) -> None:
    async def _create():
        async with TestSession() as session:
            session.add(
                NextPlan(
                    user_id=user_id,
                    user_template_id=user_template_id,
                    data_limit=2048,
                    expire=3600,
                    add_remaining_traffic=False,
                )
            )
            await session.commit()

    asyncio.run(_create())


def get_next_plan_state(user_id: int) -> dict | None:
    async def _get():
        async with TestSession() as session:
            result = await session.execute(
                select(NextPlan.id, NextPlan.user_template_id).where(NextPlan.user_id == user_id)
            )
            row = result.one_or_none()
            return None if row is None else {"exists": True, "user_template_id": row.user_template_id}

    return asyncio.run(_get())


def get_template_group_link_count(template_id: int) -> int:
    async def _count():
        async with TestSession() as session:
            result = await session.execute(
                select(func.count())
                .select_from(template_group_association)
                .where(template_group_association.c.user_template_id == template_id)
            )
            return result.scalar_one()

    return asyncio.run(_count())


def test_bulk_delete_admins_clears_owned_users_and_usage_logs(access_token):
    admin = create_admin(access_token, is_sudo=False)
    user = create_user(access_token, payload={"username": unique_name("bulk_admin_user")})
    try:
        owner_response = client.put(
            f"/api/user/{user['username']}/set_owner",
            headers=auth_headers(access_token),
            params={"admin_username": admin["username"]},
        )
        assert owner_response.status_code == status.HTTP_200_OK

        seed_admin_usage_log(admin["id"])

        response = client.post(
            "/api/admins/bulk/delete",
            headers=auth_headers(access_token),
            json={"usernames": [admin["username"]]},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        assert get_user_admin_id(user["username"]) is None
        assert count_admin_usage_logs(admin["id"]) == 0
    finally:
        delete_user(access_token, user["username"])
        delete_admin_if_present(access_token, admin["username"])


def test_bulk_delete_admins_rejects_sudo_accounts(access_token):
    admin = create_admin(access_token, is_sudo=False)
    set_admin_sudo(admin["username"], True)
    try:
        response = client.post(
            "/api/admins/bulk/delete",
            headers=auth_headers(access_token),
            json={"usernames": [admin["username"]]},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        set_admin_sudo(admin["username"], False)
        delete_admin(access_token, admin["username"])


def test_bulk_delete_client_templates_reassigns_default(access_token):
    create_client_template(
        access_token,
        name=unique_name("bulk_client_system"),
        template_type="user_agent",
        content='{"list": ["agent-one"]}',
    )
    second = create_client_template(
        access_token,
        name=unique_name("bulk_client_default"),
        template_type="user_agent",
        content='{"list": ["agent-two"]}',
        is_default=True,
    )

    response = client.post(
        "/api/client_templates/bulk/delete",
        headers=auth_headers(access_token),
        json={"ids": [second["id"]]},
    )

    assert response.status_code == status.HTTP_200_OK
    templates_response = client.get(
        "/api/client_templates",
        headers=auth_headers(access_token),
        params={"template_type": "user_agent"},
    )
    assert templates_response.status_code == status.HTTP_200_OK
    remaining = templates_response.json()["templates"]
    assert second["id"] not in {template["id"] for template in remaining}
    assert len([template for template in remaining if template["is_default"]]) == 1


def test_bulk_delete_client_templates_rejects_system_template(access_token):
    templates_response = client.get("/api/client_templates", headers=auth_headers(access_token))
    assert templates_response.status_code == status.HTTP_200_OK
    system_template = next(
        (template for template in templates_response.json()["templates"] if template["is_system"]),
        None,
    )

    if system_template is None:
        system_template = create_client_template(
            access_token,
            name=unique_name("bulk_system_template"),
            template_type="grpc_user_agent",
            content='{"list": ["grpc-agent"]}',
        )

    response = client.post(
        "/api/client_templates/bulk/delete",
        headers=auth_headers(access_token),
        json={"ids": [system_template["id"]]},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_bulk_delete_cores_clears_node_core_references(access_token):
    seed_core = create_core(access_token, name=unique_name("bulk_core_seed"))
    target_core = create_core(access_token, name=unique_name("bulk_core"))
    node_id = create_db_node(core_config_id=target_core["id"], name=unique_name("bulk_core_node"))
    try:
        response = client.post(
            "/api/cores/bulk/delete",
            headers=auth_headers(access_token),
            json={"ids": [target_core["id"]]},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        assert get_node_core_config_id(node_id) is None
    finally:
        delete_db_node(node_id)
        delete_core_if_present(access_token, target_core["id"])
        delete_core_if_present(access_token, seed_core["id"])


def test_bulk_delete_cores_rejects_default_core(access_token):
    response = client.post(
        "/api/cores/bulk/delete",
        headers=auth_headers(access_token),
        json={"ids": [1]},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_bulk_delete_groups_removes_all_associations(access_token):
    core = create_core(access_token, name=unique_name("bulk_group_core"))
    group = create_group(access_token, name=unique_name("bulk_group"))
    user = create_user(
        access_token,
        payload={"username": unique_name("bulk_group_user")},
        group_ids=[group["id"]],
    )
    template = create_user_template(
        access_token,
        name=unique_name("bulk_group_template"),
        group_ids=[group["id"]],
    )
    try:
        response = client.post(
            "/api/groups/bulk/delete",
            headers=auth_headers(access_token),
            json={"ids": [group["id"]]},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1

        user_response = client.get(f"/api/user/{user['username']}", headers=auth_headers(access_token))
        assert user_response.status_code == status.HTTP_200_OK
        assert user_response.json()["group_ids"] == []
        assert get_group_association_counts(group["id"]) == {"users": 0, "templates": 0, "inbounds": 0}
    finally:
        delete_user(access_token, user["username"])
        delete_user_template(access_token, template["id"])
        delete_core_if_present(access_token, core["id"])


def test_bulk_delete_hosts_removes_selected_hosts(access_token):
    core = create_core(access_token, name=unique_name("bulk_host_core"))
    inbounds = get_inbounds(access_token)
    host_ids = []
    try:
        for index, inbound in enumerate(inbounds[:2], start=1):
            response = client.post(
                "/api/host",
                headers=auth_headers(access_token),
                json={
                    "remark": unique_name(f"bulk_host_{index}"),
                    "address": ["127.0.0.1"],
                    "port": 443,
                    "sni": [f"bulk-host-{index}.example.com"],
                    "inbound_tag": inbound,
                    "priority": index,
                },
            )
            assert response.status_code == status.HTTP_201_CREATED
            host_ids.append(response.json()["id"])

        response = client.post(
            "/api/hosts/bulk/delete",
            headers=auth_headers(access_token),
            json={"ids": host_ids},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == len(host_ids)
        assert set(response.json()["hosts"]) == {str(host_id) for host_id in host_ids}

        hosts_response = client.get("/api/hosts", headers=auth_headers(access_token))
        assert hosts_response.status_code == status.HTTP_200_OK
        assert not ({host["id"] for host in hosts_response.json()} & set(host_ids))
    finally:
        delete_core_if_present(access_token, core["id"])


def test_bulk_delete_nodes_removes_usage_tables(access_token, monkeypatch):
    from app.routers import node as node_router

    monkeypatch.setattr(node_router.node_operator, "_remove_node_impl", AsyncMock())

    user = create_user(access_token, payload={"username": unique_name("bulk_node_user")})
    node_id = create_db_node(core_config_id=1, name=unique_name("bulk_node"))
    seed_node_usage_rows(node_id, user["id"])
    try:
        response = client.post(
            "/api/nodes/bulk/delete",
            headers=auth_headers(access_token),
            json={"ids": [node_id]},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        assert get_node_related_counts(node_id) == {
            "nodes": 0,
            "user_usages": 0,
            "usages": 0,
            "usage_logs": 0,
            "stats": 0,
        }
    finally:
        delete_user(access_token, user["username"])


def test_bulk_delete_user_templates_removes_group_links_and_next_plan_refs(access_token):
    core = create_core(access_token, name=unique_name("bulk_template_core"))
    group = create_group(access_token, name=unique_name("bulk_template_group"))
    user = create_user(access_token, payload={"username": unique_name("bulk_template_user")})
    template = create_user_template(
        access_token,
        name=unique_name("bulk_template"),
        group_ids=[group["id"]],
    )
    create_next_plan(user["id"], template["id"])
    try:
        response = client.post(
            "/api/user_templates/bulk/delete",
            headers=auth_headers(access_token),
            json={"ids": [template["id"]]},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1
        assert get_template_group_link_count(template["id"]) == 0
        assert get_next_plan_state(user["id"]) == {"exists": True, "user_template_id": None}
    finally:
        delete_user(access_token, user["username"])
        delete_group_if_present(access_token, group["id"])
        delete_core_if_present(access_token, core["id"])

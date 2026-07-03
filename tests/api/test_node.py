from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import status
from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import selectinload

from app.db.crud.core import create_core_config, remove_core_config
from app.db.crud.node import create_node as db_create_node, remove_node as db_remove_node
from app.db.models import (
    Admin,
    AdminRole,
    AdminStatus,
    CoreConfig,
    DataLimitResetStrategy,
    Group,
    Node,
    NodeConnectionType,
    NodeStat,
    NodeStatus,
    NodeUsage,
    NodeUsageResetLogs,
    NodeUserUsage,
    ProxyInbound,
    User,
    UserStatus,
    users_groups_association,
)
from app.models.core import CoreCreate
from app.models.admin import AdminDetails, AdminRoleData
from app.models.node import NodeCreate, NodeModify, NodeResponse, NodeSettings, NodesResponse
from app.models.stats import (
    NodeRealtimeStats,
    NodeStats,
    NodeStatsList,
    UserCountMetric,
    UserCountMetricStat,
    UserCountMetricStatsList,
    NodeUsageStat,
    NodeUsageStatsList,
    Period,
)
from app.operation import OperatorType
from app.operation.node import NodeOperation
from app.node import user as node_user_module
from app.node.sync import _blocked_admin_ids_for_users
from app.models.proxy import ProxyTable
from tests.api import TestSession, client, engine
from tests.api.helpers import auth_headers, unique_name
from tests.api.sample_data import XRAY_CONFIG

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


def sample_node_response(**overrides) -> NodeResponse:
    base_api_key = "123e4567-e89b-12d3-a456-426614174000"
    data = {
        "id": 1,
        "name": "test-node",
        "address": "node.example.com",
        "port": 62050,
        "api_port": 62051,
        "usage_coefficient": 1.0,
        "connection_type": NodeConnectionType.grpc,
        "server_ca": VALID_CERTIFICATE,
        "keep_alive": 60,
        "core_config_id": 1,
        "api_key": base_api_key,
        "data_limit": 0,
        "data_limit_reset_strategy": DataLimitResetStrategy.no_reset,
        "reset_time": -1,
        "default_timeout": 10,
        "internal_timeout": 15,
        "xray_version": "1.7.5",
        "node_version": "1.7.5",
        "status": NodeStatus.connected,
        "message": None,
        "uplink": 0,
        "downlink": 0,
        "lifetime_uplink": 0,
        "lifetime_downlink": 0,
        "proxy_url": "socks5://127.0.0.1:1080",
    }
    data.update(overrides)
    return NodeResponse(**data)


@pytest.mark.asyncio
async def test_sync_users_blocked_admin_lookup_is_batched():
    blocking_username = unique_name("syba")
    disabled_username = unique_name("sydba")
    nonblocking_username = unique_name("synba")
    disabled_nonblocking_username = unique_name("syndba")
    active_username = unique_name("syaa")
    nonblocking_role_name = unique_name("sync_nonblocking_role")
    disabled_nonblocking_role_name = unique_name("sync_disabled_nonblocking_role")
    user_prefix = unique_name("sync_user")

    async with TestSession() as session:
        nonblocking_role = AdminRole(
            name=nonblocking_role_name,
            is_owner=False,
            permissions={},
            limits={},
            features={},
            access={},
            disconnect_users_when_limited=False,
        )
        disabled_nonblocking_role = AdminRole(
            name=disabled_nonblocking_role_name,
            is_owner=False,
            permissions={},
            limits={},
            features={},
            access={},
            disconnect_users_when_disabled=False,
        )
        blocking_admin = Admin(
            username=blocking_username,
            hashed_password="secret",
            role_id=3,
            status=AdminStatus.limited,
        )
        disabled_admin = Admin(
            username=disabled_username,
            hashed_password="secret",
            role_id=3,
            status=AdminStatus.disabled,
        )
        active_admin = Admin(
            username=active_username,
            hashed_password="secret",
            role_id=3,
            status=AdminStatus.active,
        )
        session.add_all([nonblocking_role, disabled_nonblocking_role, blocking_admin, disabled_admin, active_admin])
        await session.flush()

        nonblocking_admin = Admin(
            username=nonblocking_username,
            hashed_password="secret",
            role_id=nonblocking_role.id,
            status=AdminStatus.limited,
        )
        disabled_nonblocking_admin = Admin(
            username=disabled_nonblocking_username,
            hashed_password="secret",
            role_id=disabled_nonblocking_role.id,
            status=AdminStatus.disabled,
        )
        session.add_all([nonblocking_admin, disabled_nonblocking_admin])
        await session.flush()

        users = [
            User(username=f"{user_prefix}_blocked_a", admin_id=blocking_admin.id),
            User(username=f"{user_prefix}_blocked_b", admin_id=blocking_admin.id),
            User(username=f"{user_prefix}_disabled_blocked", admin_id=disabled_admin.id),
            User(username=f"{user_prefix}_nonblocking", admin_id=nonblocking_admin.id),
            User(username=f"{user_prefix}_disabled_nonblocking", admin_id=disabled_nonblocking_admin.id),
            User(username=f"{user_prefix}_active", admin_id=active_admin.id),
        ]
        session.add_all(users)
        await session.commit()

        user_ids = [user.id for user in users]
        blocking_admin_id = blocking_admin.id
        disabled_admin_id = disabled_admin.id
        nonblocking_admin_id = nonblocking_admin.id
        disabled_nonblocking_admin_id = disabled_nonblocking_admin.id
        active_admin_id = active_admin.id

    query_count = 0

    def count_admin_role_queries(_, __, statement, *args):
        nonlocal query_count
        if "admin_roles" in statement.lower():
            query_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_admin_role_queries)
    try:
        async with TestSession() as session:
            loaded_users = list((await session.execute(select(User).where(User.id.in_(user_ids)))).scalars().all())
            blocked_ids = await _blocked_admin_ids_for_users(loaded_users)

        assert blocked_ids == {blocking_admin_id, disabled_admin_id}
        assert nonblocking_admin_id not in blocked_ids
        assert disabled_nonblocking_admin_id not in blocked_ids
        assert active_admin_id not in blocked_ids
        assert query_count == 1
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_admin_role_queries)


@pytest.mark.asyncio
async def test_sync_users_blocked_admin_lookup_uses_preloaded_roles_without_fallback_query():
    blocking_username = unique_name("sylba")
    active_username = unique_name("sylaa")
    user_prefix = unique_name("sync_loaded_user")

    async with TestSession() as session:
        blocking_admin = Admin(
            username=blocking_username,
            hashed_password="secret",
            role_id=3,
            status=AdminStatus.limited,
        )
        active_admin = Admin(
            username=active_username,
            hashed_password="secret",
            role_id=3,
            status=AdminStatus.active,
        )
        session.add_all([blocking_admin, active_admin])
        await session.flush()

        users = [
            User(username=f"{user_prefix}_blocked", admin_id=blocking_admin.id),
            User(username=f"{user_prefix}_active", admin_id=active_admin.id),
        ]
        session.add_all(users)
        await session.commit()

        user_ids = [user.id for user in users]
        blocking_admin_id = blocking_admin.id

    async with TestSession() as session:
        loaded_users = list(
            (
                await session.execute(
                    select(User).options(selectinload(User.admin).selectinload(Admin.role)).where(User.id.in_(user_ids))
                )
            )
            .unique()
            .scalars()
            .all()
        )

        query_count = 0

        def count_admin_role_queries(_, __, statement, *args):
            nonlocal query_count
            if "admin_roles" in statement.lower():
                query_count += 1

        event.listen(engine.sync_engine, "before_cursor_execute", count_admin_role_queries)
        try:
            blocked_ids = await _blocked_admin_ids_for_users(loaded_users)

            assert blocked_ids == {blocking_admin_id}
            assert query_count == 0
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count_admin_role_queries)


@pytest.mark.asyncio
async def test_sync_users_blocked_admin_lookup_falls_back_when_admin_role_is_not_loaded():
    blocking_username = unique_name("sync_admin_no_role")
    user_prefix = unique_name("sync_user_no_role")

    async with TestSession() as session:
        blocking_admin = Admin(
            username=blocking_username,
            hashed_password="secret",
            role_id=3,
            status=AdminStatus.limited,
        )
        session.add(blocking_admin)
        await session.flush()

        user = User(username=f"{user_prefix}_blocked", admin_id=blocking_admin.id)
        session.add(user)
        await session.commit()

        user_id = user.id
        blocking_admin_id = blocking_admin.id

    async with TestSession() as session:
        loaded_users = list(
            (await session.execute(select(User).options(selectinload(User.admin)).where(User.id == user_id)))
            .unique()
            .scalars()
            .all()
        )

        assert "admin" in loaded_users[0].__dict__
        assert "role" not in loaded_users[0].admin.__dict__

        query_count = 0

        def count_admin_role_queries(_, __, statement, *args):
            nonlocal query_count
            if "admin_roles" in statement.lower():
                query_count += 1

        event.listen(engine.sync_engine, "before_cursor_execute", count_admin_role_queries)
        try:
            blocked_ids = await _blocked_admin_ids_for_users(loaded_users)

            assert blocked_ids == {blocking_admin_id}
            assert query_count == 1
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count_admin_role_queries)


@pytest.mark.asyncio
async def test_core_users_only_excludes_admins_with_blocking_sync_roles(monkeypatch):
    inbound_tag = unique_name("sync_inbound")
    group_name = unique_name("sync_group")
    user_prefix = unique_name("sync_core_user")

    monkeypatch.setattr(
        node_user_module,
        "_serialize_user_for_node",
        lambda id, user_settings, inbounds, allowed_protocols=None: {"id": id, "inbounds": inbounds},
    )

    async with TestSession() as session:
        blocking_role = AdminRole(
            name=unique_name("sync_blocking_role"),
            is_owner=False,
            permissions={},
            limits={},
            features={},
            access={},
            disconnect_users_when_limited=True,
        )
        nonblocking_role = AdminRole(
            name=unique_name("sync_nonblocking_role"),
            is_owner=False,
            permissions={},
            limits={},
            features={},
            access={},
            disconnect_users_when_limited=False,
        )
        session.add_all([blocking_role, nonblocking_role])
        await session.flush()

        active_admin = Admin(
            username=unique_name("sync_active_admin"),
            hashed_password="secret",
            role_id=blocking_role.id,
            status=AdminStatus.active,
        )
        blocking_admin = Admin(
            username=unique_name("sync_blocking_admin"),
            hashed_password="secret",
            role_id=blocking_role.id,
            status=AdminStatus.limited,
        )
        nonblocking_admin = Admin(
            username=unique_name("sync_nonblocking_admin"),
            hashed_password="secret",
            role_id=nonblocking_role.id,
            status=AdminStatus.limited,
        )
        session.add_all([active_admin, blocking_admin, nonblocking_admin])
        await session.flush()

        inbound = ProxyInbound(tag=inbound_tag)
        group = Group(name=group_name, inbounds=[inbound])
        session.add(group)
        await session.flush()

        active_user = User(
            username=f"{user_prefix}_active",
            admin_id=active_admin.id,
            proxy_settings=ProxyTable().dict(no_obj=True),
            status=UserStatus.active,
        )
        blocked_user = User(
            username=f"{user_prefix}_blocked",
            admin_id=blocking_admin.id,
            proxy_settings=ProxyTable().dict(no_obj=True),
            status=UserStatus.active,
        )
        nonblocked_user = User(
            username=f"{user_prefix}_nonblocked",
            admin_id=nonblocking_admin.id,
            proxy_settings=ProxyTable().dict(no_obj=True),
            status=UserStatus.active,
        )
        session.add_all([active_user, blocked_user, nonblocked_user])
        await session.flush()

        await session.execute(
            users_groups_association.insert(),
            [
                {"user_id": active_user.id, "groups_id": group.id},
                {"user_id": blocked_user.id, "groups_id": group.id},
                {"user_id": nonblocked_user.id, "groups_id": group.id},
            ],
        )
        await session.commit()

        expected_user_ids = {active_user.id, nonblocked_user.id}
        blocked_user_id = blocked_user.id

    async with TestSession() as session:
        users = await node_user_module.core_users(session, inbound_tags=[inbound_tag])

    synced_user_ids = {user["id"] for user in users}
    assert synced_user_ids == expected_user_ids
    assert blocked_user_id not in synced_user_ids
    assert all(user["inbounds"] == [inbound_tag] for user in users)


def node_create_payload(**overrides) -> dict:
    payload = {
        "name": "new-node",
        "address": "node.example.com",
        "port": 62050,
        "api_port": 62051,
        "usage_coefficient": 1.0,
        "server_ca": VALID_CERTIFICATE,
        "connection_type": "grpc",
        "keep_alive": 60,
        "core_config_id": 1,
        "api_key": str(uuid4()),
        "data_limit": 0,
        "data_limit_reset_strategy": DataLimitResetStrategy.no_reset.value,
        "reset_time": -1,
        "default_timeout": 10,
        "internal_timeout": 15,
        "proxy_url": "socks5://127.0.0.1:1080",
    }
    payload.update(overrides)
    return payload


def core_create_model(name: str) -> CoreCreate:
    return CoreCreate(
        name=name,
        config=XRAY_CONFIG,
        exclude_inbound_tags=set(),
        fallbacks_inbound_tags=set(),
    )


async def setup_nodes_simple(names: list[str]) -> tuple[int, list[int]]:
    async with TestSession() as session:
        core = await create_core_config(session, core_create_model(unique_name("core_nodes_simple")))
        core_id = inspect(core).identity[0]
        node_ids: list[int] = []
        for name in names:
            node_model = NodeCreate(**node_create_payload(name=name, core_config_id=core_id))
            db_node = await db_create_node(session, node_model)
            node_ids.append(inspect(db_node).identity[0])
        return core_id, node_ids


async def cleanup_nodes_simple(core_id: int, node_ids: list[int]) -> None:
    async with TestSession() as session:
        for node_id in node_ids:
            db_node = await session.get(Node, node_id)
            if db_node:
                await db_remove_node(session, db_node)
        db_core = await session.get(CoreConfig, core_id)
        if db_core:
            await remove_core_config(session, db_core)


async def test_update_node_status_preserves_version_when_not_provided():
    from app.db.crud.node import update_node_status

    async with TestSession() as session:
        core = await create_core_config(session, core_create_model(unique_name("core_preserve_version")))
        core_id = inspect(core).identity[0]
        node_model = NodeCreate(**node_create_payload(name=unique_name("node_preserve_version"), core_config_id=core_id))
        db_node = await db_create_node(session, node_model)
        node_id = inspect(db_node).identity[0]

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        await update_node_status(session, db_node, NodeStatus.connected, xray_version="26.6.1", node_version="0.5.2")

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        assert db_node.xray_version == "26.6.1"
        assert db_node.node_version == "0.5.2"

        # Transition to error WITHOUT passing xray_version/node_version (the real-world
        # call pattern from every error path in operation/node.py and jobs/node_checker.py) —
        # the last-known version must survive.
        await update_node_status(session, db_node, NodeStatus.error, message="Connection refused")

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        assert db_node.status == NodeStatus.error
        assert db_node.message == "Connection refused"
        assert db_node.xray_version == "26.6.1"
        assert db_node.node_version == "0.5.2"

    async with TestSession() as session:
        core = await session.get(CoreConfig, core_id)
        await cleanup_nodes_simple(core_id, [node_id])


async def test_bulk_update_node_status_preserves_version_when_empty():
    from app.db.crud.node import bulk_update_node_status, update_node_status

    async with TestSession() as session:
        core = await create_core_config(session, core_create_model(unique_name("core_bulk_preserve")))
        core_id = inspect(core).identity[0]
        node_a_model = NodeCreate(**node_create_payload(name=unique_name("node_bulk_a"), core_config_id=core_id))
        node_b_model = NodeCreate(**node_create_payload(name=unique_name("node_bulk_b"), core_config_id=core_id))
        node_c_model = NodeCreate(**node_create_payload(name=unique_name("node_bulk_c"), core_config_id=core_id))
        db_node_a = await db_create_node(session, node_a_model)
        db_node_b = await db_create_node(session, node_b_model)
        db_node_c = await db_create_node(session, node_c_model)
        node_a_id = inspect(db_node_a).identity[0]
        node_b_id = inspect(db_node_b).identity[0]
        node_c_id = inspect(db_node_c).identity[0]

    async with TestSession() as session:
        db_node_a = await session.get(Node, node_a_id)
        db_node_b = await session.get(Node, node_b_id)
        db_node_c = await session.get(Node, node_c_id)
        await update_node_status(session, db_node_a, NodeStatus.connected, xray_version="26.6.1", node_version="0.5.2")
        await update_node_status(session, db_node_b, NodeStatus.connected, xray_version="26.5.3", node_version="0.5.1")
        await update_node_status(session, db_node_c, NodeStatus.connected, xray_version="26.5.9", node_version="0.4.9")

    async with TestSession() as session:
        # node_a: real error transition with a fresh reported version (should overwrite).
        # node_b: error transition without a known version (should preserve "26.5.3").
        # node_c: mismatched columns - xray_version reported (overwrite), node_version empty (preserve).
        await bulk_update_node_status(
            session,
            [
                {
                    "node_id": node_a_id,
                    "status": NodeStatus.error,
                    "message": "boom",
                    "xray_version": "26.6.22",
                    "node_version": "0.5.3",
                },
                {
                    "node_id": node_b_id,
                    "status": NodeStatus.error,
                    "message": "boom",
                    "xray_version": "",
                    "node_version": "",
                },
                {
                    "node_id": node_c_id,
                    "status": NodeStatus.error,
                    "message": "boom",
                    "xray_version": "26.6.27",
                    "node_version": "",
                },
            ],
        )

    async with TestSession() as session:
        db_node_a = await session.get(Node, node_a_id)
        db_node_b = await session.get(Node, node_b_id)
        db_node_c = await session.get(Node, node_c_id)
        assert db_node_a.xray_version == "26.6.22"
        assert db_node_a.node_version == "0.5.3"
        assert db_node_b.xray_version == "26.5.3"
        assert db_node_b.node_version == "0.5.1"
        assert db_node_c.xray_version == "26.6.27"
        assert db_node_c.node_version == "0.4.9"

        await cleanup_nodes_simple(core_id, [node_a_id, node_b_id, node_c_id])


def _xhttp_core_config(tag: str) -> dict:
    return {
        "inbounds": [
            {
                "tag": tag,
                "listen": "0.0.0.0",
                "port": 8443,
                "protocol": "vless",
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {
                    "network": "xhttp",
                    "xhttpSettings": {
                        "path": "/",
                        "sessionPlacement": "header",
                        "sessionKey": "X-Request-ID",
                    },
                },
            }
        ],
        "outbounds": [{"tag": "DIRECT", "protocol": "freedom"}],
    }


async def test_update_node_status_does_not_rewrite_stored_session_keys():
    """update_node_status must never mutate the admin's stored core config — the sessionID*
    rename is applied on the fly per-node when pushing config (NodeOperation.connect_node),
    not persisted. Crossing the version threshold here should leave the stored config as-is."""
    from app.db.crud.node import update_node_status

    async with TestSession() as session:
        core = await create_core_config(
            session,
            CoreCreate(name=unique_name("core_no_migrate"), config=_xhttp_core_config("xhttp-no-migrate"), exclude_inbound_tags=set(), fallbacks_inbound_tags=set()),
        )
        core_id = inspect(core).identity[0]
        node_model = NodeCreate(**node_create_payload(name=unique_name("node_no_migrate"), core_config_id=core_id))
        db_node = await db_create_node(session, node_model)
        node_id = inspect(db_node).identity[0]

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        await update_node_status(session, db_node, NodeStatus.connected, xray_version="26.5.9", node_version="0.5.0")

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        # Crossing the sessionID-rename threshold must not touch the stored config.
        await update_node_status(session, db_node, NodeStatus.connected, xray_version="26.6.22", node_version="0.5.3")

    async with TestSession() as session:
        db_core = await session.get(CoreConfig, core_id)
        xhttp = db_core.config["inbounds"][0]["streamSettings"]["xhttpSettings"]
        assert xhttp["sessionPlacement"] == "header"
        assert xhttp["sessionKey"] == "X-Request-ID"
        assert "sessionIDPlacement" not in xhttp
        assert "sessionIDKey" not in xhttp

        await cleanup_nodes_simple(core_id, [node_id])


async def test_get_xray_version_by_core_id_ignores_status():
    from app.db.crud.node import get_xray_version_by_core_id, update_node_status

    async with TestSession() as session:
        core = await create_core_config(session, core_create_model(unique_name("core_version_lookup")))
        core_id = inspect(core).identity[0]
        node_model = NodeCreate(**node_create_payload(name=unique_name("node_version_lookup"), core_config_id=core_id))
        db_node = await db_create_node(session, node_model)
        node_id = inspect(db_node).identity[0]

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        await update_node_status(session, db_node, NodeStatus.connected, xray_version="26.6.1", node_version="0.5.2")

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        # Node errors out but keeps its last-known version.
        await update_node_status(session, db_node, NodeStatus.error, message="Connection refused")

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        assert db_node.status == NodeStatus.error

        version = await get_xray_version_by_core_id(session, core_id)
        assert version == "26.6.1"

        await cleanup_nodes_simple(core_id, [node_id])


async def test_get_xray_version_by_core_id_prefers_known_version_over_never_connected_sibling():
    from app.db.crud.node import get_xray_version_by_core_id, update_node_status

    async with TestSession() as session:
        core = await create_core_config(session, core_create_model(unique_name("core_version_sibling")))
        core_id = inspect(core).identity[0]
        node_a_model = NodeCreate(**node_create_payload(name=unique_name("node_a_never_connected"), core_config_id=core_id))
        node_b_model = NodeCreate(**node_create_payload(name=unique_name("node_b_known_version"), core_config_id=core_id))
        db_node_a = await db_create_node(session, node_a_model)
        db_node_b = await db_create_node(session, node_b_model)
        node_a_id = inspect(db_node_a).identity[0]
        node_b_id = inspect(db_node_b).identity[0]

    async with TestSession() as session:
        # node_a never gets a version set (simulates a freshly added, never-connected node).
        db_node_b = await session.get(Node, node_b_id)
        await update_node_status(session, db_node_b, NodeStatus.connected, xray_version="26.6.1", node_version="0.5.2")

    async with TestSession() as session:
        version = await get_xray_version_by_core_id(session, core_id)
        assert version == "26.6.1"

        await cleanup_nodes_simple(core_id, [node_a_id, node_b_id])


async def test_modify_node_status_toggle_preserves_version():
    from app.db.crud.node import modify_node, update_node_status

    async with TestSession() as session:
        core = await create_core_config(session, core_create_model(unique_name("core_modify_status_only")))
        core_id = inspect(core).identity[0]
        node_model = NodeCreate(**node_create_payload(name=unique_name("node_modify_status_only"), core_config_id=core_id))
        db_node = await db_create_node(session, node_model)
        node_id = inspect(db_node).identity[0]

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        await update_node_status(session, db_node, NodeStatus.connected, xray_version="26.6.1", node_version="0.5.2")

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        # Pure status toggle: disable the node without changing address/port/etc.
        await modify_node(session, db_node, NodeModify(status=NodeStatus.disabled))

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        assert db_node.status == NodeStatus.disabled
        assert db_node.xray_version == "26.6.1"
        assert db_node.node_version == "0.5.2"

        await cleanup_nodes_simple(core_id, [node_id])


async def test_modify_node_address_change_clears_version():
    from app.db.crud.node import modify_node, update_node_status

    async with TestSession() as session:
        core = await create_core_config(session, core_create_model(unique_name("core_modify_address_change")))
        core_id = inspect(core).identity[0]
        node_model = NodeCreate(**node_create_payload(name=unique_name("node_modify_address_change"), core_config_id=core_id))
        db_node = await db_create_node(session, node_model)
        node_id = inspect(db_node).identity[0]

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        await update_node_status(session, db_node, NodeStatus.connected, xray_version="26.6.1", node_version="0.5.2")

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        # Real identity change: pointing at a different address should reset the known version,
        # since the panel can no longer assume the same physical instance is on the other end.
        await modify_node(session, db_node, NodeModify(address="different-node.example.com"))

    async with TestSession() as session:
        db_node = await session.get(Node, node_id)
        assert db_node.address == "different-node.example.com"
        assert db_node.xray_version is None
        assert db_node.node_version is None

        await cleanup_nodes_simple(core_id, [node_id])


def usage_stats_payload() -> NodeUsageStatsList:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return NodeUsageStatsList(
        start=start,
        end=end,
        period=Period.day,
        stats={
            1: [
                NodeUsageStat(uplink=100, downlink=50, period_start=start),
                NodeUsageStat(uplink=200, downlink=75, period_start=start + timedelta(hours=1)),
            ]
        },
    )


def user_count_metric_stats_payload() -> UserCountMetricStatsList:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return UserCountMetricStatsList(
        metric=UserCountMetric.online,
        start=start,
        end=end,
        period=Period.day,
        stats={1: [UserCountMetricStat(count=3, period_start=start)]},
    )


def node_stats_payload() -> NodeStatsList:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    return NodeStatsList(
        start=start,
        end=end,
        period=Period.hour,
        stats=[
            NodeStats(
                period_start=start,
                mem_usage_percentage=25.5,
                cpu_usage_percentage=50.0,
                incoming_bandwidth_speed=1024.5,
                outgoing_bandwidth_speed=2048.25,
            ),
            NodeStats(
                period_start=start + timedelta(hours=1),
                mem_usage_percentage=30.5,
                cpu_usage_percentage=48.0,
                incoming_bandwidth_speed=2048.5,
                outgoing_bandwidth_speed=4096.25,
            ),
        ],
    )


def realtime_stats_payload() -> NodeRealtimeStats:
    return NodeRealtimeStats(
        mem_total=4096,
        mem_used=1024,
        cpu_cores=4,
        cpu_usage=23.5,
        incoming_bandwidth_speed=512,
        outgoing_bandwidth_speed=256,
        uptime=50,
    )


@pytest.fixture
def node_operator_mock(monkeypatch: pytest.MonkeyPatch):
    operator = MagicMock()
    async_methods = [
        "get_usage",
        "get_db_nodes",
        "restart_all_node",
        "create_node",
        "get_validated_node",
        "modify_node",
        "bulk_set_nodes_status",
        "bulk_reset_nodes_usage",
        "bulk_restart_nodes",
        "bulk_update_nodes",
        "reset_node_usage",
        "restart_node",
        "sync_node_users",
        "remove_node",
        "get_node_stats_periodic",
        "get_node_system_stats",
        "get_user_count_metric",
    ]
    for name in async_methods:
        setattr(operator, name, AsyncMock(name=name))
    monkeypatch.setattr("app.routers.node.node_operator", operator)
    return operator


def test_node_create_accepts_localhost_address():
    node = NodeCreate(**node_create_payload(address="localhost"))
    assert node.address == "localhost"
    assert NodeCreate(**node_create_payload(address="LOCALHOST")).address == "LOCALHOST"


def test_node_modify_accepts_localhost_address():
    assert NodeModify(address="localhost").address == "localhost"


def test_get_node_settings_returns_defaults(access_token):
    response = client.get("/api/node/settings", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == NodeSettings().model_dump()


def test_get_usage_passes_filters(access_token, node_operator_mock):
    usage = usage_stats_payload()
    node_operator_mock.get_usage.return_value = usage
    start = datetime(2024, 2, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    response = client.get(
        "/api/node/usage",
        headers=auth_headers(access_token),
        params={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "period": "day",
            "node_id": 5,
            "group_by_node": True,
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == usage.model_dump(mode="json")

    awaited_kwargs = node_operator_mock.get_usage.await_args.kwargs
    query = awaited_kwargs["query"]
    assert query.node_id == 5
    assert query.group_by_node is True
    assert query.period == Period.day
    assert query.start == start
    assert query.end == end


def test_get_user_count_metric_passes_filters(access_token, node_operator_mock):
    counts = user_count_metric_stats_payload()
    node_operator_mock.get_user_count_metric.return_value = counts
    start = datetime(2024, 2, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    response = client.get(
        "/api/node/user_counts/online",
        headers=auth_headers(access_token),
        params={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "period": "day",
            "node_id": 5,
            "group_by_node": True,
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == counts.model_dump(mode="json")

    awaited_kwargs = node_operator_mock.get_user_count_metric.await_args.kwargs
    assert awaited_kwargs["metric"] == UserCountMetric.online
    query = awaited_kwargs["query"]
    assert query.node_id == 5
    assert query.group_by_node is True
    assert query.period == Period.day
    assert query.start == start
    assert query.end == end


def test_get_user_count_metric_rejects_status_metric_node_scope(access_token, node_operator_mock):
    response = client.get(
        "/api/node/user_counts/limited",
        headers=auth_headers(access_token),
        params={"period": "day", "group_by_node": True},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Only online user counts" in response.json()["detail"]
    node_operator_mock.get_user_count_metric.assert_not_called()


def test_get_nodes_forwards_query_params(access_token, node_operator_mock):
    node_response = sample_node_response()
    nodes_response = NodesResponse(nodes=[node_response], total=1)
    node_operator_mock.get_db_nodes.return_value = nodes_response
    params = [
        ("core_id", "2"),
        ("offset", "5"),
        ("limit", "25"),
        ("enabled", "true"),
        ("search", "test"),
        ("ids", "1"),
        ("ids", "2"),
        ("status", "connected"),
        ("status", "error"),
    ]
    response = client.get("/api/nodes", headers=auth_headers(access_token), params=params)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == nodes_response.model_dump(mode="json")

    awaited_kwargs = node_operator_mock.get_db_nodes.await_args.kwargs
    query = awaited_kwargs["query"]
    assert query.core_id == 2
    assert query.offset == 5
    assert query.limit == 25
    assert query.enabled is True
    assert query.ids == [1, 2]
    assert query.search == "test"
    assert query.status == [NodeStatus.connected, NodeStatus.error]


def test_reconnect_all_nodes_triggers_restart(access_token, node_operator_mock):
    response = client.post(
        "/api/nodes/reconnect",
        headers=auth_headers(access_token),
        params={"core_id": 7},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {}
    awaited_kwargs = node_operator_mock.restart_all_node.await_args.kwargs
    assert awaited_kwargs["core_id"] == 7
    assert awaited_kwargs["db"] is not None
    assert awaited_kwargs["admin"] is not None


def test_create_node_returns_created_node(access_token, node_operator_mock):
    node_response = sample_node_response(id=10, name="created-node")
    node_operator_mock.create_node.return_value = node_response
    payload = node_create_payload()
    response = client.post("/api/node", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json() == node_response.model_dump()

    await_args = node_operator_mock.create_node.await_args.args
    expected_payload = {
        **payload,
        "connection_type": NodeConnectionType(payload["connection_type"]),
        "data_limit_reset_strategy": DataLimitResetStrategy(payload["data_limit_reset_strategy"]),
    }
    assert await_args[1].model_dump() == expected_payload
    UUID(await_args[1].api_key)


def test_get_single_node(access_token, node_operator_mock):
    node_response = sample_node_response(id=22, name="fetched-node")
    node_operator_mock.get_validated_node.return_value = node_response
    response = client.get("/api/node/22", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == node_response.model_dump()
    awaited_kwargs = node_operator_mock.get_validated_node.await_args.kwargs
    assert awaited_kwargs["node_id"] == 22


def test_modify_node_updates_fields(access_token, node_operator_mock):
    node_response = sample_node_response(name="updated-node")
    node_operator_mock.modify_node.return_value = node_response
    payload = {
        "name": "updated-node",
        "status": "disabled",
        "address": "new.example.com",
        "port": 43000,
        "api_port": 44000,
        "usage_coefficient": 0.8,
        "keep_alive": 30,
    }
    response = client.put("/api/node/3", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == node_response.model_dump()
    awaited_kwargs = node_operator_mock.modify_node.await_args.kwargs
    assert awaited_kwargs["node_id"] == 3
    assert awaited_kwargs["modified_node"].model_dump(exclude_none=True) == {
        **payload,
        "status": NodeStatus(payload["status"]),
    }


def test_reset_node_usage_returns_response(access_token, node_operator_mock):
    node_response = sample_node_response(uplink=100)
    node_operator_mock.reset_node_usage.return_value = node_response
    response = client.post("/api/node/4/reset", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == node_response.model_dump()
    awaited_kwargs = node_operator_mock.reset_node_usage.await_args.kwargs
    assert awaited_kwargs["node_id"] == 4


def test_reconnect_node(access_token, node_operator_mock):
    response = client.post("/api/node/9/reconnect", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {}
    await_args = node_operator_mock.restart_node.await_args.args
    assert await_args[1] == 9


def test_sync_node_users(access_token, node_operator_mock):
    node_operator_mock.sync_node_users.return_value = {"synced": True}
    response = client.put(
        "/api/node/11/sync",
        headers=auth_headers(access_token),
        params={"flush_users": True},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"synced": True}
    awaited_kwargs = node_operator_mock.sync_node_users.await_args.kwargs
    assert awaited_kwargs["node_id"] == 11
    assert awaited_kwargs["flush_users"] is True


def test_sync_node_users_flushes_by_default(access_token, node_operator_mock):
    node_operator_mock.sync_node_users.return_value = {"synced": True}
    response = client.put("/api/node/11/sync", headers=auth_headers(access_token))

    assert response.status_code == status.HTTP_200_OK
    awaited_kwargs = node_operator_mock.sync_node_users.await_args.kwargs
    assert awaited_kwargs["node_id"] == 11
    assert awaited_kwargs["flush_users"] is True


def test_remove_node(access_token, node_operator_mock):
    response = client.delete("/api/node/6", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_204_NO_CONTENT
    awaited_kwargs = node_operator_mock.remove_node.await_args.kwargs
    assert awaited_kwargs["node_id"] == 6


def test_bulk_disable_nodes(access_token, node_operator_mock):
    node_operator_mock.bulk_set_nodes_status.return_value = {"nodes": ["node-a", "node-b"], "count": 2}

    response = client.post(
        "/api/nodes/bulk/disable",
        headers=auth_headers(access_token),
        json={"ids": [1, 2]},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"nodes": ["node-a", "node-b"], "count": 2}
    await_args = node_operator_mock.bulk_set_nodes_status.await_args
    assert await_args.args[1].ids == [1, 2]
    assert await_args.kwargs["status"] == NodeStatus.disabled


def test_bulk_enable_nodes(access_token, node_operator_mock):
    node_operator_mock.bulk_set_nodes_status.return_value = {"nodes": ["node-a"], "count": 1}

    response = client.post(
        "/api/nodes/bulk/enable",
        headers=auth_headers(access_token),
        json={"ids": [3]},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"nodes": ["node-a"], "count": 1}
    await_args = node_operator_mock.bulk_set_nodes_status.await_args
    assert await_args.args[1].ids == [3]
    assert await_args.kwargs["status"] == NodeStatus.connected


def test_bulk_reset_nodes_usage(access_token, node_operator_mock):
    node_operator_mock.bulk_reset_nodes_usage.return_value = {"nodes": ["node-a"], "count": 1}

    response = client.post(
        "/api/nodes/bulk/reset",
        headers=auth_headers(access_token),
        json={"ids": [4]},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"nodes": ["node-a"], "count": 1}
    await_args = node_operator_mock.bulk_reset_nodes_usage.await_args
    assert await_args.args[1].ids == [4]


def test_bulk_reconnect_nodes(access_token, node_operator_mock):
    node_operator_mock.bulk_restart_nodes.return_value = {"nodes": ["node-a"], "count": 1}

    response = client.post(
        "/api/nodes/bulk/reconnect",
        headers=auth_headers(access_token),
        json={"ids": [5]},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"nodes": ["node-a"], "count": 1}
    await_args = node_operator_mock.bulk_restart_nodes.await_args
    assert await_args.args[1].ids == [5]


def test_bulk_update_nodes(access_token, node_operator_mock):
    node_operator_mock.bulk_update_nodes.return_value = {"nodes": ["node-a"], "count": 1}

    response = client.post(
        "/api/nodes/bulk/update",
        headers=auth_headers(access_token),
        json={"ids": [6]},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"nodes": ["node-a"], "count": 1}
    await_args = node_operator_mock.bulk_update_nodes.await_args
    assert await_args.args[1].ids == [6]


def test_get_node_stats(access_token, node_operator_mock):
    stats = node_stats_payload()
    node_operator_mock.get_node_stats_periodic.return_value = stats
    start = datetime(2024, 3, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    response = client.get(
        "/api/node/8/stats",
        headers=auth_headers(access_token),
        params={"start": start.isoformat(), "end": end.isoformat(), "period": "hour"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == stats.model_dump(mode="json")
    awaited_kwargs = node_operator_mock.get_node_stats_periodic.await_args.kwargs
    assert awaited_kwargs["node_id"] == 8
    query = awaited_kwargs["query"]
    assert query.start == start
    assert query.end == end
    assert query.period == Period.hour


def test_realtime_node_stats(access_token, node_operator_mock):
    realtime_stats = realtime_stats_payload()
    node_operator_mock.get_node_system_stats.return_value = realtime_stats
    response = client.get("/api/node/12/realtime_stats", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == realtime_stats.model_dump()
    awaited_kwargs = node_operator_mock.get_node_system_stats.await_args.kwargs
    assert awaited_kwargs["node_id"] == 12


@pytest.mark.asyncio
async def test_node_create_and_modify_schedule_background_reconnect(monkeypatch: pytest.MonkeyPatch):
    operator = NodeOperation(operator_type=OperatorType.API)
    scheduled_node_ids: list[int] = []

    async def record_background_connect(node_id: int) -> None:
        scheduled_node_ids.append(node_id)

    monkeypatch.setattr(operator, "_update_node_impl", AsyncMock())
    monkeypatch.setattr(operator, "_connect_single_node_background", record_background_connect)
    monkeypatch.setattr("app.operation.node.notification.create_node", AsyncMock())
    monkeypatch.setattr("app.operation.node.notification.modify_node", AsyncMock())

    admin = AdminDetails(username="admin", role=AdminRoleData(is_owner=True))
    async with TestSession() as session:
        core = await create_core_config(session, core_create_model(unique_name("core_node_background")))
        core_id = inspect(core).identity[0]
        node_id: int | None = None
        try:
            created = await operator.create_node(
                session,
                NodeCreate(**node_create_payload(name=unique_name("node_background"), core_config_id=core_id)),
                admin,
            )
            node_id = created.id
            await asyncio.sleep(0)

            modified = await operator.modify_node(
                session,
                created.id,
                NodeModify(name=unique_name("node_background_modified")),
                admin,
            )
            await asyncio.sleep(0)

            assert scheduled_node_ids == [created.id, modified.id]
        finally:
            if node_id is not None:
                db_node = await session.get(Node, node_id)
                if db_node:
                    await db_remove_node(session, db_node)
            db_core = await session.get(CoreConfig, core_id)
            if db_core:
                await remove_core_config(session, db_core)


# Tests for /api/nodes/simple endpoint


@pytest.mark.asyncio
async def test_get_nodes_simple_basic(access_token):
    """Test that nodes/simple returns correct minimal data structure."""
    names = [unique_name("node_simple_1"), unique_name("node_simple_2"), unique_name("node_simple_3")]
    core_id, node_ids = await setup_nodes_simple(names)
    try:
        response = client.get(
            "/api/nodes/simple",
            headers=auth_headers(access_token),
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "nodes" in data
        assert "total" in data

        for node in data["nodes"]:
            assert set(node.keys()) == {"id", "name", "status"}

        response_names = [n["name"] for n in data["nodes"]]
        for name in names:
            assert name in response_names
    finally:
        await cleanup_nodes_simple(core_id, node_ids)


@pytest.mark.asyncio
async def test_get_nodes_simple_search(access_token):
    """Test case-insensitive search by node name."""
    name_alpha = unique_name("node_alpha_search")
    name_beta = unique_name("node_beta_search")
    name_other = unique_name("node_other_search")
    names = [name_alpha, name_beta, name_other]
    core_id, node_ids = await setup_nodes_simple(names)
    try:
        response = client.get(
            "/api/nodes/simple",
            headers=auth_headers(access_token),
            params={"search": "alpha_search"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["nodes"]) >= 1
        assert any(n["name"] == name_alpha for n in data["nodes"])
    finally:
        await cleanup_nodes_simple(core_id, node_ids)


@pytest.mark.asyncio
async def test_get_nodes_simple_sort_ascending(access_token):
    """Test ascending sort by node name."""
    names = [
        unique_name("node_c_sort"),
        unique_name("node_a_sort"),
        unique_name("node_b_sort"),
    ]
    core_id, node_ids = await setup_nodes_simple(names)
    try:
        response = client.get(
            "/api/nodes/simple",
            headers=auth_headers(access_token),
            params={"sort": "name"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        our_nodes = [n for n in data["nodes"] if n["name"] in names]
        our_names = [n["name"] for n in our_nodes]
        assert our_names == sorted(names)
    finally:
        await cleanup_nodes_simple(core_id, node_ids)


@pytest.mark.asyncio
async def test_get_nodes_simple_sort_descending(access_token):
    """Test descending sort by node name."""
    names = [
        unique_name("node_a_desc"),
        unique_name("node_b_desc"),
        unique_name("node_c_desc"),
    ]
    core_id, node_ids = await setup_nodes_simple(names)
    try:
        response = client.get(
            "/api/nodes/simple",
            headers=auth_headers(access_token),
            params={"sort": "-name"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        our_nodes = [n for n in data["nodes"] if n["name"] in names]
        our_names = [n["name"] for n in our_nodes]
        assert our_names == sorted(names, reverse=True)
    finally:
        await cleanup_nodes_simple(core_id, node_ids)


@pytest.mark.asyncio
async def test_get_nodes_simple_pagination(access_token):
    """Test pagination with offset and limit."""
    names = [unique_name(f"node_pag_{i}") for i in range(5)]
    core_id, node_ids = await setup_nodes_simple(names)
    try:
        response1 = client.get(
            "/api/nodes/simple",
            headers=auth_headers(access_token),
            params={"offset": 0, "limit": 2},
        )
        response2 = client.get(
            "/api/nodes/simple",
            headers=auth_headers(access_token),
            params={"offset": 2, "limit": 2},
        )

        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
        data1 = response1.json()
        data2 = response2.json()
        assert len(data1["nodes"]) == 2
        assert len(data2["nodes"]) == 2

        ids1 = {n["id"] for n in data1["nodes"]}
        ids2 = {n["id"] for n in data2["nodes"]}
        assert len(ids1 & ids2) == 0
    finally:
        await cleanup_nodes_simple(core_id, node_ids)


@pytest.mark.asyncio
async def test_get_nodes_simple_skip_pagination(access_token):
    """Test all=true parameter returns all records."""
    names = [unique_name(f"node_all_{i}") for i in range(10)]
    core_id, node_ids = await setup_nodes_simple(names)
    try:
        response = client.get(
            "/api/nodes/simple",
            headers=auth_headers(access_token),
            params={"all": "true"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "nodes" in data
        assert "total" in data
        assert data["total"] >= 10
    finally:
        await cleanup_nodes_simple(core_id, node_ids)


@pytest.mark.asyncio
async def test_get_nodes_simple_empty_search(access_token):
    """Test search with no matching results."""
    names = [unique_name("known_node_search_1"), unique_name("known_node_search_2")]
    core_id, node_ids = await setup_nodes_simple(names)
    try:
        response = client.get(
            "/api/nodes/simple",
            headers=auth_headers(access_token),
            params={"search": "nonexistent_node_xyz_12345"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert len(data["nodes"]) == 0
    finally:
        await cleanup_nodes_simple(core_id, node_ids)


def test_get_nodes_simple_invalid_sort(access_token):
    """Test error handling for invalid sort parameter."""
    response = client.get(
        "/api/nodes/simple",
        headers=auth_headers(access_token),
        params={"sort": "invalid_field_xyz"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_get_nodes_simple_search_and_sort(access_token):
    """Test combining search and sort parameters."""
    names = [
        unique_name("alpha_node_combo"),
        unique_name("beta_node_combo"),
        unique_name("gamma_node_combo"),
        unique_name("other_node_combo"),
    ]
    core_id, node_ids = await setup_nodes_simple(names)
    try:
        response = client.get(
            "/api/nodes/simple",
            headers=auth_headers(access_token),
            params={"search": "_node_combo", "sort": "-name"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        matching = [n for n in data["nodes"] if n["name"] in names and "_node_combo" in n["name"]]
        matching_names = [n["name"] for n in matching]
        assert len(matching_names) >= 3
        assert matching_names == sorted(matching_names, reverse=True)
    finally:
        await cleanup_nodes_simple(core_id, node_ids)


@pytest.mark.asyncio
async def test_remove_node_deletes_associated_usage_tables():
    async with TestSession() as session:
        node_model = NodeCreate(**node_create_payload(name=unique_name("bulk_node")))
        db_node = await db_create_node(session, node_model)
        node_id = db_node.id

        user = User(username=unique_name("bulk_user"), proxy_settings={})
        session.add(user)
        await session.commit()
        await session.refresh(user)

        now = datetime.now(timezone.utc)
        user_usages = [
            NodeUserUsage(
                user_id=user.id,
                node_id=node_id,
                created_at=now + timedelta(minutes=idx),
                used_traffic=idx + 1,
            )
            for idx in range(500)
        ]
        node_usages = [
            NodeUsage(
                node_id=node_id,
                created_at=now + timedelta(hours=idx),
                uplink=1000 + idx,
                downlink=2000 + idx,
            )
            for idx in range(550)
        ]
        reset_logs = [
            NodeUsageResetLogs(
                node_id=node_id,
                uplink=5000 + idx,
                downlink=6000 + idx,
            )
            for idx in range(750)
        ]
        node_stats = [
            NodeStat(
                node_id=node_id,
                mem_total=4096 + idx,
                mem_used=1024 + idx,
                cpu_cores=4,
                cpu_usage=idx % 100,
                incoming_bandwidth_speed=300 + idx,
                outgoing_bandwidth_speed=600 + idx,
            )
            for idx in range(600)
        ]
        session.add_all([*user_usages, *node_usages, *reset_logs, *node_stats])
        await session.commit()

        async def count_rows(model):
            return await session.scalar(select(func.count()).select_from(model).where(model.node_id == node_id))

        assert await count_rows(NodeUserUsage) == len(user_usages)
        assert await count_rows(NodeUsage) == len(node_usages)
        assert await count_rows(NodeUsageResetLogs) == len(reset_logs)
        assert await count_rows(NodeStat) == len(node_stats)

        db_node = await session.get(Node, node_id)
        await db_remove_node(session, db_node)

        assert await count_rows(NodeUserUsage) == 0
        assert await count_rows(NodeUsage) == 0
        assert await count_rows(NodeUsageResetLogs) == 0
        assert await count_rows(NodeStat) == 0
        remaining_nodes = await session.scalar(select(func.count()).select_from(Node).where(Node.id == node_id))
        assert remaining_nodes == 0

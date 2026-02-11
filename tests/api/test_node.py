from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import status
from sqlalchemy import func, inspect, select

from app.db.crud.core import create_core_config, remove_core_config
from app.db.crud.node import create_node as db_create_node, remove_node as db_remove_node
from app.db.models import (
    CoreConfig,
    DataLimitResetStrategy,
    Node,
    NodeConnectionType,
    NodeStat,
    NodeStatus,
    NodeUsage,
    NodeUsageResetLogs,
    NodeUserUsage,
    User,
)
from app.models.core import CoreCreate
from app.models.node import NodeCreate, NodeResponse, NodeSettings, NodesResponse
from app.models.stats import (
    NodeRealtimeStats,
    NodeStats,
    NodeStatsList,
    NodeUsageStat,
    NodeUsageStatsList,
    Period,
)
from tests.api import TestSession, client
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
    }
    data.update(overrides)
    return NodeResponse(**data)


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
        "reset_node_usage",
        "restart_node",
        "sync_node_users",
        "remove_node",
        "get_node_stats_periodic",
        "get_node_system_stats",
    ]
    for name in async_methods:
        setattr(operator, name, AsyncMock(name=name))
    monkeypatch.setattr("app.routers.node.node_operator", operator)
    return operator


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
    assert awaited_kwargs["node_id"] == 5
    assert awaited_kwargs["group_by_node"] is True
    assert awaited_kwargs["period"] == Period.day
    assert awaited_kwargs["start"] == start
    assert awaited_kwargs["end"] == end


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
    assert awaited_kwargs["core_id"] == 2
    assert awaited_kwargs["offset"] == 5
    assert awaited_kwargs["limit"] == 25
    assert awaited_kwargs["enabled"] is True
    assert awaited_kwargs["ids"] == [1, 2]
    assert awaited_kwargs["search"] == "test"
    assert awaited_kwargs["status"] == [NodeStatus.connected, NodeStatus.error]


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


def test_remove_node(access_token, node_operator_mock):
    response = client.delete("/api/node/6", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_204_NO_CONTENT
    awaited_kwargs = node_operator_mock.remove_node.await_args.kwargs
    assert awaited_kwargs["node_id"] == 6


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
    assert awaited_kwargs["start"] == start
    assert awaited_kwargs["end"] == end
    assert awaited_kwargs["period"] == Period.hour


def test_realtime_node_stats(access_token, node_operator_mock):
    realtime_stats = realtime_stats_payload()
    node_operator_mock.get_node_system_stats.return_value = realtime_stats
    response = client.get("/api/node/12/realtime_stats", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == realtime_stats.model_dump()
    awaited_kwargs = node_operator_mock.get_node_system_stats.await_args.kwargs
    assert awaited_kwargs["node_id"] == 12


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

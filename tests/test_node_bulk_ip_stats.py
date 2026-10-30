from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from PasarGuardNodeBridge import NodeAPIError
from sqlalchemy import update

from app.db.models import Admin, AdminRole, Group, ProxyInbound, User, UserStatus, users_groups_association
from app.models.admin import AdminDetails
from app.models.node import UserIPRankingQuery
from app.models.proxy import ProxyTable
from app.operation import OperatorType
from app.operation.node import NodeOperation
from tests.api import TestSession

NOW = datetime.now(UTC)


@dataclass(frozen=True)
class FakeOnlineIps:
    ips: dict[str, int]


@dataclass(frozen=True)
class FakeUsersOnlineIps:
    users: dict[str, FakeOnlineIps]


def _users_response(users: dict[str, dict[str, int]]) -> FakeUsersOnlineIps:
    return FakeUsersOnlineIps(users={email: FakeOnlineIps(ips=ips) for email, ips in users.items()})


class FakeNode:
    def __init__(self, response: FakeUsersOnlineIps | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls = 0

    async def get_users_online_ip_list(self, timeout: int | None = None) -> FakeUsersOnlineIps | None:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._response


class NodeWithoutBulkIpList:
    """Nodes built on an older bridge don't expose get_users_online_ip_list."""


@pytest.mark.asyncio
async def test_bulk_ip_list_converts_response_by_user(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)
    response = _users_response({"1": {"1.2.3.4": 1000}, "2": {"5.6.7.8": 2000}})

    async def fake_get_node(node_id):
        return FakeNode(response)

    monkeypatch.setattr("app.operation.node.node_manager.get_node", fake_get_node)

    result = await operation._get_node_users_ip_list_bulk_safe(1)

    assert result == {"1": {"1.2.3.4": 1000}, "2": {"5.6.7.8": 2000}}


@pytest.mark.asyncio
async def test_bulk_ip_list_returns_empty_dict_for_node_without_online_users(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)

    async def fake_get_node(node_id):
        return FakeNode(_users_response({}))

    monkeypatch.setattr("app.operation.node.node_manager.get_node", fake_get_node)

    result = await operation._get_node_users_ip_list_bulk_safe(1)

    assert result == {}


@pytest.mark.asyncio
async def test_bulk_ip_list_returns_none_for_node_without_method(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)
    debug = []

    async def fake_get_node(node_id):
        return NodeWithoutBulkIpList()

    monkeypatch.setattr("app.operation.node.node_manager.get_node", fake_get_node)
    monkeypatch.setattr("app.operation.node.logger.debug", lambda msg: debug.append(msg))

    result = await operation._get_node_users_ip_list_bulk_safe(1)

    assert result is None
    assert len(debug) == 1


@pytest.mark.asyncio
async def test_bulk_ip_list_returns_none_when_bridge_returns_none(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)

    async def fake_get_node(node_id):
        return FakeNode(None)

    monkeypatch.setattr("app.operation.node.node_manager.get_node", fake_get_node)

    result = await operation._get_node_users_ip_list_bulk_safe(1)

    assert result is None


@pytest.mark.asyncio
async def test_bulk_ip_list_returns_none_when_node_missing(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)

    async def fake_get_node(node_id):
        return None

    monkeypatch.setattr("app.operation.node.node_manager.get_node", fake_get_node)

    result = await operation._get_node_users_ip_list_bulk_safe(1)

    assert result is None


@pytest.mark.asyncio
async def test_bulk_ip_list_logs_non_404_node_api_error(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)
    logged = []

    async def fake_get_node(node_id):
        return FakeNode(error=NodeAPIError(500, "boom"))

    monkeypatch.setattr("app.operation.node.node_manager.get_node", fake_get_node)
    monkeypatch.setattr("app.operation.node.logger.error", lambda msg: logged.append(msg))

    result = await operation._get_node_users_ip_list_bulk_safe(1)

    assert result is None
    assert len(logged) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [404, 501])
async def test_bulk_ip_list_skips_quietly_for_missing_node_or_unimplemented_rpc(
    monkeypatch: pytest.MonkeyPatch, code: int
):
    """501 comes from nodes that predate the RPC; both codes mean skip, not error."""
    operation = NodeOperation(operator_type=OperatorType.API)
    logged = []

    async def fake_get_node(node_id):
        return FakeNode(error=NodeAPIError(code, "unimplemented"))

    debug = []

    monkeypatch.setattr("app.operation.node.node_manager.get_node", fake_get_node)
    monkeypatch.setattr("app.operation.node.logger.error", lambda msg: logged.append(msg))
    monkeypatch.setattr("app.operation.node.logger.debug", lambda msg: debug.append(msg))

    result = await operation._get_node_users_ip_list_bulk_safe(1)

    assert result is None
    assert logged == []
    assert len(debug) == 1


@pytest.mark.asyncio
async def test_online_ips_unions_across_nodes(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)

    per_node = {
        1: {"1": {"1.2.3.4": 1000}, "2": {"9.9.9.9": 500}},
        2: {"1": {"5.6.7.8": 2000}},
    }

    async def fake_get_healthy_nodes():
        return [(1, object()), (2, object())]

    async def fake_bulk(node_id):
        return per_node[node_id]

    monkeypatch.setattr("app.operation.node.node_manager.get_healthy_nodes", fake_get_healthy_nodes)
    monkeypatch.setattr(operation, "_get_node_users_ip_list_bulk_safe", fake_bulk)

    result, skipped_node_count = await operation._get_users_online_ips()

    assert result == {1: {"1.2.3.4": 1000, "5.6.7.8": 2000}, 2: {"9.9.9.9": 500}}
    assert skipped_node_count == 0


@pytest.mark.asyncio
async def test_online_ips_keeps_latest_last_seen_for_same_ip_across_nodes(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)

    per_node = {
        1: {"1": {"1.2.3.4": 1000}},
        2: {"1": {"1.2.3.4": 2000}},
    }

    async def fake_get_healthy_nodes():
        return [(1, object()), (2, object())]

    async def fake_bulk(node_id):
        return per_node[node_id]

    monkeypatch.setattr("app.operation.node.node_manager.get_healthy_nodes", fake_get_healthy_nodes)
    monkeypatch.setattr(operation, "_get_node_users_ip_list_bulk_safe", fake_bulk)

    result, skipped_node_count = await operation._get_users_online_ips()

    assert result == {1: {"1.2.3.4": 2000}}
    assert skipped_node_count == 0


@pytest.mark.asyncio
async def test_online_ips_counts_nodes_that_cannot_report_as_skipped(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)

    async def fake_get_healthy_nodes():
        return [(1, object()), (2, object())]

    async def fake_bulk(node_id):
        if node_id == 1:
            return {"1": {"1.2.3.4": 1000}}
        return None

    monkeypatch.setattr("app.operation.node.node_manager.get_healthy_nodes", fake_get_healthy_nodes)
    monkeypatch.setattr(operation, "_get_node_users_ip_list_bulk_safe", fake_bulk)

    result, skipped_node_count = await operation._get_users_online_ips()

    assert result == {1: {"1.2.3.4": 1000}}
    assert skipped_node_count == 1


@pytest.mark.asyncio
async def test_online_ips_filters_by_node_ids(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)

    per_node = {
        1: {"1": {"1.2.3.4": 1000}},
        2: {"1": {"5.6.7.8": 2000}},
    }
    queried = []

    async def fake_get_healthy_nodes():
        return [(1, object()), (2, object())]

    async def fake_bulk(node_id):
        queried.append(node_id)
        return per_node[node_id]

    monkeypatch.setattr("app.operation.node.node_manager.get_healthy_nodes", fake_get_healthy_nodes)
    monkeypatch.setattr(operation, "_get_node_users_ip_list_bulk_safe", fake_bulk)

    result, skipped_node_count = await operation._get_users_online_ips(node_ids=[2])

    assert queried == [2]
    assert result == {1: {"5.6.7.8": 2000}}
    assert skipped_node_count == 0


def _ips(count: int, *, offset: int = 0) -> dict[str, int]:
    return {f"10.0.{offset}.{i}": 1000 + i for i in range(count)}


async def _make_ranking_fixture():
    suffix = uuid4().hex[:8]
    async with TestSession() as session:
        role = AdminRole(name=f"ipr_role_{suffix}", is_owner=False, permissions={}, limits={}, features={}, access={})
        session.add(role)
        await session.flush()

        admin_a = Admin(username=f"ipr_admin_a_{suffix}", hashed_password="secret", role_id=role.id)
        admin_b = Admin(username=f"ipr_admin_b_{suffix}", hashed_password="secret", role_id=role.id)
        session.add_all([admin_a, admin_b])
        await session.flush()

        inbound = ProxyInbound(tag=f"ipr_tag_{suffix}")
        group = Group(name=f"ipr_group_{suffix}", inbounds=[inbound])
        session.add(group)
        await session.flush()

        active_user = User(
            username=f"ipr_active_{suffix}",
            admin_id=admin_a.id,
            proxy_settings=ProxyTable().dict(no_obj=True),
            status=UserStatus.active,
            used_traffic=1_000,
        )
        limited_user = User(
            username=f"ipr_limited_{suffix}",
            admin_id=admin_a.id,
            proxy_settings=ProxyTable().dict(no_obj=True),
            status=UserStatus.limited,
            used_traffic=2_000,
        )
        other_admin_user = User(
            username=f"ipr_other_admin_{suffix}",
            admin_id=admin_b.id,
            proxy_settings=ProxyTable().dict(no_obj=True),
            status=UserStatus.active,
            used_traffic=3_000,
        )
        session.add_all([active_user, limited_user, other_admin_user])
        await session.flush()

        await session.execute(
            users_groups_association.insert(),
            [{"user_id": active_user.id, "groups_id": group.id}],
        )
        await session.commit()

        return {
            "admin_a": admin_a.id,
            "admin_b": admin_b.id,
            "group": group.id,
            "active": active_user.id,
            "limited": limited_user.id,
            "other_admin": other_admin_user.id,
        }


@pytest.mark.asyncio
async def test_ip_ranking_filters_by_ip_count_range():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    ips_by_user = {ids["active"]: _ips(10), ids["limited"]: _ips(50), ids["other_admin"]: _ips(100)}

    async with TestSession() as session:
        result = await operation._resolve_ip_ranking(
            session, ips_by_user, NOW, UserIPRankingQuery(ip_count_min=50, ip_count_max=100)
        )

    assert {entry.user_id for entry in result.users} == {ids["limited"], ids["other_admin"]}


@pytest.mark.asyncio
async def test_ip_ranking_filters_by_admin_ids():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    ips_by_user = {ids["active"]: _ips(5), ids["limited"]: _ips(5), ids["other_admin"]: _ips(5)}

    async with TestSession() as session:
        result = await operation._resolve_ip_ranking(
            session, ips_by_user, NOW, UserIPRankingQuery(admin_ids=[ids["admin_a"]])
        )

    assert {entry.user_id for entry in result.users} == {ids["active"], ids["limited"]}


@pytest.mark.asyncio
async def test_ip_ranking_filters_by_group_ids():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    ips_by_user = {ids["active"]: _ips(5), ids["limited"]: _ips(5), ids["other_admin"]: _ips(5)}

    async with TestSession() as session:
        result = await operation._resolve_ip_ranking(
            session, ips_by_user, NOW, UserIPRankingQuery(group_ids=[ids["group"]])
        )

    assert {entry.user_id for entry in result.users} == {ids["active"]}


@pytest.mark.asyncio
async def test_ip_ranking_filters_by_status():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    ips_by_user = {ids["active"]: _ips(5), ids["limited"]: _ips(5), ids["other_admin"]: _ips(5)}

    async with TestSession() as session:
        result = await operation._resolve_ip_ranking(
            session, ips_by_user, NOW, UserIPRankingQuery(status=UserStatus.limited)
        )

    assert {entry.user_id for entry in result.users} == {ids["limited"]}


@pytest.mark.asyncio
async def test_ip_ranking_applies_offset_and_limit_after_sorting():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    ips_by_user = {ids["active"]: _ips(10), ids["limited"]: _ips(30), ids["other_admin"]: _ips(20)}

    async with TestSession() as session:
        result = await operation._resolve_ip_ranking(session, ips_by_user, NOW, UserIPRankingQuery(offset=1, limit=1))

    assert [entry.user_id for entry in result.users] == [ids["other_admin"]]
    assert result.total == 3


@pytest.mark.asyncio
async def test_ip_ranking_entries_include_ips_and_traffic():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    active_ips = _ips(2)
    ips_by_user = {ids["active"]: active_ips, ids["limited"]: _ips(1)}

    async with TestSession() as session:
        result = await operation._resolve_ip_ranking(session, ips_by_user, NOW, UserIPRankingQuery())

    entry = next(entry for entry in result.users if entry.user_id == ids["active"])
    assert entry.ips == active_ips
    assert entry.distinct_ip_count == 2
    assert entry.used_traffic == 1_000


@pytest.mark.asyncio
async def test_ip_ranking_skips_users_without_online_ips():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    ips_by_user = {ids["active"]: {}, ids["limited"]: _ips(2)}

    async with TestSession() as session:
        result = await operation._resolve_ip_ranking(session, ips_by_user, NOW, UserIPRankingQuery())

    assert [entry.user_id for entry in result.users] == [ids["limited"]]
    assert result.total == 1


@pytest.mark.asyncio
async def test_ip_ranking_with_no_online_ips_returns_empty_list():
    await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)

    async with TestSession() as session:
        result = await operation._resolve_ip_ranking(session, {}, NOW, UserIPRankingQuery())

    assert result.users == []
    assert result.total == 0


@pytest.mark.asyncio
async def test_ip_ranking_orders_by_ip_count_then_traffic_then_username():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    ips_by_user = {ids["active"]: _ips(3), ids["limited"]: _ips(2), ids["other_admin"]: _ips(2)}

    async with TestSession() as session:
        result = await operation._resolve_ip_ranking(session, ips_by_user, NOW, UserIPRankingQuery())

    assert [entry.user_id for entry in result.users] == [ids["active"], ids["other_admin"], ids["limited"]]


@pytest.mark.asyncio
async def test_ip_ranking_breaks_equal_ip_count_by_username_when_traffic_equal():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    ips_by_user = {ids["active"]: _ips(2), ids["limited"]: _ips(2), ids["other_admin"]: _ips(2)}

    async with TestSession() as session:
        await session.execute(update(User).where(User.id == ids["limited"]).values(used_traffic=3_000))
        await session.commit()
        result = await operation._resolve_ip_ranking(session, ips_by_user, NOW, UserIPRankingQuery())

    assert [entry.user_id for entry in result.users] == [ids["limited"], ids["other_admin"], ids["active"]]


@pytest.mark.asyncio
async def test_ip_ranking_offset_past_end_returns_empty_page():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    ips_by_user = {ids["active"]: _ips(1), ids["limited"]: _ips(2)}

    async with TestSession() as session:
        result = await operation._resolve_ip_ranking(session, ips_by_user, NOW, UserIPRankingQuery(offset=10, limit=5))

    assert result.users == []
    assert result.total == 2


@pytest.mark.asyncio
async def test_online_ips_keeps_ip_whose_last_seen_is_zero(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)

    async def fake_get_healthy_nodes():
        return [(1, object())]

    async def fake_bulk(node_id):
        return {"1": {"1.2.3.4": 0}}

    monkeypatch.setattr("app.operation.node.node_manager.get_healthy_nodes", fake_get_healthy_nodes)
    monkeypatch.setattr(operation, "_get_node_users_ip_list_bulk_safe", fake_bulk)

    result, _ = await operation._get_users_online_ips()

    assert result == {1: {"1.2.3.4": 0}}


@pytest.mark.asyncio
async def test_ip_ranking_with_owner_lists_only_that_admins_users():
    ids = await _make_ranking_fixture()
    operation = NodeOperation(operator_type=OperatorType.API)
    ips_by_user = {ids["active"]: _ips(5), ids["limited"]: _ips(5), ids["other_admin"]: _ips(9)}

    async with TestSession() as session:
        owner = (await session.get(Admin, ids["admin_a"])).username
        result = await operation._resolve_ip_ranking(
            session, ips_by_user, NOW, UserIPRankingQuery(admin_ids=[ids["admin_b"]]), owner=owner
        )

    assert {entry.user_id for entry in result.users} == {ids["active"], ids["limited"]}


def _admin_with(users_read) -> AdminDetails:
    permissions = {"nodes": {"stats": True}}
    if users_read is not None:
        permissions["users"] = {"read": users_read}
    role = {"is_owner": False, "permissions": permissions, "limits": {}, "features": {}, "access": {}}
    return AdminDetails(id=7, username="scoped_admin", role=role)


@pytest.mark.asyncio
async def test_ip_ranking_needs_users_read(monkeypatch: pytest.MonkeyPatch):
    operation = NodeOperation(operator_type=OperatorType.API)
    monkeypatch.setattr(operation, "_get_users_ip_ranking_impl", AsyncMock())

    with pytest.raises(HTTPException) as denied:
        await operation.get_users_ip_ranking(None, UserIPRankingQuery(), _admin_with(None))

    assert denied.value.status_code == 403
    operation._get_users_ip_ranking_impl.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(("users_read", "expected_owner"), [({"scope": 1}, "scoped_admin"), ({"scope": 2}, None)])
async def test_ip_ranking_follows_the_users_read_scope(
    monkeypatch: pytest.MonkeyPatch, users_read: dict[str, int], expected_owner: str | None
):
    operation = NodeOperation(operator_type=OperatorType.API)
    impl = AsyncMock()
    monkeypatch.setattr(operation, "_get_users_ip_ranking_impl", impl)
    query = UserIPRankingQuery()

    await operation.get_users_ip_ranking(None, query, _admin_with(users_read))

    impl.assert_awaited_once_with(None, query, expected_owner)

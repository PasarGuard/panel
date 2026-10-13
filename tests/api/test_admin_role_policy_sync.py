"""Role disconnect-policy edits and the node reconciliation they trigger."""

import asyncio

from fastapi import status
from sqlalchemy import update

from app.db.models import Admin, AdminRole, AdminStatus, User, UserStatus
from app.node import node_manager
from app.operation import admin_role as admin_role_operation, admin_sync
from tests.api import GetTestDB, TestSession, client
from tests.api.helpers import auth_headers, create_user, strong_password, unique_name

UNREACHABLE_NODE_ID = 987654


class UnreachableNode:
    """Answers like the bridge does for a node it cannot reach: every user comes back as failed."""

    def __init__(self):
        self.chunked_calls = 0

    async def _supports_chunked_sync(self):
        return True, None

    async def sync_users_chunked(self, users, chunk_size=100, flush_pending=False, timeout=None):
        self.chunked_calls += 1
        return list(users)

    async def _sync_batch_users(self, users):
        return list(users)


def _role_payload(*, blocks: bool) -> dict:
    """The full body the dashboard sends when a role is saved."""
    return {
        "name": unique_name("policy_role"),
        "permissions": {},
        "limits": {
            "max_users": None,
            "data_limit_min": None,
            "data_limit_max": None,
            "expire_min": None,
            "expire_max": None,
            "max_hwid_per_user": None,
        },
        "features": {"can_use_reset_strategy": True, "can_use_next_plan": True},
        "access": {"require_template": False, "allowed_template_ids": None, "allowed_group_ids": None},
        "hwid": {
            "mode": "use_global",
            "enabled": True,
            "forced": False,
            "fallback_limit": None,
            "min_limit": None,
            "max_limit": None,
        },
        "disabled_when_limited": False,
        "disconnect_users_when_limited": blocks,
        "disconnect_users_when_disabled": blocks,
    }


def _create_role(access_token: str, payload: dict) -> int:
    response = client.post("/api/admin-role", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()["id"]


def _create_disabled_admin_with_users(access_token: str, role_id: int, statuses: list[UserStatus]) -> list[int]:
    response = client.post(
        "/api/admin",
        headers=auth_headers(access_token),
        json={"username": unique_name("policy_admin"), "password": strong_password("PolicyAdmin"), "role_id": role_id},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    admin_id = response.json()["id"]
    user_ids = [create_user(access_token)["id"] for _ in statuses]

    async def assign():
        async with TestSession() as session:
            for user_id, user_status in zip(user_ids, statuses, strict=True):
                await session.execute(
                    update(User).where(User.id == user_id).values(admin_id=admin_id, status=user_status)
                )
            await session.execute(update(Admin).where(Admin.id == admin_id).values(status=AdminStatus.disabled))
            await session.commit()

    asyncio.run(assign())
    return user_ids


def _set_disabled_policy(role_id: int, blocks: bool) -> None:
    async def run():
        async with TestSession() as session:
            await session.execute(
                update(AdminRole).where(AdminRole.id == role_id).values(disconnect_users_when_disabled=blocks)
            )
            await session.commit()

    asyncio.run(run())


def _record_schedules(monkeypatch) -> list[tuple[int, list[AdminStatus]]]:
    calls = []
    monkeypatch.setattr(
        admin_role_operation,
        "schedule_role_users_block_sync",
        lambda role_id, statuses: calls.append((role_id, list(statuses))),
    )
    return calls


def _record_dispatches(monkeypatch) -> dict[str, list[list[int]]]:
    batches = {"remove": [], "sync": []}

    def recorder(kind):
        async def dispatch(users, *, await_dispatch=False):
            assert await_dispatch is True
            batches[kind].append([user.id for user in users])

        return dispatch

    monkeypatch.setattr(admin_sync, "sync_remove_users", recorder("remove"))
    monkeypatch.setattr(admin_sync, "sync_users", recorder("sync"))
    return batches


def test_role_save_without_policy_change_does_not_dispatch(access_token, monkeypatch):
    payload = _role_payload(blocks=True)
    role_id = _create_role(access_token, payload)
    _create_disabled_admin_with_users(access_token, role_id, [UserStatus.active])
    calls = _record_schedules(monkeypatch)

    node = UnreachableNode()
    node_manager._nodes[UNREACHABLE_NODE_ID] = node
    try:
        # The dashboard always sends both policy fields; a rename must not touch nodes.
        response = client.put(
            f"/api/admin-role/{role_id}",
            headers=auth_headers(access_token),
            json={**payload, "name": unique_name("renamed_role")},
        )
    finally:
        node_manager._nodes.pop(UNREACHABLE_NODE_ID, None)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert calls == []
    assert node.chunked_calls == 0


def test_role_policy_change_schedules_only_the_changed_status(access_token, monkeypatch):
    payload = _role_payload(blocks=True)
    role_id = _create_role(access_token, payload)
    calls = _record_schedules(monkeypatch)

    response = client.put(
        f"/api/admin-role/{role_id}",
        headers=auth_headers(access_token),
        json={**payload, "disconnect_users_when_disabled": False},
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()["disconnect_users_when_disabled"] is False
    assert calls == [(role_id, [AdminStatus.disabled])]


def test_role_policy_sync_follows_current_policy_in_bounded_batches(access_token, monkeypatch):
    role_id = _create_role(access_token, _role_payload(blocks=True))
    user_ids = _create_disabled_admin_with_users(
        access_token,
        role_id,
        [UserStatus.active, UserStatus.on_hold, UserStatus.active, UserStatus.expired],
    )
    connectable = sorted(user_ids[:3])
    monkeypatch.setattr(admin_sync, "GetDB", GetTestDB)
    monkeypatch.setattr(admin_sync, "_role_sync_locks", {})
    monkeypatch.setattr(admin_sync, "ROLE_SYNC_BATCH_SIZE", 2)
    batches = _record_dispatches(monkeypatch)

    # The role blocks users of disabled admins: connectable users are removed, in ID order.
    assert asyncio.run(admin_sync.apply_role_users_block_sync(role_id, [AdminStatus.disabled])) == 3
    assert batches == {"remove": [connectable[:2], connectable[2:]], "sync": []}

    # The task reads the policy again when it runs, so the latest edit wins.
    _set_disabled_policy(role_id, False)
    batches["remove"].clear()
    assert asyncio.run(admin_sync.apply_role_users_block_sync(role_id, [AdminStatus.disabled])) == 3
    assert batches == {"remove": [], "sync": [connectable[:2], connectable[2:]]}

    # A status whose policy did not change is left alone.
    batches["sync"].clear()
    assert asyncio.run(admin_sync.apply_role_users_block_sync(role_id, [AdminStatus.limited])) == 0
    assert batches == {"remove": [], "sync": []}


def test_role_policy_sync_tolerates_an_unreachable_node(access_token, monkeypatch):
    role_id = _create_role(access_token, _role_payload(blocks=True))
    _create_disabled_admin_with_users(access_token, role_id, [UserStatus.active])
    monkeypatch.setattr(admin_sync, "GetDB", GetTestDB)
    monkeypatch.setattr(admin_sync, "_role_sync_locks", {})

    node = UnreachableNode()
    node_manager._nodes[UNREACHABLE_NODE_ID] = node
    try:
        removed = asyncio.run(admin_sync.apply_role_users_block_sync(role_id, [AdminStatus.disabled]))
        _set_disabled_policy(role_id, False)
        restored = asyncio.run(admin_sync.apply_role_users_block_sync(role_id, [AdminStatus.disabled]))
    finally:
        node_manager._nodes.pop(UNREACHABLE_NODE_ID, None)

    assert (removed, restored) == (1, 1)
    assert node.chunked_calls == 2


def test_role_policy_sync_failure_is_logged_not_raised(monkeypatch):
    async def broken_get_role(db, role_id):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(admin_sync, "GetDB", GetTestDB)
    monkeypatch.setattr(admin_sync, "_role_sync_locks", {})
    monkeypatch.setattr(admin_sync, "get_role", broken_get_role)

    # The background task has no caller to report to: a failure is logged and swallowed.
    assert asyncio.run(admin_sync.apply_role_users_block_sync(1, [AdminStatus.disabled])) == 0

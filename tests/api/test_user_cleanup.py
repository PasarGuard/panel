from datetime import UTC, datetime as dt, timedelta as td

import pytest
from fastapi import status
from sqlalchemy import select

from app.db.models import User
from app.models.user import UserStatus
from tests.api import TestSession, client
from tests.api.helpers import auth_headers, create_user

NOW = dt.now(UTC)
CUTOFF = (NOW - td(days=30)).isoformat()


async def _set_activity(user_id: int, *, online_at: dt | None, created_at: dt, user_status: UserStatus | None = None):
    async with TestSession() as session:
        db_user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        db_user.online_at = online_at
        db_user.created_at = created_at
        if user_status is not None:
            db_user.status = user_status
        await session.commit()


def _cleanup_leftovers(access_token: str, users: list[dict]) -> None:
    for user in users:
        client.delete(f"/api/user/{user['username']}", headers=auth_headers(access_token))


@pytest.mark.asyncio
async def test_inactive_target_selects_by_last_activity(access_token):
    users = {name: create_user(access_token) for name in ("idle", "recent", "never_old", "never_new")}

    try:
        await _set_activity(users["idle"]["id"], online_at=NOW - td(days=60), created_at=NOW - td(days=90))
        await _set_activity(users["recent"]["id"], online_at=NOW - td(days=1), created_at=NOW - td(days=90))
        await _set_activity(users["never_old"]["id"], online_at=None, created_at=NOW - td(days=60))
        await _set_activity(users["never_new"]["id"], online_at=None, created_at=NOW - td(days=1))

        response = client.get(
            "/api/users/expired",
            params={"target": "inactive", "expired_before": CUTOFF},
            headers=auth_headers(access_token),
        )

        assert response.status_code == status.HTTP_200_OK
        selected = set(response.json())
        assert {users["idle"]["username"], users["never_old"]["username"]} <= selected
        assert not {users["recent"]["username"], users["never_new"]["username"]} & selected
    finally:
        _cleanup_leftovers(access_token, list(users.values()))


def test_inactive_target_requires_a_cutoff(access_token):
    response = client.get("/api/users/expired", params={"target": "inactive"}, headers=auth_headers(access_token))

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_inactive_cleanup_removes_provisioned_users_from_nodes(access_token, monkeypatch):
    removed_from_nodes: list[int] = []

    async def capture_node_removal(users) -> None:
        removed_from_nodes.extend(user.id for user in users)

    monkeypatch.setattr("app.operation.user.sync_remove_users", capture_node_removal)
    users = {name: create_user(access_token) for name in ("active", "on_hold", "disabled")}

    try:
        await _set_activity(users["active"]["id"], online_at=NOW - td(days=60), created_at=NOW - td(days=90))
        await _set_activity(
            users["on_hold"]["id"], online_at=None, created_at=NOW - td(days=60), user_status=UserStatus.on_hold
        )
        await _set_activity(
            users["disabled"]["id"],
            online_at=NOW - td(days=60),
            created_at=NOW - td(days=90),
            user_status=UserStatus.disabled,
        )
        params = {"target": "inactive", "expired_before": CUTOFF}

        response = client.delete(
            "/api/users/expired", params={**params, "dry_run": True}, headers=auth_headers(access_token)
        )
        assert response.status_code == status.HTTP_200_OK
        assert removed_from_nodes == []

        response = client.delete("/api/users/expired", params=params, headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK
        assert {user["username"] for user in users.values()} <= set(response.json()["users"])

        # Disabled users are already off the nodes; active and on_hold ones are not.
        assert users["active"]["id"] in removed_from_nodes
        assert users["on_hold"]["id"] in removed_from_nodes
        assert users["disabled"]["id"] not in removed_from_nodes
        for user in users.values():
            response = client.get(f"/api/user/{user['username']}", headers=auth_headers(access_token))
            assert response.status_code == status.HTTP_404_NOT_FOUND
    finally:
        _cleanup_leftovers(access_token, list(users.values()))

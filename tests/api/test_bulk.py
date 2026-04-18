import asyncio
from datetime import datetime as dt, timedelta as td, timezone as tz

from fastapi import status
from sqlalchemy import select

from app.db.models import User
from tests.api import TestSession
from tests.api import client
from tests.api.helpers import (
    create_admin,
    create_core,
    create_group,
    create_user,
    delete_admin,
    delete_core,
    delete_group,
    delete_user,
    unique_name,
)


def setup_groups(access_token: str, count: int = 1):
    core = create_core(access_token)
    groups = [create_group(access_token, name=unique_name(f"bulk_group_{idx}")) for idx in range(count)]
    return core, groups


def cleanup(access_token: str, core: dict, groups: list[dict], users: list[dict]):
    for user in users:
        delete_user(access_token, user["username"])
    for group in groups:
        delete_group(access_token, group["id"])
    delete_core(access_token, core["id"])


def set_user_used_traffic(username: str, used_traffic: int) -> None:
    async def _set_usage():
        async with TestSession() as session:
            result = await session.execute(select(User).where(User.username == username))
            db_user = result.scalar_one()
            db_user.used_traffic = used_traffic
            await session.commit()

    asyncio.run(_set_usage())


def get_user_sub_revoked_at(username: str):
    async def _get_revoked_at():
        async with TestSession() as session:
            result = await session.execute(select(User).where(User.username == username))
            db_user = result.scalar_one()
            return db_user.sub_revoked_at

    return asyncio.run(_get_revoked_at())


def test_add_groups_to_users(access_token):
    """Test bulk adding groups to users."""

    core, groups = setup_groups(access_token, 2)
    users = [create_user(access_token, payload={"username": unique_name("bulk_user")}) for _ in range(2)]
    group_ids = [group["id"] for group in groups]
    try:
        response = client.post(
            "/api/groups/bulk/add",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"group_ids": group_ids},
        )

        assert response.status_code == status.HTTP_200_OK
        for user in users:
            response = client.get(f"/api/user/{user['username']}", headers={"Authorization": f"Bearer {access_token}"})
            assert set(response.json()["group_ids"]) == set(group_ids)
    finally:
        cleanup(access_token, core, groups, users)


def test_remove_groups_from_users(access_token):
    """Test bulk removing groups from users."""
    core, groups = setup_groups(access_token, 2)
    users = [create_user(access_token, payload={"username": unique_name("bulk_user_remove")}) for _ in range(2)]
    group_ids = [group["id"] for group in groups]
    try:
        client.post(
            "/api/groups/bulk/add",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"group_ids": group_ids},
        )
        response = client.post(
            "/api/groups/bulk/remove",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"group_ids": [group_ids[0]]},
        )

        assert response.status_code == status.HTTP_200_OK
        for user in users:
            response = client.get(f"/api/user/{user['username']}", headers={"Authorization": f"Bearer {access_token}"})
            assert set(response.json()["group_ids"]) == {group_ids[1]}
    finally:
        cleanup(access_token, core, groups, users)


def test_update_users_datalimit(access_token):
    """Test bulk updating user data limits."""
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(
            access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user7"), "data_limit": 100}
        ),
        create_user(
            access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user8"), "data_limit": 200}
        ),
    ]
    user_ids = [user["id"] for user in users]
    try:
        response = client.post(
            "/api/users/bulk/data_limit",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "amount": 50,
                "users": user_ids,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        response = client.get("/api/users", headers={"Authorization": f"Bearer {access_token}"})
        listed = {u["id"]: u for u in response.json()["users"] if u["id"] in user_ids}
        assert listed[users[0]["id"]]["data_limit"] == 150
        assert listed[users[1]["id"]]["data_limit"] == 250
    finally:
        cleanup(access_token, core, groups, users)


def test_update_users_expire(access_token):
    """Test bulk updating user expiration dates."""
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user_expire1")}),
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user_expire2")}),
    ]
    client.put(
        f"/api/user/{users[0]['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": "2025-01-01T00:00:00+00:00"},
    )
    client.put(
        f"/api/user/{users[1]['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": "2026-01-01T00:00:00+00:00"},
    )

    try:
        response = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 3600},
        )

        assert response.status_code == status.HTTP_200_OK
        response = client.get("/api/users", headers={"Authorization": f"Bearer {access_token}"})
        listed = {
            u["username"]: u
            for u in response.json()["users"]
            if u["username"] in {users[0]["username"], users[1]["username"]}
        }
        assert (
            dt.fromisoformat(listed[users[0]["username"]]["expire"]).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
            == "2025-01-01T01:00:00"
        )
        assert (
            dt.fromisoformat(listed[users[1]["username"]]["expire"]).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
            == "2026-01-01T01:00:00"
        )
    finally:
        cleanup(access_token, core, groups, users)


def test_update_users_proxy_settings(access_token):
    """Test bulk updating user proxy settings."""
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user_proxy1")}),
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user_proxy2")}),
    ]
    try:
        response = client.post(
            "/api/users/bulk/proxy_settings",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"flow": "xtls-rprx-vision"},
        )

        assert response.status_code == status.HTTP_200_OK
        response = client.get("/api/users", headers={"Authorization": f"Bearer {access_token}"})
        listed = {
            u["username"]: u
            for u in response.json()["users"]
            if u["username"] in {users[0]["username"], users[1]["username"]}
        }
        assert listed[users[0]["username"]]["proxy_settings"]["vless"]["flow"] == "xtls-rprx-vision"
        assert listed[users[1]["username"]]["proxy_settings"]["vless"]["flow"] == "xtls-rprx-vision"
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_expire_with_range(access_token):
    # Setup
    core = create_core(access_token)
    group = create_group(access_token, name=unique_name("bulk_range_group"))

    # Create two users, both expired, but at different times
    # User 1: expired 2 days ago
    # User 2: expired 10 days ago

    now = dt.now(tz.utc).replace(microsecond=0)
    expire1 = now - td(days=2)
    expire2 = now - td(days=10)

    user1 = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("exp_range1")})
    user2 = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("exp_range2")})

    # Manually set them to expired status by setting expire date in the past
    # Note: the API might return slightly different formatted strings, so we use isoformat
    client.put(
        f"/api/user/{user1['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": expire1.isoformat()},
    )
    client.put(
        f"/api/user/{user2['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": expire2.isoformat()},
    )

    try:
        # Bulk modify expire for those expired between 1 and 3 days ago (should only target user1)
        expired_after = now - td(days=3)
        expired_before = now - td(days=1)

        response = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "amount": 3600,  # Add 1 hour
                "status": ["expired"],
                "expired_after": expired_after.isoformat(),
                "expired_before": expired_before.isoformat(),
            },
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify user1 was updated
        resp1 = client.get(f"/api/user/{user1['username']}", headers={"Authorization": f"Bearer {access_token}"})
        new_expire1 = dt.fromisoformat(resp1.json()["expire"].replace("Z", "+00:00"))
        # Should be approximately expire1 + 1 hour
        assert (new_expire1 - expire1).total_seconds() == 3600

        # Verify user2 was NOT updated
        resp2 = client.get(f"/api/user/{user2['username']}", headers={"Authorization": f"Bearer {access_token}"})
        new_expire2 = dt.fromisoformat(resp2.json()["expire"].replace("Z", "+00:00"))
        # Should be exactly expire2 (or very close)
        assert abs((new_expire2 - expire2).total_seconds()) < 1

    finally:
        delete_user(access_token, user1["username"])
        delete_user(access_token, user2["username"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_bulk_expire_dry_run(access_token):
    """Dry-run returns affected user count without modifying users."""
    response = client.post(
        "/api/users/bulk/expire",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"amount": 3600, "dry_run": True},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["dry_run"] is True
    assert "affected_users" in data


def test_bulk_delete_users_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_delete")})
        for _ in range(2)
    ]
    try:
        response = client.post(
            "/api/users/bulk/delete",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)

        lookup = client.get(
            "/api/users",
            params={"username": [user["username"] for user in users]},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert lookup.status_code == status.HTTP_200_OK
        assert lookup.json()["users"] == []
    finally:
        cleanup(access_token, core, groups, [])


def test_bulk_reset_users_usage_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_reset")})
        for _ in range(2)
    ]
    try:
        for index, user in enumerate(users, start=1):
            set_user_used_traffic(user["username"], index * 1024)

        response = client.post(
            "/api/users/bulk/reset",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)

        for user in users:
            user_response = client.get(
                f"/api/user/{user['username']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["used_traffic"] == 0
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_revoke_users_subscription_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_revoke")})
        for _ in range(2)
    ]
    try:
        response = client.post(
            "/api/users/bulk/revoke_sub",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)
        for user in users:
            assert get_user_sub_revoked_at(user["username"]) is not None
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_disable_users_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_disable")})
        for _ in range(2)
    ]
    try:
        response = client.post(
            "/api/users/bulk/disable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)

        for user in users:
            user_response = client.get(
                f"/api/user/{user['username']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["status"] == "disabled"
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_enable_users_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_enable")})
        for _ in range(2)
    ]
    try:
        disable_response = client.post(
            "/api/users/bulk/disable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )
        assert disable_response.status_code == status.HTTP_200_OK

        response = client.post(
            "/api/users/bulk/enable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)

        for user in users:
            user_response = client.get(
                f"/api/user/{user['username']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["status"] == "active"
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_disable_enable_users_ignore_noops(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_noop")})
        for _ in range(2)
    ]
    try:
        first_user = users[0]
        second_user = users[1]
        disable_single_response = client.put(
            f"/api/user/{first_user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"status": "disabled"},
        )
        assert disable_single_response.status_code == status.HTTP_200_OK

        disable_bulk_response = client.post(
            "/api/users/bulk/disable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [first_user["id"], second_user["id"]]},
        )
        assert disable_bulk_response.status_code == status.HTTP_200_OK
        assert disable_bulk_response.json()["count"] == 1

        enable_bulk_response = client.post(
            "/api/users/bulk/enable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [first_user["id"], second_user["id"]]},
        )
        assert enable_bulk_response.status_code == status.HTTP_200_OK
        assert enable_bulk_response.json()["count"] == 2

        enable_again_response = client.post(
            "/api/users/bulk/enable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [first_user["id"], second_user["id"]]},
        )
        assert enable_again_response.status_code == status.HTTP_200_OK
        assert enable_again_response.json()["count"] == 0
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_set_owner_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_owner")})
        for _ in range(2)
    ]
    new_owner = create_admin(access_token, is_sudo=False)
    try:
        response = client.put(
            "/api/users/bulk/set_owner",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users], "admin_username": new_owner["username"]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)

        for user in users:
            user_response = client.get(
                f"/api/user/{user['username']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["admin"]["username"] == new_owner["username"]
    finally:
        cleanup(access_token, core, groups, users)
        delete_admin(access_token, new_owner["username"])


def test_bulk_wireguard_reallocate_peer_ips_accepts_status_filter(access_token):
    """Dry-run accepts optional status filter like other bulk user actions."""
    response = client.post(
        "/api/users/bulk/wireguard/reallocate-peer-ips",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "dry_run": True,
            "confirm": False,
            "status": ["active", "disabled"],
        },
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["dry_run"] is True
    assert "candidates" in data
    assert "affected_users" in data

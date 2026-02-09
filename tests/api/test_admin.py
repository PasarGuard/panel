from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status

from app.db.models import NodeUserUsage
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_user,
    delete_admin,
    delete_user,
    unique_name,
    strong_password,
)


def set_user_owner(access_token: str, username: str, admin_username: str) -> None:
    response = client.put(
        f"/api/user/{username}/set_owner",
        headers=auth_headers(access_token),
        params={"admin_username": admin_username},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["admin"]["username"] == admin_username


def test_admin_login():
    """Test that the admin login route is accessible."""

    response = client.post(
        url="/api/admin/token",
        data={"username": "testadmin", "password": "testadmin", "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()
    return response.json()["access_token"]


def test_get_admin(access_token):
    """Test that the admin get route is accessible."""

    # mock_settings(monkeypatch)
    username = "testadmin"
    response = client.get(
        url="/api/admin",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == username


def test_admin_create(access_token):
    """Test that the admin create route is accessible."""

    username = unique_name("testadmincreate")
    password = strong_password("TestAdmincreate")
    admin = create_admin(access_token, username=username, password=password)
    assert admin["username"] == username
    assert admin["is_sudo"] is False
    delete_admin(access_token, username)


def test_admin_db_login(access_token):
    """Test that the admin db login route is accessible."""

    admin = create_admin(access_token)
    response = client.post(
        url="/api/admin/token",
        data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()
    delete_admin(access_token, admin["username"])


def test_update_admin(access_token):
    """Test that the admin update route is accessible."""

    admin = create_admin(access_token)
    password = strong_password("TestAdminupdate")
    response = client.put(
        url=f"/api/admin/{admin['username']}",
        json={
            "password": password,
            "is_sudo": False,
            "is_disabled": True,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == admin["username"]
    assert response.json()["is_sudo"] is False
    assert response.json()["is_disabled"] is True
    delete_admin(access_token, admin["username"])


def test_get_admins(access_token):
    """Test that the admins get route is accessible."""

    admin = create_admin(access_token)
    response = client.get(
        url="/api/admins",
        params={"sort": "-created_at"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "admins" in response_data
    assert "total" in response_data
    assert "active" in response_data
    assert "disabled" in response_data
    assert admin["username"] in [record["username"] for record in response_data["admins"]]
    delete_admin(access_token, admin["username"])


def test_disable_admin(access_token):
    """Test that the admin disable route is accessible."""

    admin = create_admin(access_token)
    password = admin["password"]
    disable_response = client.put(
        url=f"/api/admin/{admin['username']}",
        json={"password": password, "is_sudo": False, "is_disabled": True},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert disable_response.status_code == status.HTTP_200_OK

    response = client.post(
        url="/api/admin/token",
        data={"username": admin["username"], "password": password, "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "your account has been disabled"
    delete_admin(access_token, admin["username"])


def test_admin_delete_all_users_endpoint(access_token):
    """Test deleting all users belonging to an admin."""

    admin = create_admin(access_token)
    admin_username = admin["username"]

    created_users = []
    for idx in range(2):
        user_name = unique_name(f"{admin_username}_user_{idx}")
        user_response = client.post(
            "/api/user",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "username": user_name,
                "proxy_settings": {},
                "data_limit": 1024,
                "data_limit_reset_strategy": "no_reset",
                "status": "active",
            },
        )
        assert user_response.status_code == status.HTTP_201_CREATED
        created_users.append(user_name)

        set_user_owner(access_token, user_name, admin_username)

    response = client.delete(
        url=f"/api/admin/{admin_username}/users",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert str(len(created_users)) in response.json()["detail"]

    for username in created_users:
        user_check = client.get(
            "/api/users",
            params={"username": username},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert user_check.status_code == status.HTTP_200_OK
        assert user_check.json()["users"] == []

    cleanup = client.delete(
        url=f"/api/admin/{admin_username}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert cleanup.status_code == status.HTTP_204_NO_CONTENT


def test_admin_disable_all_active_users_endpoint(access_token):
    """Test disabling only active users belonging to an admin."""
    admin = create_admin(access_token)
    admin_username = admin["username"]

    active_user = create_user(
        access_token,
        payload={"username": unique_name(f"{admin_username}_active"), "status": "active"},
    )
    disabled_user = create_user(
        access_token,
        payload={"username": unique_name(f"{admin_username}_disabled"), "status": "disabled"},
    )

    try:
        set_user_owner(access_token, active_user["username"], admin_username)
        set_user_owner(access_token, disabled_user["username"], admin_username)

        response = client.post(
            url=f"/api/admin/{admin_username}/users/disable",
            headers=auth_headers(access_token),
        )
        assert response.status_code == status.HTTP_200_OK

        active_user_response = client.get(f"/api/user/{active_user['username']}", headers=auth_headers(access_token))
        disabled_user_response = client.get(f"/api/user/{disabled_user['username']}", headers=auth_headers(access_token))

        assert active_user_response.status_code == status.HTTP_200_OK
        assert disabled_user_response.status_code == status.HTTP_200_OK
        assert active_user_response.json()["status"] == "disabled"
        assert disabled_user_response.json()["status"] == "disabled"
    finally:
        delete_user(access_token, active_user["username"])
        delete_user(access_token, disabled_user["username"])
        delete_admin(access_token, admin_username)


def test_admin_activate_all_disabled_users_endpoint(access_token):
    """Test activating only disabled users belonging to an admin."""
    admin = create_admin(access_token)
    admin_username = admin["username"]

    disabled_user = create_user(
        access_token,
        payload={"username": unique_name(f"{admin_username}_disabled"), "status": "disabled"},
    )
    active_user = create_user(
        access_token,
        payload={"username": unique_name(f"{admin_username}_active"), "status": "active"},
    )

    try:
        set_user_owner(access_token, disabled_user["username"], admin_username)
        set_user_owner(access_token, active_user["username"], admin_username)

        response = client.post(
            url=f"/api/admin/{admin_username}/users/activate",
            headers=auth_headers(access_token),
        )
        assert response.status_code == status.HTTP_200_OK

        disabled_user_response = client.get(
            f"/api/user/{disabled_user['username']}", headers=auth_headers(access_token)
        )
        active_user_response = client.get(
            f"/api/user/{active_user['username']}", headers=auth_headers(access_token)
        )

        assert disabled_user_response.status_code == status.HTTP_200_OK
        assert active_user_response.status_code == status.HTTP_200_OK
        assert disabled_user_response.json()["status"] == "active"
        assert active_user_response.json()["status"] == "active"
    finally:
        delete_user(access_token, disabled_user["username"])
        delete_user(access_token, active_user["username"])
        delete_admin(access_token, admin_username)


def test_admin_delete(access_token):
    """Test that the admin delete route is accessible."""

    admin = create_admin(access_token)
    response = client.delete(
        url=f"/api/admin/{admin['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_admin_usage_returns_stats_for_admin(access_token):
    admin = create_admin(access_token)
    login_response = client.post(
        url="/api/admin/token",
        data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
    )
    assert login_response.status_code == status.HTTP_200_OK
    admin_token = login_response.json()["access_token"]

    user = create_user(admin_token, payload={"username": unique_name("admin_usage_user")})
    now = datetime.now(timezone.utc)
    usages = [
        NodeUserUsage(user_id=user["id"], node_id=None, created_at=now - timedelta(hours=2), used_traffic=123),
        NodeUserUsage(user_id=user["id"], node_id=None, created_at=now - timedelta(hours=1), used_traffic=456),
    ]

    async with TestSession() as session:
        session.add_all(usages)
        await session.commit()

    response = client.get(
        f"/api/admin/{admin['username']}/usage",
        headers=auth_headers(admin_token),
        params={"period": "hour"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["period"] == "hour"
    assert "-1" in data["stats"]
    total = sum(item["total_traffic"] for item in data["stats"]["-1"])
    assert total == 579

    delete_user(admin_token, user["username"])
    delete_admin(access_token, admin["username"])


@pytest.mark.asyncio
async def test_admin_usage_forbidden_for_other_admin(access_token):
    admin_a = create_admin(access_token)
    admin_b = create_admin(access_token)
    login_response = client.post(
        url="/api/admin/token",
        data={"username": admin_a["username"], "password": admin_a["password"], "grant_type": "password"},
    )
    assert login_response.status_code == status.HTTP_200_OK
    admin_a_token = login_response.json()["access_token"]

    response = client.get(
        f"/api/admin/{admin_b['username']}/usage",
        headers=auth_headers(admin_a_token),
        params={"period": "hour"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    delete_admin(access_token, admin_a["username"])
    delete_admin(access_token, admin_b["username"])


# Tests for /api/admins/simple endpoint

def test_get_admins_simple_basic(access_token):
    """Test that admins/simple returns correct minimal data structure."""
    created_admins = []
    try:
        # Create 2 admins
        admin1 = create_admin(access_token, username=unique_name("admin_1"))
        admin2 = create_admin(access_token, username=unique_name("admin_2"))
        created_admins = [admin1["username"], admin2["username"]]

        # Execute
        response = client.get(
            "/api/admins/simple",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "admins" in data
        assert "total" in data

        # Check that each admin has only id and username
        for admin in data["admins"]:
            assert set(admin.keys()) == {"id", "username"}

        # Check created admins are present
        response_usernames = [a["username"] for a in data["admins"]]
        for username in created_admins:
            assert username in response_usernames
    finally:
        for username in created_admins:
            delete_admin(access_token, username)


def test_get_admins_simple_search(access_token):
    """Test case-insensitive search by username."""
    created_admins = []
    try:
        # Create 3 admins with specific names
        admin1 = create_admin(access_token, username="admin_alpha_search")
        admin2 = create_admin(access_token, username="admin_beta_search")
        admin3 = create_admin(access_token, username="other_admin_search")
        created_admins = [admin1["username"], admin2["username"], admin3["username"]]

        # Execute search for "alpha"
        response = client.get(
            "/api/admins/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "alpha"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["admins"]) >= 1
        assert any(a["username"] == "admin_alpha_search" for a in data["admins"])
    finally:
        for username in created_admins:
            delete_admin(access_token, username)


def test_get_admins_simple_sort_ascending(access_token):
    """Test ascending sort by username."""
    created_admins = []
    try:
        # Create 3 admins with specific names for ordering
        admin1 = create_admin(access_token, username="admin_c_sort")
        admin2 = create_admin(access_token, username="admin_a_sort")
        admin3 = create_admin(access_token, username="admin_b_sort")
        created_admins = [admin1["username"], admin2["username"], admin3["username"]]

        # Execute with ascending sort
        response = client.get(
            "/api/admins/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "username"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Find our created admins in the response
        our_admins = [a for a in data["admins"] if a["username"] in created_admins]
        our_usernames = [a["username"] for a in our_admins]
        assert our_usernames == sorted(created_admins)
    finally:
        for username in created_admins:
            delete_admin(access_token, username)


def test_get_admins_simple_sort_descending(access_token):
    """Test descending sort by username."""
    created_admins = []
    try:
        # Create 3 admins with specific names for ordering
        admin1 = create_admin(access_token, username="admin_a_desc")
        admin2 = create_admin(access_token, username="admin_b_desc")
        admin3 = create_admin(access_token, username="admin_c_desc")
        created_admins = [admin1["username"], admin2["username"], admin3["username"]]

        # Execute with descending sort
        response = client.get(
            "/api/admins/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "-username"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Find our created admins in the response
        our_admins = [a for a in data["admins"] if a["username"] in created_admins]
        our_usernames = [a["username"] for a in our_admins]
        assert our_usernames == sorted(created_admins, reverse=True)
    finally:
        for username in created_admins:
            delete_admin(access_token, username)


def test_get_admins_simple_pagination(access_token):
    """Test pagination with offset and limit."""
    created_admins = []
    try:
        # Create 5 admins
        for i in range(5):
            admin = create_admin(access_token, username=unique_name(f"admin_pag_{i}"))
            created_admins.append(admin["username"])

        # Execute first request
        response1 = client.get(
            "/api/admins/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 0, "limit": 2},
        )

        # Execute second request
        response2 = client.get(
            "/api/admins/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 2, "limit": 2},
        )

        # Assert
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
        data1 = response1.json()
        data2 = response2.json()

        assert len(data1["admins"]) == 2
        assert len(data2["admins"]) == 2

        # Check no overlap
        usernames1 = {a["username"] for a in data1["admins"]}
        usernames2 = {a["username"] for a in data2["admins"]}
        assert len(usernames1 & usernames2) == 0
    finally:
        for username in created_admins:
            delete_admin(access_token, username)


def test_get_admins_simple_skip_pagination(access_token):
    """Test all=true parameter returns all records."""
    created_admins = []
    try:
        # Create 8 admins
        for i in range(8):
            admin = create_admin(access_token, username=unique_name(f"admin_all_{i}"))
            created_admins.append(admin["username"])

        # Execute with all=true
        response = client.get(
            "/api/admins/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"all": "true"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "admins" in data
        assert "total" in data
        assert data["total"] >= 8
    finally:
        for username in created_admins:
            delete_admin(access_token, username)


def test_get_admins_simple_requires_sudo(access_token):
    """Test that non-sudo admin cannot access admins/simple."""
    non_sudo_admin = create_admin(access_token, is_sudo=False)
    try:
        # Login as non-sudo admin
        login_response = client.post(
            url="/api/admin/token",
            data={
                "username": non_sudo_admin["username"],
                "password": non_sudo_admin["password"],
                "grant_type": "password",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        non_sudo_token = login_response.json()["access_token"]

        # Try to access admins/simple
        response = client.get(
            "/api/admins/simple",
            headers={"Authorization": f"Bearer {non_sudo_token}"},
        )

        # Assert 403 Forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, non_sudo_admin["username"])


def test_get_admins_simple_empty_search(access_token):
    """Test search with no matching results."""
    created_admins = []
    try:
        # Create 1 admin
        admin = create_admin(access_token, username="known_admin_search")
        created_admins = [admin["username"]]

        # Execute search for non-existent admin
        response = client.get(
            "/api/admins/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "nonexistent_xyz"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert len(data["admins"]) == 0
    finally:
        for username in created_admins:
            delete_admin(access_token, username)


def test_get_admins_simple_invalid_sort(access_token):
    """Test error handling for invalid sort parameter."""
    # Execute with invalid sort
    response = client.get(
        "/api/admins/simple",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"sort": "invalid_field"},
    )

    # Assert
    assert response.status_code == status.HTTP_400_BAD_REQUEST

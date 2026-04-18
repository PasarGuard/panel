import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status
from sqlalchemy import select

from app.db.crud.admin import get_admin_by_telegram_id
from app.db.models import Admin, NodeUserUsage
from app.models.settings import RunMethod, Telegram
from app.routers.authentication import validate_mini_app_admin
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_admin as _create_admin,
    create_user,
    delete_admin,
    delete_user,
    strong_password,
    unique_name,
)


def _admin_slug(value: str, max_length: int, default: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug[:max_length] or default


def admin_username(label: str = "admin") -> str:
    current_test = os.environ.get("PYTEST_CURRENT_TEST", "tests/api/test_admin.py::test_admin")
    test_name = current_test.split("::")[-1].split(" ")[0].removeprefix("test_")
    return unique_name(f"{_admin_slug(test_name, 12, 'test')}_{_admin_slug(label, 12, 'admin')}")


def create_admin(
    access_token: str, *, username: str | None = None, password: str | None = None, is_sudo: bool = False
) -> dict:
    return _create_admin(
        access_token,
        username=username or admin_username("admin"),
        password=password,
        is_sudo=is_sudo,
    )


def set_admin_sudo(username: str, is_sudo: bool) -> None:
    async def _set_flag():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.username == username))
            db_admin = result.scalar_one()
            db_admin.is_sudo = is_sudo
            await session.commit()

    asyncio.run(_set_flag())


def set_admin_used_traffic(username: str, used_traffic: int) -> None:
    async def _set_usage():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.username == username))
            db_admin = result.scalar_one()
            db_admin.used_traffic = used_traffic
            await session.commit()

    asyncio.run(_set_usage())


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

    username = admin_username("create")
    password = strong_password("TestAdmincreate")
    admin = create_admin(access_token, username=username, password=password)
    assert admin["username"] == username
    assert admin["is_sudo"] is False
    delete_admin(access_token, username)


def test_admin_create_sudo_forbidden_via_api(access_token):
    """Creating sudo admin via API should be forbidden."""
    username = admin_username("forbidden")
    password = strong_password("ForbiddenSudo")

    response = client.post(
        url="/api/admin",
        json={"username": username, "password": password, "is_sudo": True},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_admin_create_with_note(access_token):
    """Test that admin note can be set during creation."""

    username = admin_username("note")
    password = strong_password("TestAdminNote")
    note = "created via api"

    response = client.post(
        url="/api/admin",
        json={"username": username, "password": password, "is_sudo": False, "note": note},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["username"] == username
    assert response.json()["note"] == note

    delete_admin(access_token, username)


def test_admin_create_duplicate_telegram_id_conflict(access_token):
    telegram_id = 9988776655
    admin_a = create_admin(access_token)
    admin_b_username = admin_username("tgdup")
    admin_b_password = strong_password("TestAdminDup")
    try:
        response_a = client.put(
            url=f"/api/admin/{admin_a['username']}",
            json={"is_sudo": False, "telegram_id": telegram_id},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response_a.status_code == status.HTTP_200_OK

        response_b = client.post(
            url="/api/admin",
            json={
                "username": admin_b_username,
                "password": admin_b_password,
                "is_sudo": False,
                "telegram_id": telegram_id,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response_b.status_code == status.HTTP_409_CONFLICT
        assert response_b.json()["detail"] == "Telegram ID is already assigned to another admin."
    finally:
        delete_admin(access_token, admin_a["username"])


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


def test_update_admin_note(access_token):
    """Test updating admin note via modify route."""

    admin = create_admin(access_token)
    note = "updated admin note"

    response = client.put(
        url=f"/api/admin/{admin['username']}",
        json={"is_sudo": False, "note": note},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == admin["username"]
    assert response.json()["note"] == note

    delete_admin(access_token, admin["username"])


def test_update_admin_duplicate_telegram_id_conflict(access_token):
    telegram_id = 8877665544
    admin_a = create_admin(access_token)
    admin_b = create_admin(access_token)
    try:
        first_update = client.put(
            url=f"/api/admin/{admin_a['username']}",
            json={"is_sudo": False, "telegram_id": telegram_id},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert first_update.status_code == status.HTTP_200_OK

        second_update = client.put(
            url=f"/api/admin/{admin_b['username']}",
            json={"is_sudo": False, "telegram_id": telegram_id},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert second_update.status_code == status.HTTP_409_CONFLICT
        assert second_update.json()["detail"] == "Telegram ID is already assigned to another admin."
    finally:
        delete_admin(access_token, admin_a["username"])
        delete_admin(access_token, admin_b["username"])


def test_promote_admin_to_sudo_forbidden_via_api(access_token):
    """Promoting non-sudo admin to sudo via API should be forbidden."""
    admin = create_admin(access_token, is_sudo=False)
    try:
        response = client.put(
            url=f"/api/admin/{admin['username']}",
            json={
                "is_sudo": True,
                "is_disabled": False,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, admin["username"])


def test_sudo_admin_can_modify_self(access_token):
    """A sudo admin can edit their own account."""
    sudo_admin = create_admin(access_token)
    set_admin_sudo(sudo_admin["username"], True)
    try:
        login_response = client.post(
            url="/api/admin/token",
            data={
                "username": sudo_admin["username"],
                "password": sudo_admin["password"],
                "grant_type": "password",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        sudo_token = login_response.json()["access_token"]

        response = client.put(
            url=f"/api/admin/{sudo_admin['username']}",
            json={
                "is_sudo": True,
                "is_disabled": False,
                "note": "self-updated",
            },
            headers={"Authorization": f"Bearer {sudo_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["username"] == sudo_admin["username"]
        assert response.json()["note"] == "self-updated"
    finally:
        set_admin_sudo(sudo_admin["username"], False)
        delete_admin(access_token, sudo_admin["username"])


def test_sudo_admin_cannot_disable_self(access_token):
    """A sudo admin cannot disable their own account."""
    sudo_admin = create_admin(access_token)
    set_admin_sudo(sudo_admin["username"], True)
    try:
        login_response = client.post(
            url="/api/admin/token",
            data={
                "username": sudo_admin["username"],
                "password": sudo_admin["password"],
                "grant_type": "password",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        sudo_token = login_response.json()["access_token"]

        response = client.put(
            url=f"/api/admin/{sudo_admin['username']}",
            json={
                "is_sudo": True,
                "is_disabled": True,
            },
            headers={"Authorization": f"Bearer {sudo_token}"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"] == "You're not allowed to disable your own account."
    finally:
        set_admin_sudo(sudo_admin["username"], False)
        delete_admin(access_token, sudo_admin["username"])


def test_sudo_admin_cannot_modify_other_sudo_admin(access_token):
    """A sudo admin cannot edit another sudo admin account."""
    sudo_admin_a = create_admin(access_token)
    sudo_admin_b = create_admin(access_token)
    set_admin_sudo(sudo_admin_a["username"], True)
    set_admin_sudo(sudo_admin_b["username"], True)
    try:
        login_response = client.post(
            url="/api/admin/token",
            data={
                "username": sudo_admin_a["username"],
                "password": sudo_admin_a["password"],
                "grant_type": "password",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        sudo_a_token = login_response.json()["access_token"]

        response = client.put(
            url=f"/api/admin/{sudo_admin_b['username']}",
            json={
                "is_sudo": True,
                "is_disabled": False,
                "note": "should-fail",
            },
            headers={"Authorization": f"Bearer {sudo_a_token}"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        set_admin_sudo(sudo_admin_a["username"], False)
        set_admin_sudo(sudo_admin_b["username"], False)
        delete_admin(access_token, sudo_admin_a["username"])
        delete_admin(access_token, sudo_admin_b["username"])


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


def test_get_admins_returns_admin_note(access_token):
    """Test that /api/admins compact response includes admin note."""

    username = admin_username("list_note")
    password = strong_password("TestAdminNote")
    note = "visible in admins list"

    create_response = client.post(
        url="/api/admin",
        json={"username": username, "password": password, "is_sudo": False, "note": note},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    try:
        response = client.get(
            url="/api/admins",
            params={"username": username},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        rows = response.json()["admins"]
        created_admin_row = next((row for row in rows if row["username"] == username), None)
        assert created_admin_row is not None
        assert created_admin_row["note"] == note
    finally:
        delete_admin(access_token, username)


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

        ownership_response = client.put(
            f"/api/user/{user_name}/set_owner",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"admin_username": admin_username},
        )
        assert ownership_response.status_code == status.HTTP_200_OK
        assert ownership_response.json()["admin"]["username"] == admin_username

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
    delete_admin(access_token, admin_username)


def test_admin_delete(access_token):
    """Test that the admin delete route is accessible."""

    admin = create_admin(access_token)
    response = client.delete(
        url=f"/api/admin/{admin['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_reset_admin_usage_keeps_lifetime_traffic(access_token):
    admin = create_admin(access_token)
    try:
        set_admin_used_traffic(admin["username"], 12345)

        reset_response = client.post(
            url=f"/api/admin/{admin['username']}/reset",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert reset_response.status_code == status.HTTP_200_OK
        reset_data = reset_response.json()
        assert reset_data["used_traffic"] == 0
        assert reset_data["lifetime_used_traffic"] == 12345

        admins_response = client.get(
            url="/api/admins",
            params={"username": admin["username"]},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert admins_response.status_code == status.HTTP_200_OK
        rows = admins_response.json()["admins"]
        target = next((row for row in rows if row["username"] == admin["username"]), None)
        assert target is not None
        assert target["used_traffic"] == 0
        assert target["lifetime_used_traffic"] == 12345
    finally:
        delete_admin(access_token, admin["username"])


@pytest.mark.asyncio
async def test_admin_usage_returns_stats_for_admin(access_token):
    try:
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
    finally:
        delete_user(admin_token, user["username"])
        delete_admin(access_token, admin["username"])
        async with TestSession() as session:
            for u in usages:
                await session.delete(u)
                await session.commit()


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


@pytest.mark.asyncio
async def test_get_admin_by_telegram_id_handles_duplicate_rows(access_token):
    telegram_id = 7766554433
    async with TestSession() as session:
        admin_a = Admin(username=admin_username("tg_read_a"), hashed_password="secret", telegram_id=telegram_id)
        admin_b = Admin(username=admin_username("tg_read_b"), hashed_password="secret", telegram_id=telegram_id)
        session.add_all([admin_a, admin_b])
        await session.commit()

        loaded = await get_admin_by_telegram_id(session, telegram_id, load_users=False, load_usage_logs=False)
        assert loaded is not None
        assert loaded.telegram_id == telegram_id
        assert loaded.username == admin_a.username
    delete_admin(access_token, admin_a.username)
    delete_admin(access_token, admin_b.username)


@pytest.mark.asyncio
async def test_validate_mini_app_admin_duplicate_telegram_id_conflict(access_token, monkeypatch: pytest.MonkeyPatch):
    telegram_id = 6655443322
    admin_a = Admin(username=admin_username("mini_dup_a"), hashed_password="secret", telegram_id=telegram_id)
    admin_b = Admin(username=admin_username("mini_dup_b"), hashed_password="secret", telegram_id=telegram_id)
    async with TestSession() as session:
        session.add_all(
            [
                admin_a,
                admin_b,
            ]
        )
        await session.commit()

        async def fake_telegram_settings():
            return Telegram(
                enable=True,
                mini_app_login=True,
                method=RunMethod.LONGPOLLING,
                token="12345678:" + ("A" * 35),
            )

        monkeypatch.setattr("app.routers.authentication.telegram_settings", fake_telegram_settings)
        monkeypatch.setattr(
            "app.routers.authentication.safe_parse_webapp_init_data",
            lambda token, init_data: SimpleNamespace(user=SimpleNamespace(id=telegram_id)),
        )

        with pytest.raises(HTTPException) as exc_info:
            await validate_mini_app_admin(session, "signed-init-data")

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert exc_info.value.detail == "Telegram ID is assigned to multiple admins. Please contact support."

    delete_admin(access_token, admin_a.username)
    delete_admin(access_token, admin_b.username)


# Tests for /api/admins/simple endpoint


def test_get_admins_simple_basic(access_token):
    """Test that admins/simple returns correct minimal data structure."""
    created_admins = []
    try:
        # Create 2 admins
        admin1 = create_admin(access_token, username=admin_username("admin_1"))
        admin2 = create_admin(access_token, username=admin_username("admin_2"))
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
        admin1 = create_admin(access_token, username=admin_username("alpha_search"))
        admin2 = create_admin(access_token, username=admin_username("beta_search"))
        admin3 = create_admin(access_token, username=admin_username("other_search"))
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
        assert any(a["username"] == admin1["username"] for a in data["admins"])
    finally:
        for username in created_admins:
            delete_admin(access_token, username)


def test_get_admins_simple_sort_ascending(access_token):
    """Test ascending sort by username."""
    created_admins = []
    try:
        # Create 3 admins with specific names for ordering
        admin1 = create_admin(access_token, username=admin_username("c_sort"))
        admin2 = create_admin(access_token, username=admin_username("a_sort"))
        admin3 = create_admin(access_token, username=admin_username("b_sort"))
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
        admin1 = create_admin(access_token, username=admin_username("a_desc"))
        admin2 = create_admin(access_token, username=admin_username("b_desc"))
        admin3 = create_admin(access_token, username=admin_username("c_desc"))
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
            admin = create_admin(access_token, username=admin_username(f"pag_{i}"))
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
            admin = create_admin(access_token, username=admin_username(f"all_{i}"))
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
        admin = create_admin(access_token, username=admin_username("known_search"))
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

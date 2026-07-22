import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status
from sqlalchemy import select

from app.db.crud.admin import get_admin_by_telegram_id
from app.db.models import Admin, AdminUsageLogs, NodeUserUsage
from app.models.admin import hash_password
from app.models.settings import RunMethod, Telegram
from app.routers.authentication import validate_mini_app_admin
from app.utils.jwt import get_admin_payload
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
    access_token: str, *, username: str | None = None, password: str | None = None, role_id: int = 3
) -> dict:
    return _create_admin(
        access_token,
        username=username or admin_username("admin"),
        password=password,
        role_id=role_id,
    )


def set_admin_role(username: str, role_id: int) -> None:
    """Set admin role by role_id (2=administrator, 3=operator)."""

    async def _set_flag():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.username == username))
            db_admin = result.scalar_one()
            db_admin.role_id = role_id
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


def create_owner_admin_row() -> dict:
    username = admin_username("owner")
    password = strong_password("OwnerAdmin")

    async def _create_owner():
        async with TestSession() as session:
            db_admin = Admin(username=username, hashed_password=await hash_password(password), role_id=1)
            session.add(db_admin)
            await session.commit()
            return db_admin.id

    return {"id": asyncio.run(_create_owner()), "username": username, "password": password}


def delete_admin_row(username: str) -> None:
    async def _delete():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.username == username))
            db_admin = result.scalar_one_or_none()
            if db_admin is not None:
                await session.delete(db_admin)
                await session.commit()

    asyncio.run(_delete())


def test_admin_login():
    """Test that the admin login route is accessible."""

    response = client.post(
        url="/api/admin/token",
        data={"username": "testadmin", "password": "testadmin", "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()
    return response.json()["access_token"]


def test_admin_token_contains_admin_id_claim(access_token):
    admin = create_admin(access_token)
    try:
        response = client.post(
            url="/api/admin/token",
            data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
        )
        assert response.status_code == status.HTTP_200_OK
        token = response.json()["access_token"]
        payload = asyncio.run(get_admin_payload(token))
        assert payload is not None
        assert payload["admin_id"] == admin["id"]
        assert payload["username"] == admin["username"]
    finally:
        delete_admin(access_token, admin["username"])


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


def test_get_admin_uses_aggregate_metrics_without_loading_relationships(access_token, monkeypatch: pytest.MonkeyPatch):
    admin = create_admin(access_token)
    admin_token_response = client.post(
        url="/api/admin/token",
        data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
    )
    assert admin_token_response.status_code == status.HTTP_200_OK
    admin_token = admin_token_response.json()["access_token"]

    user = create_user(admin_token, payload={"username": unique_name("admin_metric_user")})

    async def _seed_admin_usage():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.username == admin["username"]))
            db_admin = result.scalar_one()
            db_admin.used_traffic = 12345
            session.add(AdminUsageLogs(admin_id=db_admin.id, used_traffic_at_reset=6789))
            await session.commit()

    async def _assert_lightweight_admin_load(_, load_users: bool = True, load_usage_logs: bool = True):
        assert load_users is False
        assert load_usage_logs is False

    try:
        asyncio.run(_seed_admin_usage())
        with monkeypatch.context() as patch_context:
            patch_context.setattr("app.db.crud.admin.load_admin_attrs", _assert_lightweight_admin_load)
            response = client.get(url="/api/admin", headers=auth_headers(admin_token))

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["username"] == admin["username"]
        assert data["total_users"] == 1
        assert data["used_traffic"] == 12345
        assert data["lifetime_used_traffic"] == 19134
    finally:
        delete_user(admin_token, user["username"])
        delete_admin(access_token, admin["username"])


def test_protected_routes_use_lightweight_current_admin(access_token, monkeypatch: pytest.MonkeyPatch):
    admin = create_admin(access_token)
    admin_token_response = client.post(
        url="/api/admin/token",
        data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
    )
    assert admin_token_response.status_code == status.HTTP_200_OK
    admin_token = admin_token_response.json()["access_token"]

    async def _assert_lightweight_admin_load(_, load_users: bool = True, load_usage_logs: bool = True):
        assert load_users is False
        assert load_usage_logs is False

    try:
        with monkeypatch.context() as patch_context:
            patch_context.setattr("app.db.crud.admin.load_admin_attrs", _assert_lightweight_admin_load)
            response = client.get(url="/api/users", headers=auth_headers(admin_token))

        assert response.status_code == status.HTTP_200_OK
    finally:
        delete_admin(access_token, admin["username"])


def test_admin_create(access_token):
    """Test that the admin create route is accessible."""

    username = admin_username("create")
    password = strong_password("TestAdmincreate")
    admin = create_admin(access_token, username=username, password=password)
    assert admin["username"] == username
    # Verify role data is present in create response
    assert admin["role"] is not None
    assert admin["role"]["id"] == 3  # default operator role
    assert admin["role"]["name"] == "operator"
    assert admin["role"]["is_owner"] is False
    delete_admin(access_token, username)


def test_admin_create_owner_forbidden_via_api(access_token):
    """Creating an admin with owner role (role_id=1) via API should be forbidden."""
    username = admin_username("forbidden")
    password = strong_password("ForbiddenOwner")

    response = client.post(
        url="/api/admin",
        json={"username": username, "password": password, "role_id": 1},
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
        json={"username": username, "password": password, "note": note, "role_id": 3},
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
            json={"telegram_id": telegram_id},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response_a.status_code == status.HTTP_200_OK

        response_b = client.post(
            url="/api/admin",
            json={
                "username": admin_b_username,
                "password": admin_b_password,
                "telegram_id": telegram_id,
                "role_id": 3,
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
    """Test that the admin update route is accessible and applies role_id changes."""

    admin = create_admin(access_token)  # role_id=3 (operator)
    password = strong_password("TestAdminupdate")
    response = client.put(
        url=f"/api/admin/{admin['username']}",
        json={
            "password": password,
            "status": "disabled",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == admin["username"]
    assert response.json()["status"] == "disabled"

    # Verify role_id change is applied
    role_change_response = client.put(
        url=f"/api/admin/{admin['username']}",
        json={"role_id": 2},  # promote to administrator
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert role_change_response.status_code == status.HTTP_200_OK
    updated = role_change_response.json()
    assert updated["role"]["id"] == 2
    assert updated["role"]["name"] == "administrator"

    delete_admin(access_token, admin["username"])


def test_admin_limited_status_not_assignable(access_token):
    """Limited admin status is reserved for automatic data-limit enforcement."""
    password = strong_password("TestAdminLimited")
    create_response = client.post(
        url="/api/admin",
        json={"username": admin_username("limited"), "password": password, "role_id": 3, "status": "limited"},
        headers=auth_headers(access_token),
    )
    assert create_response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    admin = create_admin(access_token)
    try:
        update_response = client.put(
            url=f"/api/admin/{admin['username']}",
            json={"status": "limited"},
            headers=auth_headers(access_token),
        )
        assert update_response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    finally:
        delete_admin(access_token, admin["username"])


def test_admin_routes_by_id_and_by_username(access_token):
    admin = create_admin(access_token)
    try:
        by_username_update = client.put(
            url=f"/api/admin/by-username/{admin['username']}",
            json={"note": "by-username note"},
            headers=auth_headers(access_token),
        )
        assert by_username_update.status_code == status.HTTP_200_OK
        assert by_username_update.json()["note"] == "by-username note"

        by_id_update = client.put(
            url=f"/api/admin/by-id/{admin['id']}",
            json={"note": "by-id note"},
            headers=auth_headers(access_token),
        )
        assert by_id_update.status_code == status.HTTP_200_OK
        assert by_id_update.json()["note"] == "by-id note"

        by_id_usage = client.get(
            f"/api/admin/by-id/{admin['id']}/usage",
            headers=auth_headers(access_token),
            params={"period": "hour"},
        )
        assert by_id_usage.status_code == status.HTTP_200_OK

        by_username_reset = client.post(
            f"/api/admin/by-username/{admin['username']}/reset",
            headers=auth_headers(access_token),
        )
        assert by_username_reset.status_code == status.HTTP_200_OK
    finally:
        delete_admin(access_token, admin["username"])


def test_update_admin_note(access_token):
    """Test updating admin note via modify route."""

    admin = create_admin(access_token)
    note = "updated admin note"

    response = client.put(
        url=f"/api/admin/{admin['username']}",
        json={"note": note},
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
            json={"telegram_id": telegram_id},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert first_update.status_code == status.HTTP_200_OK

        second_update = client.put(
            url=f"/api/admin/{admin_b['username']}",
            json={"telegram_id": telegram_id},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert second_update.status_code == status.HTTP_409_CONFLICT
        assert second_update.json()["detail"] == "Telegram ID is already assigned to another admin."
    finally:
        delete_admin(access_token, admin_a["username"])
        delete_admin(access_token, admin_b["username"])


def test_promote_admin_to_owner_forbidden_via_api(access_token):
    """Assigning owner role (role_id=1) to an admin via API should be forbidden."""
    admin = create_admin(access_token)
    try:
        response = client.put(
            url=f"/api/admin/{admin['username']}",
            json={
                "status": "active",
                "role_id": 1,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, admin["username"])


def test_administrator_can_modify_self(access_token):
    """An administrator (role_id=2) can edit their own account."""
    # Create admin with administrator role so they have admins.update permission
    administrator_username = admin_username("admin")
    administrator_password = strong_password("TestAdminPass")
    create_response = client.post(
        url="/api/admin",
        json={"username": administrator_username, "password": administrator_password, "role_id": 2},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    administrator_admin = create_response.json()
    administrator_admin["password"] = administrator_password
    try:
        login_response = client.post(
            url="/api/admin/token",
            data={
                "username": administrator_admin["username"],
                "password": administrator_admin["password"],
                "grant_type": "password",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        administrator_token = login_response.json()["access_token"]

        response = client.put(
            url=f"/api/admin/{administrator_admin['username']}",
            json={
                "status": "active",
                "note": "self-updated",
            },
            headers={"Authorization": f"Bearer {administrator_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["username"] == administrator_admin["username"]
        assert response.json()["note"] == "self-updated"
    finally:
        delete_admin(access_token, administrator_admin["username"])


def test_administrator_cannot_disable_self(access_token):
    """An administrator (role_id=2) cannot disable their own account."""
    administrator_username = admin_username("admin")
    administrator_password = strong_password("TestAdminPass")
    create_response = client.post(
        url="/api/admin",
        json={"username": administrator_username, "password": administrator_password, "role_id": 2},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    administrator_admin = create_response.json()
    administrator_admin["password"] = administrator_password
    try:
        login_response = client.post(
            url="/api/admin/token",
            data={
                "username": administrator_admin["username"],
                "password": administrator_admin["password"],
                "grant_type": "password",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        administrator_token = login_response.json()["access_token"]

        response = client.put(
            url=f"/api/admin/{administrator_admin['username']}",
            json={
                "status": "disabled",
            },
            headers={"Authorization": f"Bearer {administrator_token}"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"] == "You're not allowed to disable your own account."
    finally:
        delete_admin(access_token, administrator_admin["username"])


def test_administrator_can_modify_other_non_owner_admin(access_token):
    """An admin with admins.update can edit another non-owner admin, regardless of role id."""
    admin_a = create_admin(access_token)
    admin_b = create_admin(access_token)
    set_admin_role(admin_a["username"], 2)
    set_admin_role(admin_b["username"], 2)
    try:
        login_response = client.post(
            url="/api/admin/token",
            data={
                "username": admin_a["username"],
                "password": admin_a["password"],
                "grant_type": "password",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        admin_a_token = login_response.json()["access_token"]

        response = client.put(
            url=f"/api/admin/{admin_b['username']}",
            json={
                "status": "active",
                "note": "updated-by-admin",
            },
            headers={"Authorization": f"Bearer {admin_a_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["note"] == "updated-by-admin"
    finally:
        delete_admin(access_token, admin_a["username"])
        delete_admin(access_token, admin_b["username"])


def test_get_admins(access_token):
    """Test that the admins get route is accessible and returns role data."""

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

    # Verify role data is present in the list response
    created_record = next(r for r in response_data["admins"] if r["username"] == admin["username"])
    assert created_record["role"] is not None
    assert "id" in created_record["role"]
    assert "name" in created_record["role"]
    assert "is_owner" in created_record["role"]
    assert created_record["role"]["id"] == 3  # operator role
    assert created_record["role"]["name"] == "operator"

    delete_admin(access_token, admin["username"])


def test_get_admins_returns_admin_note(access_token):
    """Test that /api/admins compact response includes admin note."""

    username = admin_username("list_note")
    password = strong_password("TestAdminNote")
    note = "visible in admins list"

    create_response = client.post(
        url="/api/admin",
        json={"username": username, "password": password, "note": note, "role_id": 3},
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


def test_non_owner_admin_list_hides_owner(access_token):
    owner = create_owner_admin_row()
    administrator = create_admin(access_token, role_id=2)
    try:
        login_response = client.post(
            url="/api/admin/token",
            data={
                "username": administrator["username"],
                "password": administrator["password"],
                "grant_type": "password",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        administrator_token = login_response.json()["access_token"]

        response = client.get(
            "/api/admins",
            params={"username": owner["username"]},
            headers=auth_headers(administrator_token),
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["admins"] == []
        assert response.json()["total"] == 0

        simple_response = client.get(
            "/api/admins/simple",
            params={"search": owner["username"], "all": True},
            headers=auth_headers(administrator_token),
        )
        assert simple_response.status_code == status.HTTP_200_OK
        assert simple_response.json()["admins"] == []
        assert simple_response.json()["total"] == 0
    finally:
        delete_admin(access_token, administrator["username"])
        delete_admin_row(owner["username"])


def test_non_owner_admin_cannot_target_owner_with_admin_permissions(access_token):
    owner = create_owner_admin_row()
    administrator = create_admin(access_token, role_id=2)
    try:
        login_response = client.post(
            url="/api/admin/token",
            data={
                "username": administrator["username"],
                "password": administrator["password"],
                "grant_type": "password",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        administrator_token = login_response.json()["access_token"]
        headers = auth_headers(administrator_token)

        modify_response = client.put(
            f"/api/admin/by-id/{owner['id']}",
            json={"note": "should not update"},
            headers=headers,
        )
        assert modify_response.status_code == status.HTTP_403_FORBIDDEN

        usage_response = client.get(
            f"/api/admin/by-id/{owner['id']}/usage",
            params={"period": "hour"},
            headers=headers,
        )
        assert usage_response.status_code == status.HTTP_403_FORBIDDEN

        bulk_delete_response = client.post(
            "/api/admins/bulk/delete",
            json={"ids": [owner["id"]]},
            headers=headers,
        )
        assert bulk_delete_response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, administrator["username"])
        delete_admin_row(owner["username"])


def test_disable_admin(access_token):
    """Test that the admin disable route is accessible."""

    admin = create_admin(access_token)
    password = admin["password"]
    disable_response = client.put(
        url=f"/api/admin/{admin['username']}",
        json={"password": password, "status": "disabled"},
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
        admin_a = Admin(
            username=admin_username("tg_read_a"), hashed_password="secret", telegram_id=telegram_id, role_id=3
        )
        admin_b = Admin(
            username=admin_username("tg_read_b"), hashed_password="secret", telegram_id=telegram_id, role_id=3
        )
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
    admin_a = Admin(username=admin_username("mini_dup_a"), hashed_password="secret", telegram_id=telegram_id, role_id=3)
    admin_b = Admin(username=admin_username("mini_dup_b"), hashed_password="secret", telegram_id=telegram_id, role_id=3)
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


def test_get_admins_simple_requires_permission(access_token):
    """Test that operator admin cannot access admins/simple."""
    non_administrator_admin = create_admin(access_token)
    try:
        # Login as operator admin
        login_response = client.post(
            url="/api/admin/token",
            data={
                "username": non_administrator_admin["username"],
                "password": non_administrator_admin["password"],
                "grant_type": "password",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        non_administrator_token = login_response.json()["access_token"]

        # Try to access admins/simple
        response = client.get(
            "/api/admins/simple",
            headers={"Authorization": f"Bearer {non_administrator_token}"},
        )

        # Assert 403 Forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, non_administrator_admin["username"])


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


def test_create_admin_with_custom_role(access_token):
    """Create a custom role (id > 3), assign it to a new admin, verify the admin has that role."""
    # Step 1: create a custom role via the owner token
    role_name = unique_name("custom_role")
    role_response = client.post(
        "/api/admin-role",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "name": role_name,
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
        },
    )
    assert role_response.status_code == status.HTTP_201_CREATED
    role = role_response.json()
    assert role["id"] > 3  # must not be one of the 3 built-in roles

    # Step 2: create an admin assigned to the custom role
    username = admin_username("custom_role_admin")
    password = strong_password("CustomRoleAdmin")
    try:
        admin_response = client.post(
            "/api/admin",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"username": username, "password": password, "role_id": role["id"]},
        )
        assert admin_response.status_code == status.HTTP_201_CREATED
        admin_data = admin_response.json()
        assert admin_data["username"] == username
        assert admin_data["role"]["id"] == role["id"]
        assert admin_data["role"]["name"] == role_name
        assert admin_data["role"]["is_owner"] is False

        # Step 3: verify the admin can log in
        login_response = client.post(
            "/api/admin/token",
            data={"username": username, "password": password, "grant_type": "password"},
        )
        assert login_response.status_code == status.HTTP_200_OK
    finally:
        delete_admin(access_token, username)
        client.delete(f"/api/admin-role/{role['id']}", headers={"Authorization": f"Bearer {access_token}"})


def test_custom_role_with_admin_update_can_modify_administrator(access_token):
    """A custom role with admins.update can modify role_id=2 admins."""
    role_response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("admin_update_role"),
            "permissions": {"admins": {"update": True}},
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
        },
    )
    assert role_response.status_code == status.HTTP_201_CREATED
    role = role_response.json()

    actor = create_admin(access_token, role_id=role["id"])
    target = create_admin(access_token, role_id=2)
    try:
        actor_token = _login(actor["username"], actor["password"])

        response = client.put(
            f"/api/admin/{target['username']}",
            json={"note": "custom-role-update"},
            headers=auth_headers(actor_token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["note"] == "custom-role-update"
    finally:
        delete_admin(access_token, actor["username"])
        delete_admin(access_token, target["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


# ---------------------------------------------------------------------------
# Admin data_limit, status, and limited-access tests
# ---------------------------------------------------------------------------


def _set_admin_traffic(username: str, used_traffic: int, data_limit: int | None = None) -> None:
    """Directly set used_traffic and optionally data_limit on an admin."""

    async def _set():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.username == username))
            db_admin = result.scalar_one()
            db_admin.used_traffic = used_traffic
            if data_limit is not None:
                db_admin.data_limit = data_limit
            await session.commit()

    asyncio.run(_set())


def _set_admin_status(username: str, status_value: str) -> None:
    """Directly set admin status in DB."""

    async def _set():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.username == username))
            db_admin = result.scalar_one()
            db_admin.status = status_value
            await session.commit()

    asyncio.run(_set())


def _login(username: str, password: str) -> str:
    response = client.post(
        "/api/admin/token",
        data={"username": username, "password": password, "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access_token"]


def test_admin_data_limit_set_and_returned(access_token):
    """Setting data_limit on an admin is persisted and returned in the response."""
    admin = create_admin(access_token)
    try:
        response = client.put(
            f"/api/admin/{admin['username']}",
            json={"data_limit": 1073741824},  # 1 GiB
            headers=auth_headers(access_token),
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data_limit"] == 1073741824
        assert data["status"] == "active"
    finally:
        delete_admin(access_token, admin["username"])


def test_admin_data_limit_zero_means_unlimited(access_token):
    """Setting data_limit=0 clears the limit (treated as unlimited)."""
    admin = create_admin(access_token)
    try:
        # Set a limit first
        client.put(
            f"/api/admin/{admin['username']}",
            json={"data_limit": 1073741824},
            headers=auth_headers(access_token),
        )
        # Clear it with 0
        response = client.put(
            f"/api/admin/{admin['username']}",
            json={"data_limit": 0},
            headers=auth_headers(access_token),
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data_limit"] is None
    finally:
        delete_admin(access_token, admin["username"])


def test_admin_status_defaults_to_active(access_token):
    """Newly created admin has status=active."""
    admin = create_admin(access_token)
    try:
        response = client.get("/api/admins", headers=auth_headers(access_token), params={"username": admin["username"]})
        assert response.status_code == status.HTTP_200_OK
        rows = response.json()["admins"]
        target = next(r for r in rows if r["username"] == admin["username"])
        assert target["status"] == "active"
    finally:
        delete_admin(access_token, admin["username"])


def test_admin_status_becomes_limited_when_traffic_exceeds_limit(access_token):
    """When used_traffic >= data_limit, status flips to limited via update_admin."""
    admin = create_admin(access_token)
    try:
        # Set data_limit=100 bytes, then simulate traffic=100 bytes
        client.put(
            f"/api/admin/{admin['username']}",
            json={"data_limit": 100},
            headers=auth_headers(access_token),
        )
        _set_admin_traffic(admin["username"], used_traffic=100)
        # Trigger status recompute by calling update_admin with any field
        response = client.put(
            f"/api/admin/{admin['username']}",
            json={"data_limit": 100},  # same value, triggers recompute in CRUD
            headers=auth_headers(access_token),
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "limited"
    finally:
        delete_admin(access_token, admin["username"])


def test_admin_status_returns_to_active_after_limit_raised(access_token):
    """Raising data_limit above used_traffic flips status back to active."""
    admin = create_admin(access_token)
    try:
        # Set limit=100, traffic=100 → limited
        client.put(f"/api/admin/{admin['username']}", json={"data_limit": 100}, headers=auth_headers(access_token))
        _set_admin_traffic(admin["username"], used_traffic=100)
        client.put(f"/api/admin/{admin['username']}", json={"data_limit": 100}, headers=auth_headers(access_token))

        # Raise limit → active
        response = client.put(
            f"/api/admin/{admin['username']}",
            json={"data_limit": 1073741824},
            headers=auth_headers(access_token),
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "active"
    finally:
        delete_admin(access_token, admin["username"])


def test_admin_status_returns_to_active_after_reset_usage(access_token):
    """Resetting usage on a limited admin flips status back to active."""
    admin = create_admin(access_token)
    try:
        # Set limit=100, traffic=100 → limited
        client.put(f"/api/admin/{admin['username']}", json={"data_limit": 100}, headers=auth_headers(access_token))
        _set_admin_traffic(admin["username"], used_traffic=100)
        client.put(f"/api/admin/{admin['username']}", json={"data_limit": 100}, headers=auth_headers(access_token))

        # Reset usage → active
        response = client.post(f"/api/admin/{admin['username']}/reset", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "active"
        assert response.json()["used_traffic"] == 0
    finally:
        delete_admin(access_token, admin["username"])


def test_limited_admin_write_blocked_by_default(access_token):
    """A limited admin cannot perform write operations (default: disabled_when_limited=False blocks writes)."""
    admin = create_admin(access_token)
    try:
        # Set limit and exceed it
        client.put(f"/api/admin/{admin['username']}", json={"data_limit": 100}, headers=auth_headers(access_token))
        _set_admin_traffic(admin["username"], used_traffic=100)
        _set_admin_status(admin["username"], "limited")

        token = _login(admin["username"], admin["password"])

        # Write operation should be blocked
        response = client.post(
            "/api/user",
            headers=auth_headers(token),
            json={
                "username": unique_name("limited_user"),
                "proxy_settings": {},
                "data_limit": 0,
                "data_limit_reset_strategy": "no_reset",
                "status": "active",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, admin["username"])


def test_limited_admin_read_allowed_when_disabled_when_limited_false(access_token):
    """A limited admin can still read when disabled_when_limited=False (default)."""
    admin = create_admin(access_token)
    try:
        client.put(f"/api/admin/{admin['username']}", json={"data_limit": 100}, headers=auth_headers(access_token))
        _set_admin_traffic(admin["username"], used_traffic=100)
        _set_admin_status(admin["username"], "limited")

        token = _login(admin["username"], admin["password"])

        # Read operation should be allowed
        response = client.get("/api/users", headers=auth_headers(token))
        assert response.status_code == status.HTTP_200_OK
    finally:
        delete_admin(access_token, admin["username"])


def test_limited_admin_all_blocked_when_disabled_when_limited_true(access_token):
    """A limited admin is fully blocked when disabled_when_limited=True on their role."""
    # Create a custom role with disabled_when_limited=True
    role_response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("limited_role"),
            "permissions": {"users": {"read": True, "create": True}},
            "limits": {},
            "features": {"can_use_reset_strategy": True, "can_use_next_plan": True},
            "access": {},
        },
    )
    assert role_response.status_code == status.HTTP_201_CREATED
    role = role_response.json()

    # Set disabled_when_limited=True directly in DB
    async def _set_role_flag():
        async with TestSession() as session:
            from app.db.models import AdminRole

            result = await session.execute(select(AdminRole).where(AdminRole.id == role["id"]))
            db_role = result.scalar_one()
            db_role.disabled_when_limited = True
            await session.commit()

    asyncio.run(_set_role_flag())

    admin = create_admin(access_token, role_id=role["id"])
    try:
        client.put(f"/api/admin/{admin['username']}", json={"data_limit": 100}, headers=auth_headers(access_token))
        _set_admin_traffic(admin["username"], used_traffic=100)
        _set_admin_status(admin["username"], "limited")

        token = _login(admin["username"], admin["password"])

        # Even read should be blocked
        response = client.get("/api/users", headers=auth_headers(token))
        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, admin["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


def test_admins_list_includes_limited_count(access_token):
    """GET /api/admins response includes a 'limited' count field."""
    admin = create_admin(access_token)
    try:
        _set_admin_status(admin["username"], "limited")
        response = client.get("/api/admins", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "limited" in data
        assert data["limited"] >= 1
    finally:
        delete_admin(access_token, admin["username"])

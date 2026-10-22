"""Per-admin host customization: an admin renames or hides hosts for its own users only."""

import asyncio
from urllib.parse import unquote

from fastapi import status
from sqlalchemy import func, select

from app.db.models import AdminHostOverride
from app.subscription import config_cache
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
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

INBOUND_TAG = "VLESS WebSocket TEST"


def _login(username: str, password: str) -> str:
    response = client.post(
        "/api/admin/token",
        data={"username": username, "password": password, "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access_token"]


def _create_role(access_token: str, permissions: dict, access: dict | None = None) -> dict:
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={"name": unique_name("role_host"), "permissions": permissions, "access": access or {}},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def _create_host(access_token: str, remark: str) -> dict:
    response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={"remark": remark, "address": ["198.51.100.7"], "inbound_tag": INBOUND_TAG, "priority": 1},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def _sub_links(user: dict) -> str:
    config_cache.clear_sub_config_cache()
    response = client.get(f"{user['subscription_url']}/links")
    assert response.status_code == status.HTTP_200_OK, response.text
    return unquote(response.text)


def _override_count(host_id: int) -> int:
    async def _count() -> int:
        async with TestSession() as session:
            stmt = select(func.count()).select_from(AdminHostOverride).where(AdminHostOverride.host_id == host_id)
            return (await session.execute(stmt)).scalar_one()

    return asyncio.run(_count())


CUSTOMIZE_PERMISSIONS = {"hosts": {"customize": True}, "users": {"create": True, "read": {"scope": 1}}}


def test_admin_customizes_hosts_for_own_users_only(access_token):
    core = create_core(access_token)
    group = create_group(access_token, inbound_tags=[INBOUND_TAG])
    role = _create_role(access_token, CUSTOMIZE_PERMISSIONS)
    admin = create_admin(access_token, role_id=role["id"])
    admin_token = _login(admin["username"], admin["password"])
    remark = unique_name("shared")
    host = _create_host(access_token, remark)
    owner_user = create_user(access_token, group_ids=[group["id"]])
    admin_user = create_user(admin_token, group_ids=[group["id"]])
    try:
        response = client.get("/api/hosts/customizations", headers=auth_headers(admin_token))
        assert response.status_code == status.HTTP_200_OK, response.text
        listed = {item["host_id"]: item for item in response.json()}
        assert listed[host["id"]] == {
            "host_id": host["id"],
            "remark": remark,
            "inbound_tag": INBOUND_TAG,
            "host_disabled": False,
            "custom_remark": None,
            "is_disabled": False,
        }

        # Renaming needs no access to the host config, and never changes it
        assert client.get(f"/api/host/{host['id']}", headers=auth_headers(admin_token)).status_code == 403
        response = client.put(
            f"/api/host/{host['id']}/customization",
            headers=auth_headers(admin_token),
            json={"remark": "Reseller {USERNAME}"},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["custom_remark"] == "Reseller {USERNAME}"
        assert client.get(f"/api/host/{host['id']}", headers=auth_headers(access_token)).json()["remark"] == remark

        admin_links = _sub_links(admin_user)
        assert f"Reseller {admin_user['username']}" in admin_links
        assert remark not in admin_links
        assert remark in _sub_links(owner_user)

        # Hiding drops the host from the admin's users only
        response = client.put(
            f"/api/host/{host['id']}/customization",
            headers=auth_headers(admin_token),
            json={"remark": "Reseller {USERNAME}", "is_disabled": True},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert "198.51.100.7" not in _sub_links(admin_user)
        assert "198.51.100.7" in _sub_links(owner_user)

        # Defaults remove the customization
        response = client.put(f"/api/host/{host['id']}/customization", headers=auth_headers(admin_token), json={})
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["custom_remark"] is None
        assert _override_count(host["id"]) == 0
        assert remark in _sub_links(admin_user)
    finally:
        client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        delete_user(access_token, owner_user["username"])
        delete_user(access_token, admin_user["username"])
        delete_admin(access_token, admin["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_customization_requires_permission(access_token):
    core = create_core(access_token)
    host = _create_host(access_token, unique_name("perm"))
    admin = create_admin(access_token)
    admin_token = _login(admin["username"], admin["password"])
    try:
        assert client.get("/api/hosts/customizations", headers=auth_headers(admin_token)).status_code == 403
        response = client.put(
            f"/api/host/{host['id']}/customization", headers=auth_headers(admin_token), json={"is_disabled": True}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        delete_admin(access_token, admin["username"])
        delete_core(access_token, core["id"])


def test_customization_is_limited_to_allowed_groups(access_token):
    core = create_core(access_token)
    group = create_group(access_token, inbound_tags=[INBOUND_TAG])
    other_group = create_group(access_token, inbound_tags=["VMess TCP"])
    role = _create_role(access_token, CUSTOMIZE_PERMISSIONS, access={"allowed_group_ids": [other_group["id"]]})
    admin = create_admin(access_token, role_id=role["id"])
    admin_token = _login(admin["username"], admin["password"])
    host = _create_host(access_token, unique_name("hidden"))
    try:
        response = client.get("/api/hosts/customizations", headers=auth_headers(admin_token))
        assert response.status_code == status.HTTP_200_OK, response.text
        assert host["id"] not in {item["host_id"] for item in response.json()}

        response = client.put(
            f"/api/host/{host['id']}/customization", headers=auth_headers(admin_token), json={"remark": "mine"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    finally:
        client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        delete_admin(access_token, admin["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))
        delete_group(access_token, other_group["id"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_customization_rejects_unrenderable_remark(access_token):
    core = create_core(access_token)
    role = _create_role(access_token, CUSTOMIZE_PERMISSIONS)
    admin = create_admin(access_token, role_id=role["id"])
    admin_token = _login(admin["username"], admin["password"])
    host = _create_host(access_token, unique_name("fmt"))
    try:
        response = client.put(
            f"/api/host/{host['id']}/customization", headers=auth_headers(admin_token), json={"remark": "{0}"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
    finally:
        client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        delete_admin(access_token, admin["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_removing_host_or_admin_removes_its_customizations(access_token):
    core = create_core(access_token)
    role = _create_role(access_token, CUSTOMIZE_PERMISSIONS)
    admin = create_admin(access_token, role_id=role["id"])
    admin_token = _login(admin["username"], admin["password"])
    hosts = [_create_host(access_token, unique_name("gone")) for _ in range(2)]
    try:
        for host in hosts:
            response = client.put(
                f"/api/host/{host['id']}/customization", headers=auth_headers(admin_token), json={"remark": "x"}
            )
            assert response.status_code == status.HTTP_200_OK, response.text

        client.delete(f"/api/host/{hosts[0]['id']}", headers=auth_headers(access_token))
        assert _override_count(hosts[0]["id"]) == 0

        delete_admin(access_token, admin["username"])
        assert _override_count(hosts[1]["id"]) == 0
    finally:
        for host in hosts:
            client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        client.delete(f"/api/admin/{admin['username']}", headers=auth_headers(access_token))
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def _modify_role(access_token: str, role_id: int, **changes) -> None:
    response = client.put(f"/api/admin-role/{role_id}", headers=auth_headers(access_token), json=changes)
    assert response.status_code == status.HTTP_200_OK, response.text


def test_overrides_stop_applying_when_permission_is_revoked(access_token):
    core = create_core(access_token)
    group = create_group(access_token, inbound_tags=[INBOUND_TAG])
    role = _create_role(access_token, CUSTOMIZE_PERMISSIONS)
    admin = create_admin(access_token, role_id=role["id"])
    admin_token = _login(admin["username"], admin["password"])
    remark = unique_name("revoked")
    host = _create_host(access_token, remark)
    admin_user = create_user(admin_token, group_ids=[group["id"]])
    try:
        response = client.put(
            f"/api/host/{host['id']}/customization",
            headers=auth_headers(admin_token),
            json={"remark": "Reseller name"},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert "Reseller name" in _sub_links(admin_user)

        # The owner revokes the permission: the saved remark no longer reaches the admin's users
        _modify_role(access_token, role["id"], permissions={"users": CUSTOMIZE_PERMISSIONS["users"]})
        links = _sub_links(admin_user)
        assert "Reseller name" not in links
        assert remark in links

        # Granting it again brings the saved remark back
        _modify_role(access_token, role["id"], permissions=CUSTOMIZE_PERMISSIONS)
        assert "Reseller name" in _sub_links(admin_user)
    finally:
        client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        delete_user(access_token, admin_user["username"])
        delete_admin(access_token, admin["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_overrides_stop_applying_outside_allowed_groups(access_token):
    core = create_core(access_token)
    group = create_group(access_token, inbound_tags=[INBOUND_TAG])
    other_group = create_group(access_token, inbound_tags=["VMess TCP"])
    role = _create_role(access_token, CUSTOMIZE_PERMISSIONS, access={"allowed_group_ids": [group["id"]]})
    admin = create_admin(access_token, role_id=role["id"])
    admin_token = _login(admin["username"], admin["password"])
    remark = unique_name("narrowed")
    host = _create_host(access_token, remark)
    admin_user = create_user(admin_token, group_ids=[group["id"]])
    try:
        response = client.put(
            f"/api/host/{host['id']}/customization",
            headers=auth_headers(admin_token),
            json={"remark": "Reseller name"},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert "Reseller name" in _sub_links(admin_user)

        # The host's inbound leaves the role's allowed groups, so the override stops applying
        _modify_role(access_token, role["id"], access={"allowed_group_ids": [other_group["id"]]})
        links = _sub_links(admin_user)
        assert "Reseller name" not in links
        assert remark in links
    finally:
        client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        delete_user(access_token, admin_user["username"])
        delete_admin(access_token, admin["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))
        delete_group(access_token, other_group["id"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])

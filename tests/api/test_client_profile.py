import asyncio
import json

import pytest
from fastapi import status

from app.db.crud.user import get_user_by_id
from app.node.user import node_payload_signature
from tests.api import GetTestDB, client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_client_template,
    create_core,
    create_group,
    create_user,
    create_user_template,
    delete_admin,
    delete_client_template,
    delete_core,
    delete_group,
    delete_user,
    delete_user_template,
    unique_name,
)

XRAY_TEMPLATE = json.dumps(
    {
        "inbounds": [{"tag": "placeholder", "protocol": "vmess", "settings": {"clients": []}}],
        "outbounds": [{"tag": "profile-marker", "protocol": "freedom", "settings": {}}],
    }
)
SINGBOX_TEMPLATE = json.dumps(
    {
        "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 2080}],
        "outbounds": [{"type": "direct", "tag": "profile-marker"}],
    }
)


@pytest.fixture(autouse=True)
def core(access_token):
    # Groups need at least one inbound
    created = create_core(access_token)
    yield created
    delete_core(access_token, created["id"])


def create_client_profile(access_token: str, **payload) -> dict:
    payload.setdefault("name", unique_name("client_profile"))
    response = client.post("/api/client_profile", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def delete_client_profile(access_token: str, profile_id: int) -> None:
    client.delete(f"/api/client_profile/{profile_id}", headers=auth_headers(access_token))


def _xray_template(access_token: str) -> dict:
    return create_client_template(
        access_token, name=unique_name("profile_xray"), template_type="xray_subscription", content=XRAY_TEMPLATE
    )


def _login(username: str, password: str) -> str:
    response = client.post(
        "/api/admin/token",
        data={"username": username, "password": password, "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access_token"]


def test_client_profile_crud(access_token):
    template = _xray_template(access_token)
    profile = create_client_profile(
        access_token,
        name="  " + unique_name("crud") + "  ",
        note="for resellers",
        templates={"xray_subscription": template["id"]},
        settings={
            "profile_title": "Reseller {USERNAME}",
            "support_url": "",
            "update_interval": 6,
            "response_headers": {"X-Brand": "acme"},
            "remove_response_headers": ["Announce", "announce"],
            "custom_variables": [{"key": "brand", "value": "Acme"}],
        },
    )
    try:
        assert profile["name"] == profile["name"].strip()
        assert profile["templates"] == {"xray_subscription": template["id"]}
        assert profile["settings"]["profile_title"] == "Reseller {USERNAME}"
        assert profile["settings"]["support_url"] is None  # empty string means inherit
        assert profile["settings"]["remove_response_headers"] == ["Announce"]
        assert profile["settings"]["custom_variables"] == [{"key": "BRAND", "value": "Acme"}]
        assert profile["users_count"] == 0
        assert profile["created_at"]

        response = client.get(f"/api/client_profile/{profile['id']}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["settings"] == profile["settings"]

        # Partial modify: only the note changes, templates/settings stay
        response = client.put(
            f"/api/client_profile/{profile['id']}", headers=auth_headers(access_token), json={"note": "changed"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["note"] == "changed"
        assert response.json()["templates"] == profile["templates"]
        assert response.json()["settings"] == profile["settings"]

        response = client.put(
            f"/api/client_profile/{profile['id']}",
            headers=auth_headers(access_token),
            json={"templates": {}, "settings": {"announce": "hi"}},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["templates"] == {}
        assert response.json()["settings"]["announce"] == "hi"
        assert response.json()["settings"]["profile_title"] is None

        listed = client.get(
            "/api/client_profiles", params={"ids": [profile["id"]]}, headers=auth_headers(access_token)
        ).json()
        assert listed["count"] == 1
        assert listed["profiles"][0]["id"] == profile["id"]

        simple = client.get(
            "/api/client_profiles/simple", params={"search": profile["name"]}, headers=auth_headers(access_token)
        ).json()
        assert simple["profiles"] == [{"id": profile["id"], "name": profile["name"]}]

        response = client.delete(f"/api/client_profile/{profile['id']}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        response = client.get(f"/api/client_profile/{profile['id']}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_404_NOT_FOUND
    finally:
        delete_client_profile(access_token, profile["id"])
        delete_client_template(access_token, template["id"])


def test_client_profile_validation(access_token):
    name = unique_name("dup")
    profile = create_client_profile(access_token, name=name)
    singbox = create_client_template(
        access_token, name=unique_name("profile_sb"), template_type="singbox_subscription", content=SINGBOX_TEMPLATE
    )
    try:
        headers = auth_headers(access_token)
        response = client.post("/api/client_profile", headers=headers, json={"name": name})
        assert response.status_code == status.HTTP_409_CONFLICT

        other = create_client_profile(access_token)
        response = client.put(f"/api/client_profile/{other['id']}", headers=headers, json={"name": name})
        assert response.status_code == status.HTTP_409_CONFLICT
        delete_client_profile(access_token, other["id"])

        # A sing-box template cannot be used as the xray template
        response = client.post(
            "/api/client_profile",
            headers=headers,
            json={"name": unique_name("mismatch"), "templates": {"xray_subscription": singbox["id"]}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not of type" in response.json()["detail"]

        response = client.put(
            f"/api/client_profile/{profile['id']}",
            headers=headers,
            json={"templates": {"singbox_subscription": 999999999}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not found" in response.json()["detail"]

        # Only whole-config template types are accepted
        response = client.post(
            "/api/client_profile",
            headers=headers,
            json={"name": unique_name("ua"), "templates": {"user_agent": singbox["id"]}},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        for settings in (
            {"response_headers": {"Bad Header": "x"}},
            {"remove_response_headers": ["bad header"]},
            {"update_interval": 0},
            {"announce": "x" * 129},
            {"custom_variables": [{"key": "USERNAME", "value": "x"}]},
        ):
            response = client.post(
                "/api/client_profile", headers=headers, json={"name": unique_name("bad"), "settings": settings}
            )
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, settings

        response = client.post("/api/client_profile", headers=headers, json={"name": "   "})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    finally:
        delete_client_profile(access_token, profile["id"])
        delete_client_template(access_token, singbox["id"])


def test_deleting_client_template_used_by_profile_is_refused(access_token):
    template = _xray_template(access_token)
    profile = create_client_profile(access_token, templates={"xray_subscription": template["id"]})
    try:
        headers = auth_headers(access_token)
        response = client.delete(f"/api/client_template/{template['id']}", headers=headers)
        assert response.status_code == status.HTTP_409_CONFLICT
        assert profile["name"] in response.json()["detail"]

        response = client.post("/api/client_templates/bulk/delete", headers=headers, json={"ids": [template["id"]]})
        assert response.status_code == status.HTTP_409_CONFLICT

        assert client.get(f"/api/client_template/{template['id']}", headers=headers).status_code == 200
    finally:
        delete_client_profile(access_token, profile["id"])
        delete_client_template(access_token, template["id"])


def test_users_count_and_delete_profile_detaches_users(access_token):
    headers = auth_headers(access_token)
    profile = create_client_profile(access_token)
    group = create_group(access_token)
    template = create_user_template(access_token, group_ids=[group["id"]])
    users = [
        create_user(access_token, group_ids=[group["id"]], payload={"client_profile_id": profile["id"]})
        for _ in range(2)
    ]
    other = create_user(access_token, group_ids=[group["id"]])
    try:
        response = client.put(
            f"/api/user_template/{template['id']}", headers=headers, json={"client_profile_id": profile["id"]}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["client_profile_id"] == profile["id"]

        assert client.get(f"/api/client_profile/{profile['id']}", headers=headers).json()["users_count"] == 2
        listed = client.get("/api/client_profiles", params={"ids": [profile["id"]]}, headers=headers).json()
        assert listed["profiles"][0]["users_count"] == 2

        response = client.delete(f"/api/client_profile/{profile['id']}", headers=headers)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        for user in users:
            assert client.get(f"/api/user/{user['username']}", headers=headers).json()["client_profile_id"] is None
        assert client.get(f"/api/user_template/{template['id']}", headers=headers).json()["client_profile_id"] is None
    finally:
        for user in [*users, other]:
            delete_user(access_token, user["username"])
        delete_user_template(access_token, template["id"])
        delete_group(access_token, group["id"])
        delete_client_profile(access_token, profile["id"])


def test_bulk_assign_and_unassign_users(access_token):
    headers = auth_headers(access_token)
    profile = create_client_profile(access_token)
    other_profile = create_client_profile(access_token)
    group = create_group(access_token)
    users = [create_user(access_token, group_ids=[group["id"]]) for _ in range(3)]
    ids = [user["id"] for user in users]
    try:
        response = client.post(f"/api/client_profile/{profile['id']}/users", headers=headers, json={"user_ids": ids})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"count": 3}
        assert client.get(f"/api/client_profile/{profile['id']}", headers=headers).json()["users_count"] == 3
        for user in users:
            assert (
                client.get(f"/api/user/{user['username']}", headers=headers).json()["client_profile_id"]
                == (profile["id"])
            )

        # Unknown user: nothing changes
        response = client.post(
            f"/api/client_profile/{other_profile['id']}/users", headers=headers, json={"user_ids": [ids[0], 999999999]}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert client.get(f"/api/client_profile/{profile['id']}", headers=headers).json()["users_count"] == 3

        response = client.request(
            "DELETE", f"/api/client_profile/{profile['id']}/users", headers=headers, json={"user_ids": [ids[0]]}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"count": 1}
        assert client.get(f"/api/user/{users[0]['username']}", headers=headers).json()["client_profile_id"] is None

        # Moving one user to another profile; unassign all only touches users still on this profile
        client.post(f"/api/client_profile/{other_profile['id']}/users", headers=headers, json={"user_ids": [ids[1]]})
        response = client.request(
            "DELETE", f"/api/client_profile/{profile['id']}/users", headers=headers, json={"all": True}
        )
        assert response.json() == {"count": 1}
        assert client.get(f"/api/client_profile/{profile['id']}", headers=headers).json()["users_count"] == 0
        assert (
            client.get(f"/api/user/{users[1]['username']}", headers=headers).json()["client_profile_id"]
            == (other_profile["id"])
        )

        response = client.request("DELETE", f"/api/client_profile/{profile['id']}/users", headers=headers, json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    finally:
        for user in users:
            delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        delete_client_profile(access_token, profile["id"])
        delete_client_profile(access_token, other_profile["id"])


def test_user_create_modify_and_template_carry_client_profile(access_token):
    headers = auth_headers(access_token)
    profile = create_client_profile(access_token)
    template_profile = create_client_profile(access_token)
    group = create_group(access_token)
    template = create_user_template(access_token, group_ids=[group["id"]])
    usernames = []
    try:
        response = client.post(
            "/api/user",
            headers=headers,
            json={"username": unique_name("cp_unknown"), "proxy_settings": {}, "client_profile_id": 999999999},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

        user = create_user(access_token, group_ids=[group["id"]], payload={"client_profile_id": profile["id"]})
        usernames.append(user["username"])
        assert user["client_profile_id"] == profile["id"]

        # Omitted = unchanged
        response = client.put(f"/api/user/{user['username']}", headers=headers, json={"note": "x"})
        assert response.json()["client_profile_id"] == profile["id"]
        response = client.put(f"/api/user/{user['username']}", headers=headers, json={"client_profile_id": 999999999})
        assert response.status_code == status.HTTP_404_NOT_FOUND
        # null = clear
        response = client.put(f"/api/user/{user['username']}", headers=headers, json={"client_profile_id": None})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["client_profile_id"] is None

        response = client.put(
            f"/api/user_template/{template['id']}", headers=headers, json={"client_profile_id": 999999999}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        response = client.put(
            f"/api/user_template/{template['id']}", headers=headers, json={"client_profile_id": template_profile["id"]}
        )
        assert response.json()["client_profile_id"] == template_profile["id"]

        # From template: copies the template's profile
        response = client.post(
            "/api/user/from_template",
            headers=headers,
            json={"user_template_id": template["id"], "username": unique_name("cp_tmpl")},
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text
        usernames.append(response.json()["username"])
        assert response.json()["client_profile_id"] == template_profile["id"]

        # ...unless the request sets one explicitly (null included)
        for explicit in (profile["id"], None):
            response = client.post(
                "/api/user/from_template",
                headers=headers,
                json={
                    "user_template_id": template["id"],
                    "username": unique_name("cp_tmpl"),
                    "client_profile_id": explicit,
                },
            )
            assert response.status_code == status.HTTP_201_CREATED, response.text
            usernames.append(response.json()["username"])
            assert response.json()["client_profile_id"] == explicit

        response = client.post(
            "/api/user/from_template",
            headers=headers,
            json={"user_template_id": template["id"], "username": unique_name("cp_tmpl"), "client_profile_id": 999999},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Applying a template to an existing user sets the template's profile
        response = client.put(
            f"/api/user/from_template/{user['username']}",
            headers=headers,
            json={"user_template_id": template["id"]},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["client_profile_id"] == template_profile["id"]
    finally:
        for username in usernames:
            delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        delete_group(access_token, group["id"])
        delete_client_profile(access_token, profile["id"])
        delete_client_profile(access_token, template_profile["id"])


def test_non_owner_needs_client_profile_read_to_assign(access_token):
    headers = auth_headers(access_token)
    profile = create_client_profile(access_token)
    role_payload = {
        "name": unique_name("cp_role"),
        "permissions": {
            "users": {"create": True, "read": {"scope": 1}, "update": {"scope": 1}, "delete": {"scope": 1}},
            "client_profiles": {"read_simple": True},
        },
    }
    role = client.post("/api/admin-role", headers=headers, json=role_payload).json()
    operator = create_admin(access_token, role_id=3)
    reseller = create_admin(access_token, role_id=role["id"])
    created = []
    try:
        operator_token = _login(operator["username"], operator["password"])
        response = client.post(
            "/api/user",
            headers=auth_headers(operator_token),
            json={"username": unique_name("cp_op"), "proxy_settings": {}, "client_profile_id": profile["id"]},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert client.get("/api/client_profiles/simple", headers=auth_headers(operator_token)).status_code == 403

        # Without a profile the operator still creates users, and echoing an unchanged value is fine
        response = client.post(
            "/api/user",
            headers=auth_headers(operator_token),
            json={"username": unique_name("cp_op"), "proxy_settings": {}, "client_profile_id": None},
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text
        created.append(response.json()["username"])

        reseller_token = _login(reseller["username"], reseller["password"])
        response = client.post(
            "/api/user",
            headers=auth_headers(reseller_token),
            json={"username": unique_name("cp_rs"), "proxy_settings": {}, "client_profile_id": profile["id"]},
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text
        created.append(response.json()["username"])
        assert response.json()["client_profile_id"] == profile["id"]

        # Managing profiles still needs the matching client_profiles actions
        response = client.post(
            f"/api/client_profile/{profile['id']}/users",
            headers=auth_headers(reseller_token),
            json={"user_ids": [response.json()["id"]]},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        for username in created:
            delete_user(access_token, username)
        delete_admin(access_token, operator["username"])
        delete_admin(access_token, reseller["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=headers)
        delete_client_profile(access_token, profile["id"])


async def _node_signature(user_id: int):
    async with GetTestDB() as db:
        db_user = await get_user_by_id(db, user_id)
        return await node_payload_signature(db_user)


def test_client_profile_does_not_reach_node_payload(access_token):
    headers = auth_headers(access_token)
    profile = create_client_profile(access_token)
    group = create_group(access_token)
    user = create_user(access_token, group_ids=[group["id"]])
    try:
        before = asyncio.run(_node_signature(user["id"]))
        response = client.put(
            f"/api/user/{user['username']}", headers=headers, json={"client_profile_id": profile["id"]}
        )
        assert response.json()["client_profile_id"] == profile["id"]
        assert asyncio.run(_node_signature(user["id"])) == before
    finally:
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        delete_client_profile(access_token, profile["id"])


def test_next_plan_template_applies_its_client_profile(access_token):
    headers = auth_headers(access_token)
    profile = create_client_profile(access_token)
    group = create_group(access_token)
    template = create_user_template(access_token, group_ids=[group["id"]])
    client.put(f"/api/user_template/{template['id']}", headers=headers, json={"client_profile_id": profile["id"]})
    user = create_user(
        access_token,
        group_ids=[group["id"]],
        payload={"next_plan": {"user_template_id": template["id"], "add_remaining_traffic": False}},
    )
    try:
        assert user["client_profile_id"] is None
        response = client.post(f"/api/user/{user['username']}/active_next", headers=headers)
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["client_profile_id"] == profile["id"]
    finally:
        delete_user(access_token, user["username"])
        delete_user_template(access_token, template["id"])
        delete_group(access_token, group["id"])
        delete_client_profile(access_token, profile["id"])


def _create_role(access_token: str, client_profiles: dict | None = None) -> dict:
    permissions = {"users": {"create": True, "read": {"scope": 1}, "update": {"scope": 1}, "delete": {"scope": 1}}}
    if client_profiles is not None:
        permissions["client_profiles"] = client_profiles
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={"name": unique_name("cp_role"), "permissions": permissions},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def _create_own_users(token: str, group_id: int, count: int) -> list[dict]:
    users = []
    for _ in range(count):
        response = client.post(
            "/api/user",
            headers=auth_headers(token),
            json={"username": unique_name("cp_own"), "proxy_settings": {}, "group_ids": [group_id]},
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text
        users.append(response.json())
    return users


def test_template_apply_checks_profile_change_against_users_current_profile(access_token):
    headers = auth_headers(access_token)
    profile = create_client_profile(access_token)
    other_profile = create_client_profile(access_token)
    group = create_group(access_token)
    # The template has no profile of its own, so the override is compared with each user's profile
    template = create_user_template(access_token, group_ids=[group["id"]])
    plain_role = _create_role(access_token)
    profile_role = _create_role(access_token, {"read_simple": True})
    plain_admin = create_admin(access_token, role_id=plain_role["id"])
    profile_admin = create_admin(access_token, role_id=profile_role["id"])
    usernames = []

    def profile_of(user: dict):
        return client.get(f"/api/user/{user['username']}", headers=headers).json()["client_profile_id"]

    try:
        users_by_admin = {}
        for admin in (plain_admin, profile_admin):
            token = _login(admin["username"], admin["password"])
            users = _create_own_users(token, group["id"], 2)
            usernames.extend(user["username"] for user in users)
            users_by_admin[admin["username"]] = (token, users)
            response = client.post(
                f"/api/client_profile/{profile['id']}/users",
                headers=headers,
                json={"user_ids": [user["id"] for user in users]},
            )
            assert response.json() == {"count": 2}

        token, (single, bulk) = users_by_admin[plain_admin["username"]]
        for explicit in (None, other_profile["id"]):
            response = client.put(
                f"/api/user/from_template/{single['username']}",
                headers=auth_headers(token),
                json={"user_template_id": template["id"], "client_profile_id": explicit},
            )
            assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
            response = client.post(
                "/api/users/bulk/apply_template",
                headers=auth_headers(token),
                json={"ids": [bulk["id"]], "user_template_id": template["id"], "client_profile_id": explicit},
            )
            assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
        assert profile_of(single) == profile_of(bulk) == profile["id"]

        # Echoing the user's current profile, or leaving it out, is not a change
        response = client.put(
            f"/api/user/from_template/{single['username']}",
            headers=auth_headers(token),
            json={"user_template_id": template["id"], "client_profile_id": profile["id"]},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["client_profile_id"] == profile["id"]
        response = client.post(
            "/api/users/bulk/apply_template",
            headers=auth_headers(token),
            json={"ids": [bulk["id"]], "user_template_id": template["id"]},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert profile_of(bulk) == profile["id"]

        token, (single, bulk) = users_by_admin[profile_admin["username"]]
        response = client.put(
            f"/api/user/from_template/{single['username']}",
            headers=auth_headers(token),
            json={"user_template_id": template["id"], "client_profile_id": None},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["client_profile_id"] is None
        response = client.post(
            "/api/users/bulk/apply_template",
            headers=auth_headers(token),
            json={"ids": [bulk["id"]], "user_template_id": template["id"], "client_profile_id": other_profile["id"]},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert profile_of(bulk) == other_profile["id"]
    finally:
        for username in usernames:
            delete_user(access_token, username)
        delete_admin(access_token, plain_admin["username"])
        delete_admin(access_token, profile_admin["username"])
        client.delete(f"/api/admin-role/{plain_role['id']}", headers=headers)
        client.delete(f"/api/admin-role/{profile_role['id']}", headers=headers)
        delete_user_template(access_token, template["id"])
        delete_group(access_token, group["id"])
        delete_client_profile(access_token, profile["id"])
        delete_client_profile(access_token, other_profile["id"])


def test_bulk_assign_with_own_scope_touches_only_own_users(access_token):
    headers = auth_headers(access_token)
    profile = create_client_profile(access_token)
    group = create_group(access_token)
    role = _create_role(access_token, {"read": True, "update": True})
    reseller = create_admin(access_token, role_id=role["id"])
    owner_user = create_user(access_token, group_ids=[group["id"]])
    usernames = [owner_user["username"]]

    def users_count():
        return client.get(f"/api/client_profile/{profile['id']}", headers=headers).json()["users_count"]

    try:
        token = _login(reseller["username"], reseller["password"])
        own_users = _create_own_users(token, group["id"], 2)
        usernames.extend(user["username"] for user in own_users)
        own_ids = [user["id"] for user in own_users]

        # Another admin's user is out of scope: the whole request is refused
        response = client.post(
            f"/api/client_profile/{profile['id']}/users",
            headers=auth_headers(token),
            json={"user_ids": [*own_ids, owner_user["id"]]},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert users_count() == 0

        response = client.post(
            f"/api/client_profile/{profile['id']}/users", headers=auth_headers(token), json={"user_ids": own_ids}
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json() == {"count": 2}
        client.post(
            f"/api/client_profile/{profile['id']}/users", headers=headers, json={"user_ids": [owner_user["id"]]}
        )
        assert users_count() == 3

        # all: true only detaches the reseller's own users
        response = client.request(
            "DELETE", f"/api/client_profile/{profile['id']}/users", headers=auth_headers(token), json={"all": True}
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json() == {"count": 2}
        assert users_count() == 1
        owner_user_now = client.get(f"/api/user/{owner_user['username']}", headers=headers).json()
        assert owner_user_now["client_profile_id"] == profile["id"]
    finally:
        for username in usernames:
            delete_user(access_token, username)
        delete_admin(access_token, reseller["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=headers)
        delete_group(access_token, group["id"])
        delete_client_profile(access_token, profile["id"])


def test_bulk_template_operations_carry_explicit_client_profile(access_token):
    headers = auth_headers(access_token)
    profile = create_client_profile(access_token)
    template_profile = create_client_profile(access_token)
    group = create_group(access_token)
    template = create_user_template(access_token, group_ids=[group["id"]])
    client.put(
        f"/api/user_template/{template['id']}", headers=headers, json={"client_profile_id": template_profile["id"]}
    )
    usernames = []

    def profile_of(username: str):
        return client.get(f"/api/user/{username}", headers=headers).json()["client_profile_id"]

    try:
        # "omit" = no client_profile_id in the request: the template's profile applies
        for explicit, expected in ((None, None), (profile["id"], profile["id"]), ("omit", template_profile["id"])):
            base_username = unique_name("cp_bulk")
            payload = {
                "user_template_id": template["id"],
                "strategy": "sequence",
                "username": base_username,
                "count": 2,
            }
            if explicit != "omit":
                payload["client_profile_id"] = explicit
            response = client.post("/api/users/bulk/from_template", headers=headers, json=payload)
            assert response.status_code == status.HTTP_201_CREATED, response.text
            created = [f"{base_username}{number}" for number in (1, 2)]
            usernames.extend(created)
            assert [profile_of(username) for username in created] == [expected, expected]

        ids = [client.get(f"/api/user/{username}", headers=headers).json()["id"] for username in usernames[:2]]
        for explicit, expected in ((profile["id"], profile["id"]), (None, None), ("omit", template_profile["id"])):
            payload = {"ids": ids, "user_template_id": template["id"]}
            if explicit != "omit":
                payload["client_profile_id"] = explicit
            response = client.post("/api/users/bulk/apply_template", headers=headers, json=payload)
            assert response.status_code == status.HTTP_200_OK, response.text
            assert [profile_of(username) for username in usernames[:2]] == [expected, expected]

        response = client.post(
            "/api/users/bulk/apply_template",
            headers=headers,
            json={"ids": ids, "user_template_id": template["id"], "client_profile_id": 999999999},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    finally:
        for username in usernames:
            delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        delete_group(access_token, group["id"])
        delete_client_profile(access_token, profile["id"])
        delete_client_profile(access_token, template_profile["id"])

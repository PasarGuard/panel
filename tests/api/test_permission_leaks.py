"""Regression tests for RBAC permission leaks."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from sqlalchemy import select

from app.db.crud.admin import build_admin_details, get_admin_by_id
from app.db.models import Admin
from app.models.admin import hash_password
from app.models.user import UserListQuery
from app.operation import OperatorType
from app.operation.user import UserOperation
from app.telegram.handlers.admin.user import search_user
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_core,
    create_group,
    create_user,
    create_user_template,
    delete_admin,
    delete_core,
    delete_group,
    set_user_hwids,
    strong_password,
    unique_name,
)

SCOPE_OWN = {"scope": 1}
SCOPE_ALL = {"scope": 2}


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
        json={
            "name": unique_name("role_leak"),
            "permissions": permissions,
            "limits": {},
            "features": {},
            "access": access or {},
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def _delete_role(access_token: str, role_id: int) -> None:
    client.delete(f"/api/admin-role/{role_id}", headers=auth_headers(access_token))


def _create_owner_admin() -> dict:
    username = unique_name("owner_key")
    password = strong_password("OwnerKey")

    async def _create() -> int:
        async with TestSession() as session:
            db_admin = Admin(username=username, hashed_password=await hash_password(password), role_id=1)
            session.add(db_admin)
            await session.commit()
            await session.refresh(db_admin)
            return db_admin.id

    return {"id": asyncio.run(_create()), "username": username, "password": password}


def _delete_admin_row(username: str) -> None:
    async def _delete() -> None:
        async with TestSession() as session:
            db_admin = (await session.execute(select(Admin).where(Admin.username == username))).scalar_one_or_none()
            if db_admin is not None:
                await session.delete(db_admin)
                await session.commit()

    asyncio.run(_delete())


def _create_api_key(token: str, **payload) -> str:
    response = client.post(
        "/api/api_key",
        headers=auth_headers(token),
        json={"name": unique_name("api_key"), **payload},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()["api_key"]


# --- API keys with custom (non-inherited) permissions ---


def test_api_key_with_empty_custom_permissions_grants_nothing(access_token):
    admin = create_admin(access_token, role_id=2)
    try:
        raw_key = _create_api_key(
            _login(admin["username"], admin["password"]),
            inherit_permissions=False,
            permissions={},
        )

        response = client.get("/api/users", headers={"X-Api-Key": raw_key})

        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, admin["username"])


def test_owner_api_key_with_empty_custom_permissions_is_not_owner(access_token):
    owner = _create_owner_admin()
    try:
        raw_key = _create_api_key(
            _login(owner["username"], owner["password"]),
            inherit_permissions=False,
            permissions={},
        )

        response = client.get("/api/admin-roles", headers={"X-Api-Key": raw_key})

        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        _delete_admin_row(owner["username"])


# --- User actions must be scoped on the action the route gates on ---

# Can read every user, but may only change its own users.
READ_ALL_WRITE_OWN = {
    "users": {
        "create": True,
        "read": SCOPE_ALL,
        "update": SCOPE_OWN,
        "delete": SCOPE_OWN,
        "reset_usage": SCOPE_OWN,
        "revoke_sub": SCOPE_OWN,
        "set_owner": SCOPE_OWN,
        "activate_next_plan": SCOPE_OWN,
    }
}

# Can update every user, but the dedicated actions are limited to its own users.
UPDATE_ALL_ACTIONS_OWN = {
    "users": {
        "create": True,
        "read": SCOPE_ALL,
        "update": SCOPE_ALL,
        "reset_usage": SCOPE_OWN,
        "set_owner": SCOPE_OWN,
        "activate_next_plan": SCOPE_OWN,
    }
}


@pytest.fixture
def scoped_actor(access_token):
    """Build a non-owner admin with the given permissions, plus a user that admin does not own."""
    created = []

    def _build(permissions: dict) -> dict:
        role = _create_role(access_token, permissions)
        actor = create_admin(access_token, role_id=role["id"])
        victim = create_user(access_token)
        created.append((role, actor, victim))
        return {"actor": actor, "token": _login(actor["username"], actor["password"]), "victim": victim}

    yield _build

    for role, actor, victim in created:
        client.delete(f"/api/user/by-id/{victim['id']}", headers=auth_headers(access_token))
        delete_admin(access_token, actor["username"])
        _delete_role(access_token, role["id"])


def _send_as_actor(context: dict, method: str, path: str, *, params: dict | None = None, json: dict | None = None):
    """Send a request as the scoped actor against its victim; "<actor>" placeholders become the actor's username."""
    victim = context["victim"]
    actor_username = context["actor"]["username"]
    if params is not None:
        params = {key: actor_username if value == "<actor>" else value for key, value in params.items()}
    if json is not None:
        json = {key: actor_username if value == "<actor>" else value for key, value in json.items()}
        if "ids" in json:
            json["ids"] = [victim["id"]]
    return client.request(
        method,
        path.format(username=victim["username"], user_id=victim["id"]),
        headers=auth_headers(context["token"]),
        params=params,
        json=json,
    )


def _assert_victim_untouched(access_token: str, victim: dict) -> None:
    response = client.get(f"/api/user/by-id/{victim['id']}", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["note"] == victim["note"]
    assert (response.json()["admin"] or {}).get("username") == (victim["admin"] or {}).get("username")


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        pytest.param("PUT", "/api/user/{username}", {"json": {"note": "changed"}}, id="modify-legacy"),
        pytest.param("PUT", "/api/user/by-username/{username}", {"json": {"note": "changed"}}, id="modify"),
        pytest.param("DELETE", "/api/user/by-username/{username}", {}, id="delete"),
        pytest.param("POST", "/api/user/by-username/{username}/reset", {}, id="reset-usage"),
        pytest.param("POST", "/api/user/by-username/{username}/revoke_sub", {}, id="revoke-sub"),
        pytest.param(
            "PUT",
            "/api/user/by-username/{username}/set_owner",
            {"params": {"admin_username": "<actor>"}},
            id="set-owner",
        ),
        pytest.param("POST", "/api/user/by-username/{username}/active_next", {}, id="activate-next-plan"),
        pytest.param(
            "PUT",
            "/api/user/from_template/by-username/{username}",
            {"json": {"user_template_id": 999999}},
            id="modify-with-template",
        ),
    ],
)
def test_username_user_actions_respect_write_scope(access_token, scoped_actor, method, path, kwargs):
    context = scoped_actor(READ_ALL_WRITE_OWN)

    response = _send_as_actor(context, method, path, **kwargs)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "User not found"
    _assert_victim_untouched(access_token, context["victim"])


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        pytest.param("POST", "/api/user/by-id/{user_id}/reset", {}, id="reset-usage"),
        pytest.param("POST", "/api/user/by-id/{user_id}/active_next", {}, id="activate-next-plan"),
        pytest.param(
            "PUT",
            "/api/user/by-id/{user_id}/set_owner",
            {"params": {"admin_username": "<actor>"}},
            id="set-owner",
        ),
        pytest.param(
            "PUT",
            "/api/users/bulk/set_owner",
            {"json": {"ids": [], "admin_username": "<actor>"}},
            id="bulk-set-owner",
        ),
    ],
)
def test_user_actions_by_id_use_their_own_scope(access_token, scoped_actor, method, path, kwargs):
    context = scoped_actor(UPDATE_ALL_ACTIONS_OWN)

    response = _send_as_actor(context, method, path, **kwargs)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "User not found"
    _assert_victim_untouched(access_token, context["victim"])


@pytest.mark.parametrize(
    ("method", "path", "expected_status"),
    [
        pytest.param("PUT", "/api/user/by-username/{username}", status.HTTP_200_OK, id="modify"),
        pytest.param("POST", "/api/user/by-username/{username}/reset", status.HTTP_200_OK, id="reset-usage"),
        pytest.param("POST", "/api/user/by-id/{user_id}/reset", status.HTTP_200_OK, id="reset-usage-by-id"),
        pytest.param("POST", "/api/user/by-username/{username}/revoke_sub", status.HTTP_200_OK, id="revoke-sub"),
        pytest.param("DELETE", "/api/user/by-username/{username}", status.HTTP_204_NO_CONTENT, id="delete"),
    ],
)
def test_scoped_admin_can_still_act_on_own_users(scoped_actor, method, path, expected_status):
    token = scoped_actor(READ_ALL_WRITE_OWN)["token"]
    own_user = create_user(token)
    try:
        response = client.request(
            method,
            path.format(username=own_user["username"], user_id=own_user["id"]),
            headers=auth_headers(token),
            json={"note": "changed"} if method == "PUT" else None,
        )

        assert response.status_code == expected_status, response.text
    finally:
        client.delete(f"/api/user/by-id/{own_user['id']}", headers=auth_headers(token))


@pytest.mark.parametrize(
    ("path", "params", "permissions"),
    [
        pytest.param(
            "/api/users",
            "username",
            {"users": {"read": SCOPE_OWN, "read_simple": SCOPE_ALL}},
            id="users-read-own-simple-all",
        ),
        pytest.param("/api/users", "username", {"users": {"read": SCOPE_OWN}}, id="users-read-own-no-simple"),
        pytest.param(
            "/api/users/simple",
            "search",
            {"users": {"read": SCOPE_ALL, "read_simple": SCOPE_OWN}},
            id="users-simple-own",
        ),
    ],
)
def test_user_lists_use_the_scope_of_the_permission_their_route_checks(scoped_actor, path, params, permissions):
    context = scoped_actor(permissions)
    victim = context["victim"]

    response = client.get(path, headers=auth_headers(context["token"]), params={params: victim["username"]})

    assert response.status_code == status.HTTP_200_OK
    assert victim["username"] not in {user["username"] for user in response.json()["users"]}


def _api_key_actor(scoped_actor):
    return scoped_actor(
        {
            "users": {"read": SCOPE_OWN, "read_simple": SCOPE_OWN},
            "api_keys": {"create": True, "read": True, "update": True},
        }
    )


def test_api_key_patch_cannot_carry_permissions_beyond_the_admin(scoped_actor):
    context = _api_key_actor(scoped_actor)
    headers = auth_headers(context["token"])
    created = client.post("/api/api_key", headers=headers, json={"name": unique_name("api_key")})
    assert created.status_code == status.HTTP_201_CREATED, created.text
    key_id, raw_key = created.json()["id"], created.json()["api_key"]

    # Permissions sent while the key still inherits are accepted but not stored...
    patched = client.patch(
        f"/api/api_key/{key_id}", headers=headers, json={"permissions": {"users": {"read": True, "read_simple": True}}}
    )
    assert patched.status_code == status.HTTP_200_OK, patched.text
    stored = client.get(f"/api/api_key/{key_id}", headers=headers).json()["permissions"]
    assert all(value is None for value in stored.values()), stored

    # ...so switching inheritance off afterwards leaves a key with no permissions at all.
    switched = client.patch(f"/api/api_key/{key_id}", headers=headers, json={"inherit_permissions": False})
    assert switched.status_code == status.HTTP_200_OK, switched.text
    response = client.get(
        "/api/users", headers={"X-Api-Key": raw_key}, params={"username": context["victim"]["username"]}
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_api_key_patch_with_null_permissions_keeps_the_key_working(scoped_actor):
    context = _api_key_actor(scoped_actor)
    headers = auth_headers(context["token"])
    created = client.post(
        "/api/api_key",
        headers=headers,
        json={
            "name": unique_name("api_key"),
            "inherit_permissions": False,
            "permissions": {"users": {"read": SCOPE_OWN}},
        },
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    key_id, raw_key = created.json()["id"], created.json()["api_key"]

    renamed = client.patch(
        f"/api/api_key/{key_id}", headers=headers, json={"name": unique_name("renamed"), "permissions": None}
    )
    assert renamed.status_code == status.HTTP_200_OK, renamed.text
    assert renamed.json()["permissions"] == created.json()["permissions"]

    assert client.get("/api/admin", headers={"X-Api-Key": raw_key}).status_code == status.HTTP_200_OK


def test_get_users_requires_users_read_without_a_router_gate(scoped_actor):
    # The Telegram inline search calls get_users directly; no route checks users.read for it.
    actor_id = scoped_actor({"users": {"create": True}})["actor"]["id"]

    async def _search():
        async with TestSession() as db:
            admin = build_admin_details(await get_admin_by_id(db, actor_id, load_users=False, load_usage_logs=False))
            return await UserOperation(OperatorType.TELEGRAM).get_users(db, admin, UserListQuery(limit=50))

    with pytest.raises(ValueError, match="users.read"):
        asyncio.run(_search())


def test_telegram_inline_search_answers_instead_of_raising_without_users_read(scoped_actor):
    # Inline queries fire on every keystroke and the bot's error handler does not cover them, so a
    # refusal must become an answer, not an exception (one traceback per keystroke otherwise).
    context = scoped_actor({"users": {"create": True}})
    actor_id = context["actor"]["id"]
    # Search for a real user, so the test also fails if the refusal ever turns into a leak.
    event = SimpleNamespace(query=context["victim"]["username"], answer=AsyncMock())

    async def _inline_search():
        async with TestSession() as db:
            admin = build_admin_details(await get_admin_by_id(db, actor_id, load_users=False, load_usage_logs=False))
            await search_user(event, admin, db)

    asyncio.run(_inline_search())

    results = event.answer.await_args.args[0]
    assert len(results) == 1  # only the "user not found" article (its id can equal a real user id)
    assert context["victim"]["username"] not in results[0].title


@pytest.mark.parametrize(
    ("method", "path", "permissions"),
    [
        pytest.param(
            "POST",
            "/api/user/{user_id}/hwids/reset",
            {"users": {"read": SCOPE_OWN}, "hwids": {"delete": True}},
            id="reset-read-own",
        ),
        pytest.param("POST", "/api/user/{user_id}/hwids/reset", {"hwids": {"delete": True}}, id="reset-no-users-perms"),
        pytest.param(
            "DELETE",
            "/api/user/{user_id}/hwids/some-device",
            {"users": {"read": SCOPE_OWN}, "hwids": {"delete": True}},
            id="delete-read-own",
        ),
        pytest.param("GET", "/api/user/{user_id}/hwids", {"hwids": {"read": True}}, id="list-no-users-perms"),
    ],
)
def test_hwid_endpoints_only_reach_users_the_admin_can_see(scoped_actor, method, path, permissions):
    context = scoped_actor(permissions)

    response = client.request(
        method, path.format(user_id=context["victim"]["id"]), headers=auth_headers(context["token"])
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "User not found"


@pytest.mark.parametrize(
    ("permissions", "sees_counts"),
    [
        pytest.param({"users": {"read": SCOPE_ALL}}, False, id="without-hwids-read"),
        pytest.param({"users": {"read": SCOPE_ALL}, "hwids": {"read": True}}, True, id="with-hwids-read"),
    ],
)
def test_user_list_shows_device_counts_only_with_hwids_read(access_token, scoped_actor, permissions, sees_counts):
    context = scoped_actor(permissions)
    tag = unique_name("hwid_scope")
    # Device count order and username order disagree, so the listing shows which sort applied
    first, second = [create_user(access_token, username=f"{tag}_{name}") for name in ("a", "b")]
    try:
        set_user_hwids(first["id"], 2)
        set_user_hwids(second["id"], 0)

        response = client.get(
            "/api/users",
            headers=auth_headers(context["token"]),
            params={"search": tag, "sort": "-hwid_count,-username"},
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        listed = [(user["username"], user["hwid_count"]) for user in response.json()["users"]]
        if sees_counts:
            assert listed == [(first["username"], 2), (second["username"], 0)]
        else:
            assert listed == [(second["username"], None), (first["username"], None)]
    finally:
        for user in (first, second):
            # SQLite keeps a deleted user's devices and can hand its id to a later test's user
            set_user_hwids(user["id"], 0)
            client.delete(f"/api/user/by-id/{user['id']}", headers=auth_headers(access_token))


# --- Group / template access lists ---


@pytest.fixture
def restricted_catalog(access_token):
    """Two groups and two templates; a restricted admin may only see the first of each."""
    core = create_core(access_token)
    allowed_group = create_group(access_token)
    hidden_group = create_group(access_token)
    allowed_template = create_user_template(access_token, group_ids=[allowed_group["id"]])
    hidden_template = create_user_template(access_token, group_ids=[hidden_group["id"]])
    role = _create_role(
        access_token,
        {
            "groups": {"read": True, "read_simple": True},
            "templates": {"read": True, "read_simple": True, "update": True, "delete": True},
        },
        access={
            "allowed_group_ids": [allowed_group["id"]],
            "allowed_template_ids": [allowed_template["id"]],
        },
    )
    admin = create_admin(access_token, role_id=role["id"])
    try:
        yield {
            "token": _login(admin["username"], admin["password"]),
            "allowed_group": allowed_group,
            "hidden_group": hidden_group,
            "allowed_template": allowed_template,
            "hidden_template": hidden_template,
        }
    finally:
        delete_admin(access_token, admin["username"])
        _delete_role(access_token, role["id"])
        for template in (allowed_template, hidden_template):
            client.delete(f"/api/user_template/{template['id']}", headers=auth_headers(access_token))
        for group in (allowed_group, hidden_group):
            delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


@pytest.mark.parametrize(
    ("path", "item", "list_key"),
    [
        pytest.param("/api/groups", "hidden_group", "groups", id="groups"),
        pytest.param("/api/groups/simple", "hidden_group", "groups", id="groups-simple"),
        pytest.param("/api/user_templates", "hidden_template", None, id="templates"),
        pytest.param("/api/user_templates/simple", "hidden_template", "templates", id="templates-simple"),
    ],
)
def test_listing_only_disallowed_ids_returns_nothing(restricted_catalog, path, item, list_key):
    response = client.get(
        path,
        headers=auth_headers(restricted_catalog["token"]),
        params={"ids": [restricted_catalog[item]["id"]]},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    items = body if list_key is None else body[list_key]
    assert items == []
    if list_key is not None:
        assert body["total"] == 0


@pytest.mark.parametrize("action", ["delete", "disable"])
def test_bulk_template_action_on_disallowed_ids_touches_nothing(access_token, restricted_catalog, action):
    response = client.post(
        f"/api/user_templates/bulk/{action}",
        headers=auth_headers(restricted_catalog["token"]),
        json={"ids": [restricted_catalog["hidden_template"]["id"]]},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    for key in ("allowed_template", "hidden_template"):
        template = client.get(
            f"/api/user_template/{restricted_catalog[key]['id']}",
            headers=auth_headers(access_token),
        )
        assert template.status_code == status.HTTP_200_OK
        assert template.json()["is_disabled"] is False


def test_role_with_empty_group_allowlist_lists_no_groups(access_token):
    core = create_core(access_token)
    group = create_group(access_token)
    role = _create_role(
        access_token,
        {"groups": {"read": True}},
        access={"allowed_group_ids": []},
    )
    admin = create_admin(access_token, role_id=role["id"])
    try:
        response = client.get("/api/groups", headers=auth_headers(_login(admin["username"], admin["password"])))

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["groups"] == []
        assert response.json()["total"] == 0
    finally:
        delete_admin(access_token, admin["username"])
        _delete_role(access_token, role["id"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])

"""Regression tests: per-user node stats must respect the caller's users.read scope."""

import pytest
from fastapi import status

from tests.api import client
from tests.api.helpers import auth_headers, create_admin, create_user, delete_admin, unique_name

SCOPE_OWN = {"scope": 1}
SCOPE_ALL = {"scope": 2}

# Can see node stats and its own users only.
STATS_OWN_USERS = {"nodes": {"stats": True}, "users": {"read": SCOPE_OWN, "create": True}}
# Can see node stats and every user.
STATS_ALL_USERS = {"nodes": {"stats": True}, "users": {"read": SCOPE_ALL, "create": True}}
# Can see node stats but has no users.read at all, which on its own means "unrestricted".
STATS_NO_USERS = {"nodes": {"stats": True}}

# (path, resolves): nodes are offline in tests, so only the all-nodes route still answers 200
# once the user is resolved; the per-node routes then fail on the missing node instead.
NODE_STATS_ROUTES = [
    pytest.param("/api/node/online_stats/{user_id}/ip", True, id="all-nodes-ips"),
    pytest.param("/api/node/1/online_stats/{user_id}", False, id="node-online-stats"),
    pytest.param("/api/node/1/online_stats/{user_id}/ip", False, id="node-ips"),
]


def _login(username: str, password: str) -> str:
    response = client.post(
        "/api/admin/token",
        data={"username": username, "password": password, "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access_token"]


def _create_role(access_token: str, permissions: dict) -> dict:
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("role_node_stats"),
            "permissions": permissions,
            "limits": {},
            "features": {},
            "access": {},
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def _delete_role(access_token: str, role_id: int) -> None:
    client.delete(f"/api/admin-role/{role_id}", headers=auth_headers(access_token))


@pytest.fixture
def stats_actor(access_token):
    """Build a non-owner admin with the given permissions, plus a user that admin does not own."""
    created = []

    def _build(permissions: dict) -> dict:
        role = _create_role(access_token, permissions)
        actor = create_admin(access_token, role_id=role["id"])
        target_user = create_user(access_token)
        created.append((role, actor, target_user))
        return {"actor": actor, "token": _login(actor["username"], actor["password"]), "target_user": target_user}

    yield _build

    for role, actor, target_user in created:
        client.delete(f"/api/user/by-id/{target_user['id']}", headers=auth_headers(access_token))
        delete_admin(access_token, actor["username"])
        _delete_role(access_token, role["id"])


def _assert_user_was_resolved(response, resolves: bool) -> None:
    """The ownership check passed: either the route answered or it failed on the absent node."""
    if resolves:
        assert response.status_code == status.HTTP_200_OK, response.text
    elif response.status_code == status.HTTP_404_NOT_FOUND:
        assert response.json()["detail"] != "User not found", response.text


@pytest.mark.parametrize(("path", "_resolves"), NODE_STATS_ROUTES)
def test_stats_caller_with_users_read_own_cannot_reach_a_foreign_user(stats_actor, path, _resolves):
    context = stats_actor(STATS_OWN_USERS)

    response = client.get(path.format(user_id=context["target_user"]["id"]), headers=auth_headers(context["token"]))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "User not found"


@pytest.mark.parametrize(("path", "_resolves"), NODE_STATS_ROUTES)
def test_stats_caller_without_users_read_is_refused(stats_actor, path, _resolves):
    # A missing users.read action resolves to an unrestricted scope, so the ownership check alone
    # would let such a caller read the stats of every user.
    context = stats_actor(STATS_NO_USERS)

    response = client.get(path.format(user_id=context["target_user"]["id"]), headers=auth_headers(context["token"]))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "users.read" in response.json()["detail"]


@pytest.mark.parametrize(("path", "resolves"), NODE_STATS_ROUTES)
def test_stats_caller_with_users_read_own_reaches_its_own_user(stats_actor, path, resolves):
    context = stats_actor(STATS_OWN_USERS)
    own_user = create_user(context["token"])
    try:
        response = client.get(path.format(user_id=own_user["id"]), headers=auth_headers(context["token"]))

        _assert_user_was_resolved(response, resolves)
    finally:
        client.delete(f"/api/user/by-id/{own_user['id']}", headers=auth_headers(context["token"]))


@pytest.mark.parametrize("permissions", [None, STATS_ALL_USERS], ids=["owner", "users-read-all"])
@pytest.mark.parametrize(("path", "resolves"), NODE_STATS_ROUTES)
def test_stats_callers_that_may_read_the_user_are_not_refused(access_token, stats_actor, path, resolves, permissions):
    context = stats_actor(STATS_ALL_USERS)  # its user belongs to another admin
    token = access_token if permissions is None else context["token"]

    response = client.get(path.format(user_id=context["target_user"]["id"]), headers=auth_headers(token))

    _assert_user_was_resolved(response, resolves)

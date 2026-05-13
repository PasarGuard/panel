"""Tests for bulk proxy settings changes in this PR.

Key changes tested:
- app/operation/user.py: bulk_modify_proxy_settings now returns 400 when method is None
- app/db/crud/bulk.py: flow update logic removed (only method is supported)
- Endpoint: POST /api/users/bulk/proxy_settings
"""
from fastapi import status

from tests.api import client
from tests.api.helpers import (
    create_core,
    create_group,
    create_user,
    delete_core,
    delete_group,
    delete_user,
    unique_name,
)


def _setup_groups(access_token: str, count: int = 1):
    core = create_core(access_token)
    groups = [create_group(access_token, name=unique_name(f"bps_group_{idx}")) for idx in range(count)]
    return core, groups


def _cleanup(access_token: str, core: dict, groups: list, users: list):
    for user in users:
        delete_user(access_token, user["username"])
    for group in groups:
        delete_group(access_token, group["id"])
    delete_core(access_token, core["id"])


def _auth(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


# ---------------------------------------------------------------------------
# Validation: method is now required
# ---------------------------------------------------------------------------


def test_bulk_proxy_settings_empty_body_returns_400(access_token):
    """No proxy settings provided at all should result in 400."""
    response = client.post(
        "/api/users/bulk/proxy_settings",
        headers=_auth(access_token),
        json={},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_bulk_proxy_settings_null_method_returns_400(access_token):
    """Explicitly null method should result in 400."""
    response = client.post(
        "/api/users/bulk/proxy_settings",
        headers=_auth(access_token),
        json={"method": None},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_bulk_proxy_settings_error_message_is_informative(access_token):
    """The 400 error response body should describe the problem."""
    response = client.post(
        "/api/users/bulk/proxy_settings",
        headers=_auth(access_token),
        json={},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    detail = body.get("detail", "")
    assert "proxy" in detail.lower() or "settings" in detail.lower()


# ---------------------------------------------------------------------------
# Flow field removed — sending only flow now returns 400 (method missing)
# or 422 (unknown field)
# ---------------------------------------------------------------------------


def test_bulk_proxy_settings_flow_only_not_accepted(access_token):
    """Sending only a flow value (no method) must not succeed.

    After this PR, flow is removed from BulkUsersProxy. The endpoint should
    return 400 (no supported proxy settings provided) or 422 (validation error).
    """
    response = client.post(
        "/api/users/bulk/proxy_settings",
        headers=_auth(access_token),
        json={"flow": "xtls-rprx-vision"},
    )
    assert response.status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ), f"Expected 400 or 422 when only flow is provided, got {response.status_code}"


# ---------------------------------------------------------------------------
# Successful operations
# ---------------------------------------------------------------------------


def test_bulk_proxy_settings_valid_method_succeeds(access_token):
    """A valid method should be accepted and return 200."""
    core, groups = _setup_groups(access_token, 1)
    users = [
        create_user(
            access_token,
            group_ids=[groups[0]["id"]],
            payload={"username": unique_name("bps_ok1")},
        ),
        create_user(
            access_token,
            group_ids=[groups[0]["id"]],
            payload={"username": unique_name("bps_ok2")},
        ),
    ]
    try:
        response = client.post(
            "/api/users/bulk/proxy_settings",
            headers=_auth(access_token),
            json={"method": "aes-256-gcm"},
        )
        assert response.status_code == status.HTTP_200_OK
    finally:
        _cleanup(access_token, core, groups, users)


def test_bulk_proxy_settings_applies_method_to_user(access_token):
    """The chosen method should be persisted on the user's proxy_settings."""
    core, groups = _setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("bps_apply")},
    )
    try:
        client.post(
            "/api/users/bulk/proxy_settings",
            headers=_auth(access_token),
            json={"method": "aes-128-gcm", "users": [user["username"]]},
        )
        get_resp = client.get(
            f"/api/user/{user['username']}",
            headers=_auth(access_token),
        )
        assert get_resp.status_code == status.HTTP_200_OK
        updated = get_resp.json()
        assert updated["proxy_settings"]["shadowsocks"]["method"] == "aes-128-gcm"
    finally:
        _cleanup(access_token, core, groups, [user])


def test_bulk_proxy_settings_all_valid_methods_accepted(access_token):
    """All four ShadowsocksMethods values must be individually accepted."""
    valid_methods = [
        "aes-128-gcm",
        "aes-256-gcm",
        "chacha20-ietf-poly1305",
        "xchacha20-poly1305",
    ]
    for method in valid_methods:
        response = client.post(
            "/api/users/bulk/proxy_settings",
            headers=_auth(access_token),
            json={"method": method},
        )
        assert response.status_code == status.HTTP_200_OK, (
            f"Method '{method}' should be accepted but got {response.status_code}"
        )


def test_bulk_proxy_settings_dry_run(access_token):
    """dry_run=True should return affected count without persisting changes."""
    core, groups = _setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("bps_dry")},
    )
    try:
        response = client.post(
            "/api/users/bulk/proxy_settings",
            headers=_auth(access_token),
            json={"method": "aes-256-gcm", "dry_run": True},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "affected_users" in data
        assert data.get("dry_run") is True
        assert data["affected_users"] >= 1
    finally:
        _cleanup(access_token, core, groups, [user])


def test_bulk_proxy_settings_invalid_method_returns_422(access_token):
    """An invalid cipher string must return 422 Unprocessable Entity."""
    response = client.post(
        "/api/users/bulk/proxy_settings",
        headers=_auth(access_token),
        json={"method": "totally-invalid-cipher"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
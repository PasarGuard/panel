"""Tests for /api/mcp endpoints and the /mcp Streamable HTTP transport (auth + RBAC)."""

import pytest
from fastapi import status

from app.models.settings import MCP
from tests.api import client
from tests.api.helpers import auth_headers, create_admin, delete_admin, unique_name

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _login(username: str, password: str) -> str:
    response = client.post(
        "/api/admin/token",
        data={"username": username, "password": password, "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access_token"]


def _rpc(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return payload


def _mcp_post(headers: dict, body: dict):
    return client.post("/mcp", headers={**MCP_HEADERS, **headers}, json=body)


def _tool_names(response) -> set[str]:
    assert response.status_code == status.HTTP_200_OK, response.text
    data = response.json()
    assert "result" in data, data
    return {tool["name"] for tool in data["result"]["tools"]}


@pytest.fixture
def mcp_config(monkeypatch: pytest.MonkeyPatch):
    """Override cached MCP settings for the MCP layer."""

    def _apply(**kwargs):
        settings = MCP(**kwargs)

        async def _fake():
            return settings

        for target in (
            "app.mcp.auth.mcp_settings",
            "app.mcp.registry.mcp_settings",
            "app.mcp.server.mcp_settings",
            "app.mcp.oauth.mcp_settings",
        ):
            monkeypatch.setattr(target, _fake)
        return settings

    return _apply


@pytest.fixture
def role_with_mcp(access_token):
    """Non-owner role with mcp.connect and read-only user access."""
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("mcp_role"),
            "permissions": {
                "mcp": {"read": True, "connect": True},
                "users": {"read": {"scope": 2}, "read_simple": {"scope": 2}},
                "system": {"read": True},
                "api_keys": {"create": True, "read": {"scope": 1}},
            },
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    role = response.json()
    yield role
    client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


# ---------------------------------------------------------------------------
# /api/mcp settings and tool catalog
# ---------------------------------------------------------------------------


def test_owner_can_read_and_update_mcp_settings(access_token):
    response = client.get("/api/mcp/settings", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["endpoint_path"] == "/mcp"
    assert data["tools_total"] > 0
    original = {"enable": data["enable"], "read_only": data["read_only"], "disabled_tools": data["disabled_tools"]}

    try:
        update = client.put(
            "/api/mcp/settings",
            headers=auth_headers(access_token),
            json={"enable": True, "read_only": True, "disabled_tools": ["remove_user"]},
        )
        assert update.status_code == status.HTTP_200_OK, update.text
        updated = update.json()
        assert updated["enable"] is True
        assert updated["read_only"] is True
        assert updated["disabled_tools"] == ["remove_user"]
        assert updated["tools_enabled"] < updated["tools_total"]

        again = client.get("/api/mcp/settings", headers=auth_headers(access_token)).json()
        assert again["enable"] is True and again["disabled_tools"] == ["remove_user"]
    finally:
        restore = client.put("/api/mcp/settings", headers=auth_headers(access_token), json=original)
        assert restore.status_code == status.HTTP_200_OK


def test_unknown_tool_in_disabled_tools_is_rejected(access_token):
    response = client.put(
        "/api/mcp/settings",
        headers=auth_headers(access_token),
        json={"disabled_tools": ["not_a_tool"]},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "not_a_tool" in response.json()["detail"]


def test_tool_catalog_reports_permissions_and_availability(access_token):
    response = client.get("/api/mcp/tools", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == len(data["tools"])
    by_name = {tool["name"]: tool for tool in data["tools"]}
    assert by_name["remove_user"]["permissions"] == [{"resource": "users", "action": "delete", "scope_all": False}]
    assert by_name["remove_user"]["method"] == "DELETE"
    assert by_name["create_role"]["owner_only"] is True
    assert by_name["remove_user"]["read_only"] is False
    assert by_name["remove_user"]["destructive"] is True
    assert by_name["get_users"]["read_only"] is True
    assert all(tool["allowed"] for tool in data["tools"])  # owner


def test_operator_without_mcp_permission_is_denied(access_token):
    operator = create_admin(access_token, role_id=3)
    token = _login(operator["username"], operator["password"])
    try:
        assert client.get("/api/mcp/settings", headers=auth_headers(token)).status_code == status.HTTP_403_FORBIDDEN
        assert client.get("/api/mcp/tools", headers=auth_headers(token)).status_code == status.HTTP_403_FORBIDDEN
        assert (
            client.put("/api/mcp/settings", headers=auth_headers(token), json={"enable": True}).status_code
            == status.HTTP_403_FORBIDDEN
        )
    finally:
        delete_admin(access_token, operator["username"])


def test_role_with_mcp_read_can_view_but_not_update(access_token, role_with_mcp):
    admin = create_admin(access_token, role_id=role_with_mcp["id"])
    token = _login(admin["username"], admin["password"])
    try:
        tools = client.get("/api/mcp/tools", headers=auth_headers(token))
        assert tools.status_code == status.HTTP_200_OK
        by_name = {tool["name"]: tool for tool in tools.json()["tools"]}
        assert by_name["get_users"]["allowed"] is True
        assert by_name["remove_user"]["allowed"] is False
        assert by_name["get_admins"]["allowed"] is False
        assert (
            client.put("/api/mcp/settings", headers=auth_headers(token), json={"enable": True}).status_code
            == status.HTTP_403_FORBIDDEN
        )
    finally:
        delete_admin(access_token, admin["username"])


# ---------------------------------------------------------------------------
# /mcp transport
# ---------------------------------------------------------------------------


def test_mcp_endpoint_is_404_when_disabled(access_token, mcp_config):
    mcp_config(enable=False)
    response = _mcp_post(auth_headers(access_token), _rpc("tools/list"))
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_mcp_endpoint_requires_credentials(mcp_config):
    mcp_config(enable=True)
    response = _mcp_post({}, _rpc("tools/list"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "www-authenticate" in {k.lower() for k in response.headers}

    response = _mcp_post({"Authorization": "Bearer not-a-token"}, _rpc("tools/list"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_owner_lists_and_calls_tools_with_jwt(access_token, mcp_config):
    mcp_config(enable=True, disabled_tools=[])
    names = _tool_names(_mcp_post(auth_headers(access_token), _rpc("tools/list")))
    assert {"get_system_stats", "get_users", "create_user", "remove_user", "modify_node", "modify_hosts"} <= names

    call = _mcp_post(
        auth_headers(access_token),
        _rpc("tools/call", {"name": "get_system_stats", "arguments": {}}, request_id=2),
    )
    assert call.status_code == status.HTTP_200_OK, call.text
    result = call.json()["result"]
    assert result.get("isError") is not True, result
    assert "structuredContent" in result or result["content"]
    payload = result.get("structuredContent") or result["content"][0]
    assert "version" in str(payload)


def test_read_only_mode_hides_and_blocks_write_tools(access_token, mcp_config):
    mcp_config(enable=True, read_only=True)
    names = _tool_names(_mcp_post(auth_headers(access_token), _rpc("tools/list")))
    assert "get_users" in names
    assert "create_user" not in names and "remove_user" not in names

    call = _mcp_post(
        auth_headers(access_token),
        _rpc("tools/call", {"name": "remove_user", "arguments": {"username": "nobody"}}, request_id=3),
    )
    assert call.status_code == status.HTTP_200_OK, call.text
    result = call.json()["result"]
    assert result.get("isError") is True
    assert "read-only" in result["content"][0]["text"]


def test_disabled_tool_is_hidden_and_blocked(access_token, mcp_config):
    mcp_config(enable=True, disabled_tools=["get_admins"])
    names = _tool_names(_mcp_post(auth_headers(access_token), _rpc("tools/list")))
    assert "get_admins" not in names

    call = _mcp_post(
        auth_headers(access_token),
        _rpc("tools/call", {"name": "get_admins", "arguments": {}}, request_id=4),
    )
    result = call.json()["result"]
    assert result.get("isError") is True
    assert "disabled" in result["content"][0]["text"]


def test_operator_without_connect_permission_gets_403(access_token, mcp_config):
    mcp_config(enable=True)
    operator = create_admin(access_token, role_id=3)
    token = _login(operator["username"], operator["password"])
    try:
        response = _mcp_post(auth_headers(token), _rpc("tools/list"))
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "mcp.connect" in response.json()["detail"]
    finally:
        delete_admin(access_token, operator["username"])


def test_tool_visibility_and_enforcement_follow_role_permissions(access_token, mcp_config, role_with_mcp):
    mcp_config(enable=True)
    admin = create_admin(access_token, role_id=role_with_mcp["id"])
    token = _login(admin["username"], admin["password"])
    try:
        names = _tool_names(_mcp_post(auth_headers(token), _rpc("tools/list")))
        assert {"get_users", "get_user", "get_system_stats"} <= names
        assert "remove_user" not in names
        assert "get_admins" not in names
        assert "create_user" not in names

        # Even if a client guesses a hidden tool name, the permission check blocks it.
        call = _mcp_post(
            auth_headers(token),
            _rpc("tools/call", {"name": "get_admins", "arguments": {}}, request_id=5),
        )
        result = call.json()["result"]
        assert result.get("isError") is True
        assert "admins.read" in result["content"][0]["text"]

        # Allowed tool works end to end.
        call = _mcp_post(
            auth_headers(token),
            _rpc("tools/call", {"name": "get_users", "arguments": {"limit": 5}}, request_id=6),
        )
        result = call.json()["result"]
        assert result.get("isError") is not True, result
    finally:
        delete_admin(access_token, admin["username"])


def test_api_key_authenticates_mcp_session(access_token, mcp_config, role_with_mcp):
    mcp_config(enable=True)
    admin = create_admin(access_token, role_id=role_with_mcp["id"])
    admin_token = _login(admin["username"], admin["password"])
    try:
        # Key inheriting the role: sees exactly what the role allows.
        inherited = client.post(
            "/api/api_key",
            headers=auth_headers(admin_token),
            json={"name": unique_name("mcp_key")},
        )
        assert inherited.status_code == status.HTTP_201_CREATED, inherited.text
        inherited_key = inherited.json()["api_key"]
        names = _tool_names(_mcp_post({"Authorization": f"Bearer {inherited_key}"}, _rpc("tools/list")))
        assert {"get_users", "get_user", "get_system_stats"} <= names
        assert "remove_user" not in names

        # Key with its own (narrower) permission snapshot: Bearer pg_key_, ApiKey and X-Api-Key all work.
        scoped = client.post(
            "/api/api_key",
            headers=auth_headers(admin_token),
            json={
                "name": unique_name("mcp_scoped_key"),
                "inherit_permissions": False,
                "permissions": {"mcp": {"connect": True}, "system": {"read": True}},
            },
        )
        assert scoped.status_code == status.HTTP_201_CREATED, scoped.text
        scoped_key = scoped.json()["api_key"]
        for headers in (
            {"Authorization": f"Bearer {scoped_key}"},
            {"Authorization": f"ApiKey {scoped_key}"},
            {"X-Api-Key": scoped_key},
        ):
            names = _tool_names(_mcp_post(headers, _rpc("tools/list")))
            assert {"get_system_stats", "get_inbounds", "get_current_admin"} <= names, names
            assert not {"get_users", "create_user", "get_admins"} & names, names
            call = _mcp_post(headers, _rpc("tools/call", {"name": "get_current_admin", "arguments": {}}, request_id=7))
            result = call.json()["result"]
            assert result.get("isError") is not True, result
            assert admin["username"] in result["content"][0]["text"]

        # A key snapshot without mcp.connect cannot open a session at all.
        no_connect = client.post(
            "/api/api_key",
            headers=auth_headers(admin_token),
            json={
                "name": unique_name("mcp_no_connect"),
                "inherit_permissions": False,
                "permissions": {"system": {"read": True}},
            },
        )
        assert no_connect.status_code == status.HTTP_201_CREATED, no_connect.text
        response = _mcp_post({"X-Api-Key": no_connect.json()["api_key"]}, _rpc("tools/list"))
        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, admin["username"])


# ---------------------------------------------------------------------------
# Defaults, destructive confirmation, OAuth
# ---------------------------------------------------------------------------


def test_sensitive_tools_are_disabled_by_default(access_token):
    response = client.get("/api/mcp/settings", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "modify_settings" in data["default_disabled_tools"]
    assert "get_users" not in data["default_disabled_tools"]
    assert data["oauth"] is True


def test_destructive_tool_requires_confirm(access_token, mcp_config):
    mcp_config(enable=True)
    call = _mcp_post(
        auth_headers(access_token),
        _rpc("tools/call", {"name": "remove_user", "arguments": {"username": "nobody"}}, request_id=8),
    )
    result = call.json()["result"]
    assert result.get("isError") is True
    assert "confirm=true" in result["content"][0]["text"]

    call = _mcp_post(
        auth_headers(access_token),
        _rpc("tools/call", {"name": "remove_user", "arguments": {"username": "nobody", "confirm": True}}, request_id=9),
    )
    result = call.json()["result"]
    assert result.get("isError") is True
    assert "not found" in result["content"][0]["text"].lower()


def _pkce_pair() -> tuple[str, str]:
    import base64
    import hashlib
    import secrets

    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def test_oauth_flow_issues_tokens_that_open_mcp_sessions(access_token, mcp_config, role_with_mcp):
    mcp_config(enable=True, oauth=True)
    admin = create_admin(access_token, role_id=role_with_mcp["id"])
    try:
        metadata = client.get("/.well-known/oauth-protected-resource/mcp")
        assert metadata.status_code == status.HTTP_200_OK
        assert metadata.json()["resource"].endswith("/mcp")
        server_metadata = client.get("/.well-known/oauth-authorization-server").json()
        assert server_metadata["authorization_endpoint"].endswith("/mcp/oauth/authorize")

        registered = client.post(
            "/mcp/oauth/register",
            json={
                "client_name": "Test client",
                "redirect_uris": ["http://localhost:9999/callback"],
                "token_endpoint_auth_method": "none",
            },
        )
        assert registered.status_code == status.HTTP_201_CREATED, registered.text
        client_id = registered.json()["client_id"]

        verifier, challenge = _pkce_pair()
        authorize = client.get(
            "/mcp/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://localhost:9999/callback",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "xyz",
            },
            follow_redirects=False,
        )
        assert authorize.status_code == status.HTTP_302_FOUND, authorize.text
        consent_url = authorize.headers["location"]
        assert "#/mcp/authorize?request=" in consent_url
        request_token = consent_url.split("request=", 1)[1]

        admin_token = _login(admin["username"], admin["password"])
        info = client.get(
            "/api/mcp/oauth/request", params={"request": request_token}, headers=auth_headers(admin_token)
        )
        assert info.status_code == status.HTTP_200_OK, info.text
        assert info.json()["client_name"] == "Test client"

        operator = create_admin(access_token, role_id=3)
        operator_token = _login(operator["username"], operator["password"])
        denied = client.post(
            "/api/mcp/oauth/consent",
            json={"request": request_token, "approve": True},
            headers=auth_headers(operator_token),
        )
        assert denied.status_code == status.HTTP_403_FORBIDDEN
        delete_admin(access_token, operator["username"])

        rejected = client.post(
            "/api/mcp/oauth/consent",
            json={"request": request_token, "approve": False},
            headers=auth_headers(admin_token),
        )
        assert rejected.status_code == status.HTTP_200_OK
        assert "error=access_denied" in rejected.json()["redirect_url"]

        too_much = client.post(
            "/api/mcp/oauth/consent",
            json={"request": request_token, "approve": True, "permissions": {"admins": {"delete": True}}},
            headers=auth_headers(admin_token),
        )
        assert too_much.status_code == status.HTTP_403_FORBIDDEN

        granted = client.post(
            "/api/mcp/oauth/consent",
            json={
                "request": request_token,
                "approve": True,
                "permissions": {"users": {"read": {"scope": 2}}},
            },
            headers=auth_headers(admin_token),
        )
        assert granted.status_code == status.HTTP_200_OK, granted.text
        location = granted.json()["redirect_url"]
        assert location.startswith("http://localhost:9999/callback?") and "state=xyz" in location
        code = dict(part.split("=", 1) for part in location.split("?", 1)[1].split("&"))["code"]

        token = client.post(
            "/mcp/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost:9999/callback",
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )
        assert token.status_code == status.HTTP_200_OK, token.text
        tokens = token.json()
        assert tokens["access_token"].startswith("pg_key_")
        assert not tokens.get("refresh_token")

        names = _tool_names(_mcp_post({"Authorization": f"Bearer {tokens['access_token']}"}, _rpc("tools/list")))
        assert "get_users" in names
        assert "get_system_stats" not in names

        keys = client.get("/api/api_keys", headers=auth_headers(admin_token)).json()["api_keys"]
        created = [key for key in keys if key["name"].startswith("Test client")]
        assert len(created) == 1
        assert created[0]["inherit_permissions"] is False
        assert created[0]["permissions"]["mcp"]["connect"] is True

        removed = client.delete(f"/api/api_key/{created[0]['id']}", headers=auth_headers(access_token))
        assert removed.status_code == status.HTTP_204_NO_CONTENT
        revoked = _mcp_post({"Authorization": f"Bearer {tokens['access_token']}"}, _rpc("tools/list"))
        assert revoked.status_code == status.HTTP_401_UNAUTHORIZED
    finally:
        delete_admin(access_token, admin["username"])


def test_oauth_is_hidden_when_disabled(mcp_config):
    mcp_config(enable=True, oauth=False)
    assert client.get("/.well-known/oauth-authorization-server").status_code == status.HTTP_404_NOT_FOUND
    assert (
        client.post("/mcp/oauth/register", json={"redirect_uris": ["http://x/cb"]}).status_code
        == status.HTTP_404_NOT_FOUND
    )

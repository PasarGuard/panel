import json

from fastapi import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.db import GetDB
from app.db.crud.api_key import get_api_key_by_raw_key
from app.db.crud.mcp import api_key_mcp_settings, get_admin_mcp_settings
from app.models.admin import AdminDetails, AdminStatus
from app.models.mcp import MCPKeySettings, MCPSettings
from app.operation.permissions import PermissionDenied, enforce_permission
from app.routers.authentication import get_admin, get_admin_from_api_key

from .registry import ACCESS_STATE_KEY, ADMIN_STATE_KEY, MCP_PATH, MCPAccess

API_KEY_PREFIX = "pg_key_"


def extract_credentials(request: Request) -> tuple[str | None, str | None]:
    """Return (bearer_token, api_key); accepts Bearer JWT, Bearer/ApiKey pg_key_ and X-Api-Key like the REST API."""
    x_api_key = request.headers.get("X-Api-Key")
    if x_api_key and x_api_key.strip():
        return None, x_api_key.strip()

    auth = request.headers.get("Authorization")
    if not auth:
        return None, None

    scheme, _, credentials = auth.partition(" ")
    scheme = scheme.lower().strip()
    credentials = credentials.strip()
    if not scheme or not credentials:
        return None, None
    if scheme == "apikey" or (scheme == "bearer" and credentials.startswith(API_KEY_PREFIX)):
        return None, credentials
    if scheme == "bearer":
        return credentials, None
    return None, None


async def authenticate_mcp_request(request: Request) -> tuple[AdminDetails | None, MCPKeySettings | None]:
    """Resolve the admin behind the request and, for API keys, the key's own MCP settings."""
    token, api_key = extract_credentials(request)
    if not token and not api_key:
        return None, None

    async with GetDB() as db:
        if api_key:
            admin = await get_admin_from_api_key(db, api_key)
            if admin is None:
                return None, None
            db_key = await get_api_key_by_raw_key(db, api_key)
            return admin, api_key_mcp_settings(db_key) if db_key is not None else None
        try:
            return await get_admin(db, token), None
        except HTTPException:
            return None, None


async def load_mcp_access(admin: AdminDetails, key_settings: MCPKeySettings | None = None) -> MCPAccess:
    if admin.id is None:
        return MCPAccess.build(MCPSettings())
    async with GetDB() as db:
        settings = await get_admin_mcp_settings(db, admin.id)
    return MCPAccess.build(settings, key_settings)


async def _send_json(send: Send, status: int, payload: dict, headers: dict[str, str] | None = None) -> None:
    body = json.dumps(payload).encode()
    raw_headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode(), value.encode()))
    await send({"type": "http.response.start", "status": status, "headers": raw_headers})
    await send({"type": "http.response.body", "body": body})


class MCPAuthMiddleware:
    """ASGI wrapper that authenticates the admin and enforces mcp.connect before the MCP app runs."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        admin, key_settings = await authenticate_mcp_request(request)
        if admin is None:
            metadata_url = f"{request.url.scheme}://{request.url.netloc}/.well-known/oauth-protected-resource{MCP_PATH}"
            challenge = f'Bearer realm="PasarGuard MCP", resource_metadata="{metadata_url}"'
            await _send_json(send, 401, {"detail": "Could not validate credentials"}, {"WWW-Authenticate": challenge})
            return
        if admin.status == AdminStatus.disabled:
            await _send_json(send, 403, {"detail": "your account has been disabled"})
            return
        try:
            enforce_permission(admin, "mcp", "connect")
        except PermissionDenied as exc:
            await _send_json(send, 403, {"detail": str(exc)})
            return

        access = await load_mcp_access(admin, key_settings)
        if not access.enable:
            await _send_json(send, 403, {"detail": "MCP is turned off for this account"})
            return

        state = scope.setdefault("state", {})
        state[ADMIN_STATE_KEY] = admin
        state[ACCESS_STATE_KEY] = access
        await self.app(scope, receive, send)

import json

from fastapi import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.db import GetDB
from app.models.admin import AdminDetails, AdminStatus
from app.operation.permissions import PermissionDenied, enforce_permission
from app.routers.authentication import get_admin, get_admin_from_api_key
from app.settings import mcp_settings

from .registry import ADMIN_STATE_KEY, MCP_PATH

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


async def authenticate_mcp_request(request: Request) -> AdminDetails | None:
    token, api_key = extract_credentials(request)
    if not token and not api_key:
        return None

    async with GetDB() as db:
        if api_key:
            return await get_admin_from_api_key(db, api_key)
        try:
            return await get_admin(db, token)
        except HTTPException:
            return None


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

        settings = await mcp_settings()
        if not settings.enable:
            await _send_json(send, 404, {"detail": "MCP server is disabled"})
            return

        request = Request(scope, receive)
        admin = await authenticate_mcp_request(request)
        if admin is None:
            challenge = 'Bearer realm="PasarGuard MCP"'
            if settings.oauth:
                metadata_url = (
                    f"{request.url.scheme}://{request.url.netloc}/.well-known/oauth-protected-resource{MCP_PATH}"
                )
                challenge += f', resource_metadata="{metadata_url}"'
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

        scope.setdefault("state", {})[ADMIN_STATE_KEY] = admin
        await self.app(scope, receive, send)

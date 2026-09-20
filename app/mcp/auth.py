from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.db import GetDB
from app.db.crud.admin import build_admin_details
from app.db.crud.api_key import get_api_key_by_raw_key
from app.db.crud.mcp import api_key_mcp_settings, get_admin_mcp_settings
from app.models.admin import AdminDetails, AdminStatus
from app.models.mcp import MCPSettings
from app.operation.permissions import PermissionDenied, enforce_permission
from app.routers.authentication import apply_api_key_permissions, get_admin

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


async def authenticate_mcp_request(request: Request) -> tuple[AdminDetails | None, MCPAccess | None]:
    """Resolve the admin behind the request and what their MCP settings (and the key's, if any) allow."""
    token, api_key = extract_credentials(request)
    if not token and not api_key:
        return None, None

    async with GetDB() as db:
        if api_key:
            db_key = await get_api_key_by_raw_key(db, api_key)
            if db_key is None or not db_key.is_usable:
                return None, None
            admin = apply_api_key_permissions(build_admin_details(db_key.admin), db_key)
            settings = MCPSettings.model_validate(db_key.admin.mcp or {})
            return admin, MCPAccess.build(settings, api_key_mcp_settings(db_key))
        try:
            admin = await get_admin(db, token)
        except HTTPException:
            return None, None
        if admin is None:
            return None, None
        settings = await get_admin_mcp_settings(db, admin.id) if admin.id is not None else MCPSettings()
        return admin, MCPAccess.build(settings)


class MCPAuthMiddleware:
    """ASGI wrapper that authenticates the admin and enforces mcp.connect before the MCP app runs."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        admin, access = await authenticate_mcp_request(request)
        if admin is None or access is None:
            metadata_url = f"{request.url.scheme}://{request.url.netloc}/.well-known/oauth-protected-resource{MCP_PATH}"
            challenge = f'Bearer realm="PasarGuard MCP", resource_metadata="{metadata_url}"'
            response = JSONResponse(
                {"detail": "Could not validate credentials"}, status_code=401, headers={"WWW-Authenticate": challenge}
            )
        elif admin.status == AdminStatus.disabled:
            response = JSONResponse({"detail": "your account has been disabled"}, status_code=403)
        else:
            try:
                enforce_permission(admin, "mcp", "connect")
            except PermissionDenied as exc:
                response = JSONResponse({"detail": str(exc)}, status_code=403)
            else:
                if not access.enable:
                    response = JSONResponse({"detail": "MCP is turned off for this account"}, status_code=403)
                else:
                    state = scope.setdefault("state", {})
                    state[ADMIN_STATE_KEY] = admin
                    state[ACCESS_STATE_KEY] = access
                    await self.app(scope, receive, send)
                    return
        await response(scope, receive, send)

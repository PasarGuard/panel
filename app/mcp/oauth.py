import secrets
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

import jwt
from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.handlers.register import RegistrationHandler
from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
)
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken, ProtectedResourceMetadata
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from app.db import GetDB
from app.db.crud.api_key import create_api_key, delete_api_key, get_api_key_by_raw_key
from app.db.crud.mcp import create_oauth_client, get_oauth_client
from app.models.admin import AdminDetails
from app.models.admin_role import MCPPermissions, RolePermissions
from app.models.api_key import APIKeyCreate
from app.routers.authentication import get_admin_from_api_key
from app.utils.jwt import get_secret_key
from config import dashboard_settings

from .registry import MCP_PATH

OAUTH_PATH = f"{MCP_PATH}/oauth"
AUTHORIZE_PATH = f"{OAUTH_PATH}/authorize"
TOKEN_PATH = f"{OAUTH_PATH}/token"
REGISTER_PATH = f"{OAUTH_PATH}/register"
AS_METADATA_PATH = "/.well-known/oauth-authorization-server"
RS_METADATA_PATH = f"/.well-known/oauth-protected-resource{MCP_PATH}"

REQUEST_TTL = 600
CODE_TTL = 300
ALGORITHM = "HS256"


async def _encode(claims: dict, ttl: int) -> str:
    now = int(time.time())
    return jwt.encode({**claims, "iat": now, "exp": now + ttl}, await get_secret_key(), algorithm=ALGORITHM)


async def _decode(token: str, typ: str) -> dict | None:
    try:
        claims = jwt.decode(token, await get_secret_key(), algorithms=[ALGORITHM], leeway=5)
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == typ else None


def _client_info(db_client) -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=db_client.client_id,
        client_secret=db_client.client_secret,
        client_name=db_client.client_name,
        redirect_uris=db_client.redirect_uris,
        grant_types=db_client.grant_types or ["authorization_code", "refresh_token"],
        token_endpoint_auth_method=db_client.token_endpoint_auth_method,
        client_id_issued_at=int(db_client.created_at.timestamp()) if db_client.created_at else None,
    )


class PanelOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    """OAuth 2.1 authorization server backed by panel admins. Access tokens are API keys."""

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with GetDB() as db:
            db_client = await get_oauth_client(db, client_id)
        return _client_info(db_client) if db_client else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        async with GetDB() as db:
            await create_oauth_client(
                db,
                client_id=client_info.client_id,
                client_name=client_info.client_name,
                client_secret=client_info.client_secret,
                redirect_uris=[str(uri) for uri in client_info.redirect_uris or []],
                grant_types=list(client_info.grant_types or []),
                token_endpoint_auth_method=client_info.token_endpoint_auth_method or "none",
            )

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        request_token = await _encode(
            {
                "typ": "mcp_authreq",
                "cid": client.client_id,
                "ru": str(params.redirect_uri),
                "rue": params.redirect_uri_provided_explicitly,
                "cc": params.code_challenge,
                "st": params.state,
                "sc": params.scopes or [],
                "res": params.resource,
            },
            REQUEST_TTL,
        )
        # The dashboard asks the signed-in admin to approve, then calls /api/mcp/oauth/consent
        return f"{dashboard_settings.path}#/mcp/authorize?{urlencode({'request': request_token})}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        claims = await _decode(authorization_code, "mcp_code")
        if not claims or claims.get("cid") != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=claims.get("sc", []),
            expires_at=float(claims["exp"]),
            client_id=client.client_id,
            code_challenge=claims["cc"],
            redirect_uri=AnyHttpUrl(claims["ru"]),
            redirect_uri_provided_explicitly=bool(claims.get("rue")),
            resource=claims.get("res"),
            subject=claims["sub"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        claims = await _decode(authorization_code.code, "mcp_code")
        if not claims:
            raise TokenError("invalid_grant", "authorization code is invalid or expired")
        # The API key created on consent is the access token; deleting the key revokes it
        return OAuthToken(access_token=claims["key"], token_type="Bearer", scope=" ".join(claims.get("sc", [])) or None)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        return None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        raise TokenError("unsupported_grant_type", "refresh is not supported; the access token does not expire")

    async def load_access_token(self, token: str) -> AccessToken | None:
        async with GetDB() as db:
            admin = await get_admin_from_api_key(db, token)
        if admin is None:
            return None
        return AccessToken(token=token, client_id="api-key", scopes=[], expires_at=None, subject=admin.username)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        async with GetDB() as db:
            db_key = await get_api_key_by_raw_key(db, token.token)
            if db_key is not None:
                await delete_api_key(db, db_key)
                await db.commit()

    async def exchange_identity_assertion(self, client, params) -> OAuthToken:
        raise TokenError("unsupported_grant_type", "identity assertion is not supported")


provider = PanelOAuthProvider()
_registration_options = ClientRegistrationOptions(enabled=True)


def _base_url(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


async def authorization_server_metadata(request: Request) -> Response:
    base = _base_url(request)
    metadata = OAuthMetadata(
        issuer=AnyHttpUrl(base),
        authorization_endpoint=AnyHttpUrl(base + AUTHORIZE_PATH),
        token_endpoint=AnyHttpUrl(base + TOKEN_PATH),
        registration_endpoint=AnyHttpUrl(base + REGISTER_PATH),
        response_types_supported=["code"],
        grant_types_supported=["authorization_code", "refresh_token"],
        token_endpoint_auth_methods_supported=["none", "client_secret_post", "client_secret_basic"],
        code_challenge_methods_supported=["S256"],
    )
    return JSONResponse(metadata.model_dump(mode="json", exclude_none=True), headers={"Cache-Control": "no-store"})


async def protected_resource_metadata(request: Request) -> Response:
    base = _base_url(request)
    metadata = ProtectedResourceMetadata(
        resource=AnyHttpUrl(base + MCP_PATH),
        authorization_servers=[AnyHttpUrl(base)],
        bearer_methods_supported=["header"],
        resource_name="PasarGuard MCP",
    )
    return JSONResponse(metadata.model_dump(mode="json", exclude_none=True), headers={"Cache-Control": "no-store"})


async def describe_request(request_token: str) -> dict | None:
    claims = await _decode(request_token, "mcp_authreq")
    if not claims:
        return None
    client = await provider.get_client(claims["cid"])
    return {"client_id": claims["cid"], "client_name": (client.client_name if client else None) or claims["cid"]}


def _redirect_with(claims: dict, query: dict) -> str:
    if claims.get("st"):
        query["state"] = claims["st"]
    separator = "&" if "?" in claims["ru"] else "?"
    return f"{claims['ru']}{separator}{urlencode(query)}"


async def grant_request(
    request_token: str, admin: AdminDetails, permissions: RolePermissions | None = None
) -> str | None:
    claims = await _decode(request_token, "mcp_authreq")
    if not claims:
        return None
    client = await provider.get_client(claims["cid"])
    client_name = (client.client_name if client else None) or "MCP client"
    if permissions is not None:
        # Every key issued here must be able to open an MCP session
        permissions.mcp = MCPPermissions(**{**(permissions.mcp or MCPPermissions()).model_dump(), "connect": True})
    async with GetDB() as db:
        raw_key, _ = await create_api_key(
            db,
            admin.id,
            APIKeyCreate(
                name=f"{client_name} {datetime.now(UTC):%Y-%m-%d %H:%M}"[:128],
                note=f"Created by MCP OAuth sign-in for {client_name}",
                permissions=permissions or RolePermissions(),
                inherit_permissions=permissions is None,
            ),
        )
        await db.commit()
    code = await _encode(
        {
            "typ": "mcp_code",
            "sub": admin.username,
            "aid": admin.id,
            "key": raw_key,
            "cid": claims["cid"],
            "cc": claims["cc"],
            "ru": claims["ru"],
            "rue": claims.get("rue", False),
            "sc": claims.get("sc", []),
            "res": claims.get("res"),
            "jti": secrets.token_hex(8),
        },
        CODE_TTL,
    )
    return _redirect_with(claims, {"code": code})


async def deny_request(request_token: str) -> str | None:
    claims = await _decode(request_token, "mcp_authreq")
    if not claims:
        return None
    return _redirect_with(claims, {"error": "access_denied"})


def oauth_routes() -> list[Route]:
    client_authenticator = ClientAuthenticator(provider)
    return [
        Route(AS_METADATA_PATH, authorization_server_metadata, methods=["GET"]),
        Route(RS_METADATA_PATH, protected_resource_metadata, methods=["GET"]),
        Route(AUTHORIZE_PATH, AuthorizationHandler(provider).handle, methods=["GET", "POST"]),
        Route(TOKEN_PATH, TokenHandler(provider, client_authenticator).handle, methods=["POST"]),
        Route(REGISTER_PATH, RegistrationHandler(provider, _registration_options).handle, methods=["POST"]),
    ]

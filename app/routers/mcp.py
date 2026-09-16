from fastapi import APIRouter, Depends, Query

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.mcp import (
    MCPOAuthConsent,
    MCPOAuthConsentResponse,
    MCPOAuthRequestInfo,
    MCPSettingsModify,
    MCPSettingsResponse,
    MCPToolsResponse,
)
from app.operation import OperatorType
from app.operation.mcp import MCPOperation
from app.utils import responses

from .authentication import require_permission

router = APIRouter(tags=["MCP"], prefix="/api/mcp", responses={401: responses._401, 403: responses._403})

mcp_operator = MCPOperation(operator_type=OperatorType.API)

ApiKeyId = Query(default=None, ge=1, description="Read or change the settings of one of your API keys instead")


@router.get("/settings", response_model=MCPSettingsResponse, responses={404: responses._404})
async def get_mcp_settings(
    api_key_id: int | None = ApiKeyId,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mcp", "read")),
):
    """MCP settings of the signed-in admin (or one of their API keys) and endpoint information."""
    return await mcp_operator.get_settings(db, admin, api_key_id)


@router.put("/settings", response_model=MCPSettingsResponse, responses={400: responses._400, 404: responses._404})
async def modify_mcp_settings(
    modify: MCPSettingsModify,
    api_key_id: int | None = ApiKeyId,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mcp", "update")),
):
    """Turn MCP on or off, allow OAuth sign-in, toggle read-only mode and disable tools for the admin or a key."""
    return await mcp_operator.modify_settings(db, admin, modify, api_key_id)


@router.get("/tools", response_model=MCPToolsResponse, responses={404: responses._404})
async def list_mcp_tools(
    api_key_id: int | None = ApiKeyId,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mcp", "read")),
):
    """Catalog of MCP tools with their REST permission mapping and availability for the admin or a key."""
    return await mcp_operator.list_tools(db, admin, api_key_id)


@router.get("/oauth/request", response_model=MCPOAuthRequestInfo, responses={400: responses._400})
async def get_mcp_oauth_request(
    request: str,
    _: AdminDetails = Depends(require_permission("mcp", "connect")),
):
    """Describe a pending OAuth authorization request so the dashboard can ask for consent."""
    return await mcp_operator.get_oauth_request(request)


@router.post("/oauth/consent", response_model=MCPOAuthConsentResponse, responses={400: responses._400})
async def mcp_oauth_consent(
    consent: MCPOAuthConsent,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mcp", "connect")),
):
    """Approve or deny a pending OAuth authorization request for the signed-in admin."""
    return await mcp_operator.consent_oauth_request(db, admin, consent)

from fastapi import APIRouter, Depends

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


@router.get("/settings", response_model=MCPSettingsResponse)
async def get_mcp_settings(
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("mcp", "read")),
):
    """MCP server settings and endpoint information."""
    return await mcp_operator.get_settings(db)


@router.put("/settings", response_model=MCPSettingsResponse, responses={400: responses._400})
async def modify_mcp_settings(
    modify: MCPSettingsModify,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("mcp", "update")),
):
    """Enable/disable the MCP server, toggle read-only mode and disable individual tools."""
    return await mcp_operator.modify_settings(db, modify)


@router.get("/tools", response_model=MCPToolsResponse)
async def list_mcp_tools(
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("mcp", "read")),
):
    """Catalog of MCP tools with their REST permission mapping and availability for the current admin."""
    return await mcp_operator.list_tools(db, admin)


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
    admin: AdminDetails = Depends(require_permission("mcp", "connect")),
):
    """Approve or deny a pending OAuth authorization request for the signed-in admin."""
    return await mcp_operator.consent_oauth_request(admin, consent)

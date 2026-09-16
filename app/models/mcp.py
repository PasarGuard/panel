from pydantic import BaseModel, ConfigDict, Field

from app.models.admin_role import RolePermissions
from app.models.settings import MCP


class MCPSettingsResponse(MCP):
    endpoint_path: str = Field(description="Path of the MCP endpoint on this panel (e.g. /mcp)")
    default_disabled_tools: list[str] = Field(default_factory=list)
    tools_total: int = 0
    tools_enabled: int = 0

    model_config = ConfigDict(from_attributes=True)


class MCPSettingsModify(BaseModel):
    enable: bool | None = None
    oauth: bool | None = None
    read_only: bool | None = None
    disabled_tools: list[str] | None = None


class MCPToolPermission(BaseModel):
    resource: str
    action: str
    scope_all: bool = False


class MCPToolInfo(BaseModel):
    name: str
    title: str
    group: str
    description: str
    method: str
    path: str
    read_only: bool
    destructive: bool
    owner_only: bool = False
    permissions: list[MCPToolPermission]
    enabled: bool = Field(description="Not disabled globally (settings.disabled_tools / read-only mode)")
    disabled_reason: str | None = Field(default=None, description="'disabled' or 'read_only' when not enabled")
    allowed: bool = Field(description="Whether the requesting admin's role permits this tool")


class MCPToolsResponse(BaseModel):
    tools: list[MCPToolInfo]
    total: int


class MCPOAuthRequestInfo(BaseModel):
    client_id: str
    client_name: str


class MCPOAuthConsent(BaseModel):
    request: str = Field(min_length=1)
    approve: bool = True
    permissions: RolePermissions | None = Field(
        default=None, description="Permissions stored on the issued key; None inherits the admin's role"
    )


class MCPOAuthConsentResponse(BaseModel):
    redirect_url: str

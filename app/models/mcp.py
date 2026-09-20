from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.mcp.catalog import DEFAULT_DISABLED_TOOLS
from app.models.admin_role import RolePermissions


def _clean_tool_names(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("disabled_tools must be a list of tool names")  # noqa: TRY004 (pydantic needs ValueError)
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("disabled_tools must be a list of tool names")  # noqa: TRY004
        name = item.strip()
        if name and name not in cleaned:
            cleaned.append(name)
    return cleaned


ToolNames = Annotated[list[str], BeforeValidator(_clean_tool_names)]


class MCPSettings(BaseModel):
    """Per-admin MCP settings, stored in admins.mcp."""

    enable: bool = Field(default=False)
    oauth: bool = Field(default=True, description="Allow OAuth sign-in for clients that cannot send an API key")
    read_only: bool = Field(default=False, description="Only expose read-only tools")
    disabled_tools: ToolNames = Field(
        default_factory=lambda: sorted(DEFAULT_DISABLED_TOOLS), description="Tool names hidden from MCP clients"
    )

    model_config = ConfigDict(from_attributes=True)


class MCPKeySettings(BaseModel):
    """Per-key MCP settings, stored in api_keys.mcp. Applied on top of the owning admin's settings."""

    enable: bool = Field(default=True)
    read_only: bool = Field(default=False)
    disabled_tools: ToolNames = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MCPSettingsResponse(MCPSettings):
    api_key_id: int | None = Field(default=None, description="Set when the response describes an API key")
    endpoint_path: str = Field(description="Path of the MCP endpoint on this panel (e.g. /mcp)")
    default_disabled_tools: list[str] = Field(default_factory=list)
    tools_total: int = 0
    tools_enabled: int = 0


class MCPSettingsModify(BaseModel):
    enable: bool | None = None
    oauth: bool | None = None
    read_only: bool | None = None
    disabled_tools: ToolNames | None = None


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
    enabled: bool = Field(description="Not disabled by the admin or key settings (disabled_tools / read-only mode)")
    disabled_reason: str | None = Field(default=None, description="'disabled' or 'read_only' when not enabled")
    allowed: bool = Field(description="Whether the requesting admin's role permits this tool")


class MCPToolsResponse(BaseModel):
    tools: list[MCPToolInfo]
    total: int


class MCPOAuthRequestInfo(BaseModel):
    client_id: str
    client_name: str
    key_name: str = Field(description="Suggested name for the API key that approving creates")


class MCPOAuthConsent(BaseModel):
    request: str = Field(min_length=1)
    approve: bool = True
    permissions: RolePermissions | None = Field(
        default=None, description="Permissions stored on the issued key; None inherits the admin's role"
    )
    mcp: MCPKeySettings | None = Field(default=None, description="MCP settings stored on the issued key")
    name: str | None = Field(default=None, min_length=1, max_length=128, description="Name of the issued key")


class MCPOAuthConsentResponse(BaseModel):
    redirect_url: str

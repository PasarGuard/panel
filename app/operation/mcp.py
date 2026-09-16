from app.db import AsyncSession
from app.db.crud.settings import get_settings, modify_settings
from app.mcp.catalog import DEFAULT_DISABLED_TOOLS
from app.mcp.oauth import deny_request, describe_request, grant_request
from app.mcp.registry import MCP_PATH, admin_can_use_tool, get_tool_specs, tool_disabled_reason
from app.models.admin import AdminDetails
from app.models.mcp import (
    MCPOAuthConsent,
    MCPOAuthConsentResponse,
    MCPOAuthRequestInfo,
    MCPSettingsModify,
    MCPSettingsResponse,
    MCPToolInfo,
    MCPToolPermission,
    MCPToolsResponse,
)
from app.models.settings import MCP, SettingsSchema
from app.nats.message import MessageTopic
from app.nats.router import router
from app.operation.api_key import _check_permissions_not_exceed_admin
from app.settings import refresh_caches

from . import BaseOperation

# Same order as the sidebar; unknown groups last
GROUP_ORDER = (
    "system",
    "users",
    "admins",
    "admin_roles",
    "api_keys",
    "nodes",
    "cores",
    "hosts",
    "groups",
    "templates",
    "client_templates",
    "hwids",
    "settings",
)


def _group_sort_key(group: str) -> tuple[int, str]:
    return (GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER), group)


class MCPOperation(BaseOperation):
    @staticmethod
    def _build_settings_response(settings: MCP) -> MCPSettingsResponse:
        specs = get_tool_specs()
        enabled = sum(1 for spec in specs if tool_disabled_reason(spec, settings) is None)
        return MCPSettingsResponse(
            **settings.model_dump(),
            endpoint_path=MCP_PATH,
            default_disabled_tools=sorted(DEFAULT_DISABLED_TOOLS),
            tools_total=len(specs),
            tools_enabled=enabled,
        )

    async def get_settings(self, db: AsyncSession) -> MCPSettingsResponse:
        db_settings = await get_settings(db)
        return self._build_settings_response(MCP.model_validate(db_settings.mcp or {}))

    async def modify_settings(self, db: AsyncSession, modify: MCPSettingsModify) -> MCPSettingsResponse:
        db_settings = await get_settings(db)
        current = MCP.model_validate(db_settings.mcp or {})

        changes = modify.model_dump(exclude_none=True)
        if "disabled_tools" in changes:
            known = {spec.name for spec in get_tool_specs()}
            unknown = [name for name in changes["disabled_tools"] if name not in known]
            if unknown:
                await self.raise_error(message=f"Unknown MCP tools: {', '.join(unknown)}", code=400)

        try:
            new_settings = current.model_copy(update=changes)
            new_settings = MCP.model_validate(new_settings.model_dump())
        except ValueError as exc:
            await self.raise_error(message=str(exc), code=400)

        await modify_settings(db, db_settings, SettingsSchema(mcp=new_settings))
        await refresh_caches()
        # All workers refresh their settings cache (same path as the settings page)
        await router.publish(MessageTopic.SETTING, {"action": "refresh"})
        return self._build_settings_response(new_settings)

    async def list_tools(self, db: AsyncSession, admin: AdminDetails) -> MCPToolsResponse:
        db_settings = await get_settings(db)
        settings = MCP.model_validate(db_settings.mcp or {})

        tools: list[MCPToolInfo] = []
        for spec in sorted(get_tool_specs(), key=lambda item: (_group_sort_key(item.group), item.name)):
            reason = tool_disabled_reason(spec, settings)
            tools.append(
                MCPToolInfo(
                    name=spec.name,
                    title=spec.title,
                    group=spec.group,
                    description=spec.description,
                    method=spec.method,
                    path=spec.path,
                    read_only=spec.read_only,
                    destructive=spec.destructive,
                    owner_only=spec.owner_only,
                    permissions=[
                        MCPToolPermission(resource=p.resource, action=p.action, scope_all=p.scope_all)
                        for p in spec.permissions
                    ],
                    enabled=reason is None,
                    disabled_reason=reason,
                    allowed=admin_can_use_tool(admin, spec),
                )
            )
        return MCPToolsResponse(tools=tools, total=len(tools))

    async def get_oauth_request(self, request: str) -> MCPOAuthRequestInfo:
        info = await describe_request(request)
        if info is None:
            await self.raise_error(message="Authorization request is invalid or expired", code=400)
        return MCPOAuthRequestInfo(**info)

    async def consent_oauth_request(self, admin: AdminDetails, consent: MCPOAuthConsent) -> MCPOAuthConsentResponse:
        if consent.approve:
            if consent.permissions is not None:
                try:
                    _check_permissions_not_exceed_admin(admin, consent.permissions)
                except ValueError as e:
                    await self.raise_error(message=str(e), code=403)
            redirect_url = await grant_request(consent.request, admin, consent.permissions)
        else:
            redirect_url = await deny_request(consent.request)
        if redirect_url is None:
            await self.raise_error(message="Authorization request is invalid or expired", code=400)
        return MCPOAuthConsentResponse(redirect_url=redirect_url)

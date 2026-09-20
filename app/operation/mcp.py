from app.db import AsyncSession
from app.db.crud.admin import build_admin_details, get_admin_by_id
from app.db.crud.mcp import (
    api_key_mcp_settings,
    get_admin_mcp_settings,
    get_api_key_with_admin,
    set_admin_mcp_settings,
    set_api_key_mcp_settings,
)
from app.db.models import APIKey
from app.mcp.catalog import DEFAULT_DISABLED_TOOLS
from app.mcp.oauth import deny_request, describe_request, grant_request
from app.mcp.registry import MCP_PATH, MCPAccess, admin_can_use_tool, get_tool_specs, tool_disabled_reason
from app.models.admin import AdminDetails
from app.models.mcp import (
    MCPKeySettings,
    MCPOAuthConsent,
    MCPOAuthConsentResponse,
    MCPOAuthRequestInfo,
    MCPSettings,
    MCPSettingsModify,
    MCPSettingsResponse,
    MCPToolInfo,
    MCPToolPermission,
    MCPToolsResponse,
)
from app.operation.api_key import _check_permissions_not_exceed_admin
from app.operation.permissions import PermissionDenied, enforce_permission
from app.routers.authentication import apply_api_key_permissions

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
    async def _get_db_admin(self, db: AsyncSession, admin: AdminDetails):
        if admin.id is None:
            await self.raise_error(message="MCP settings are not available for env admins", code=403)
        db_admin = await get_admin_by_id(db, admin.id, load_users=False, load_usage_logs=False)
        if db_admin is None:
            await self.raise_error(message="Admin not found", code=404)
        return db_admin

    async def _get_db_key(self, db: AsyncSession, admin: AdminDetails, key_id: int) -> APIKey:
        db_key = await get_api_key_with_admin(db, key_id)
        if db_key is None or (db_key.admin_id != admin.id and not admin.is_owner):
            await self.raise_error(message="API key not found", code=404)
        return db_key

    @staticmethod
    def _build_response(settings: MCPSettings, access: MCPAccess, api_key_id: int | None) -> MCPSettingsResponse:
        specs = get_tool_specs()
        enabled = sum(1 for spec in specs if tool_disabled_reason(spec, access) is None)
        return MCPSettingsResponse(
            **settings.model_dump(),
            api_key_id=api_key_id,
            endpoint_path=MCP_PATH,
            default_disabled_tools=sorted(DEFAULT_DISABLED_TOOLS),
            tools_total=len(specs),
            tools_enabled=enabled,
        )

    async def _resolve(
        self, db: AsyncSession, admin: AdminDetails, api_key_id: int | None
    ) -> tuple[MCPSettings, MCPAccess, AdminDetails]:
        """Settings shown on the page, the access they produce and who a session would act as."""
        if api_key_id is None:
            settings = await get_admin_mcp_settings(db, admin.id) if admin.id is not None else MCPSettings()
            return settings, MCPAccess.build(settings), admin
        db_key = await self._get_db_key(db, admin, api_key_id)
        key_settings = api_key_mcp_settings(db_key)
        owner_settings = MCPSettings.model_validate(db_key.admin.mcp or {})
        shown = MCPSettings(
            enable=key_settings.enable,
            oauth=owner_settings.oauth,
            read_only=key_settings.read_only,
            disabled_tools=key_settings.disabled_tools,
        )
        # A key session acts with the key's permission snapshot, not the viewer's role
        key_admin = apply_api_key_permissions(build_admin_details(db_key.admin), db_key)
        return shown, MCPAccess.build(owner_settings, key_settings), key_admin

    async def get_settings(
        self, db: AsyncSession, admin: AdminDetails, api_key_id: int | None = None
    ) -> MCPSettingsResponse:
        settings, access, _ = await self._resolve(db, admin, api_key_id)
        return self._build_response(settings, access, api_key_id)

    async def modify_settings(
        self, db: AsyncSession, admin: AdminDetails, modify: MCPSettingsModify, api_key_id: int | None = None
    ) -> MCPSettingsResponse:
        changes = modify.model_dump(exclude_none=True)
        if "disabled_tools" in changes:
            known = {spec.name for spec in get_tool_specs()}
            unknown = [name for name in changes["disabled_tools"] if name not in known]
            if unknown:
                await self.raise_error(message=f"Unknown MCP tools: {', '.join(unknown)}", code=400)

        if api_key_id is None:
            db_admin = await self._get_db_admin(db, admin)
            current = MCPSettings.model_validate(db_admin.mcp or {})
            try:
                new_settings = MCPSettings.model_validate(current.model_copy(update=changes).model_dump())
            except ValueError as exc:
                await self.raise_error(message=str(exc), code=400)
            await set_admin_mcp_settings(db, db_admin, new_settings)
            return self._build_response(new_settings, MCPAccess.build(new_settings), None)

        db_key = await self._get_db_key(db, admin, api_key_id)
        changes.pop("oauth", None)
        current = api_key_mcp_settings(db_key)
        try:
            new_key_settings = MCPKeySettings.model_validate(current.model_copy(update=changes).model_dump())
        except ValueError as exc:
            await self.raise_error(message=str(exc), code=400)
        await set_api_key_mcp_settings(db, db_key, new_key_settings)
        settings, access, _ = await self._resolve(db, admin, api_key_id)
        return self._build_response(settings, access, api_key_id)

    async def list_tools(
        self, db: AsyncSession, admin: AdminDetails, api_key_id: int | None = None
    ) -> MCPToolsResponse:
        _, access, actor = await self._resolve(db, admin, api_key_id)

        tools: list[MCPToolInfo] = []
        for spec in sorted(get_tool_specs(), key=lambda item: (_group_sort_key(item.group), item.name)):
            reason = tool_disabled_reason(spec, access)
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
                    allowed=admin_can_use_tool(actor, spec),
                )
            )
        return MCPToolsResponse(tools=tools, total=len(tools))

    async def get_oauth_request(self, request: str) -> MCPOAuthRequestInfo:
        info = await describe_request(request)
        if info is None:
            await self.raise_error(message="Authorization request is invalid or expired", code=400)
        return MCPOAuthRequestInfo(**info)

    async def consent_oauth_request(
        self, db: AsyncSession, admin: AdminDetails, consent: MCPOAuthConsent
    ) -> MCPOAuthConsentResponse:
        if consent.approve:
            settings = await get_admin_mcp_settings(db, admin.id) if admin.id is not None else MCPSettings()
            if not settings.enable:
                await self.raise_error(message="MCP is turned off for this account", code=403)
            if not settings.oauth:
                await self.raise_error(message="OAuth sign-in is turned off for this account", code=403)
            # Approving issues an API key, so the same permission as the API Keys page applies
            try:
                enforce_permission(admin, "api_keys", "create")
            except PermissionDenied as e:
                await self.raise_error(message=str(e), code=403)
            if consent.permissions is not None:
                try:
                    _check_permissions_not_exceed_admin(admin, consent.permissions)
                except ValueError as e:
                    await self.raise_error(message=str(e), code=403)
            if consent.mcp is not None:
                known = {spec.name for spec in get_tool_specs()}
                unknown = [name for name in consent.mcp.disabled_tools if name not in known]
                if unknown:
                    await self.raise_error(message=f"Unknown MCP tools: {', '.join(unknown)}", code=400)
            redirect_url = await grant_request(consent.request, admin, consent.permissions, consent.mcp, consent.name)
        else:
            redirect_url = await deny_request(consent.request)
        if redirect_url is None:
            await self.raise_error(message="Authorization request is invalid or expired", code=400)
        return MCPOAuthConsentResponse(redirect_url=redirect_url)

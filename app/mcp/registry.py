from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Self

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.models.admin import AdminDetails
from app.models.mcp import MCPKeySettings, MCPSettings
from app.operation.permissions import PermissionDenied, enforce_permission, is_scope_all

MCP_PATH = "/mcp"
ADMIN_STATE_KEY = "mcp_admin"
ACCESS_STATE_KEY = "mcp_access"


@dataclass(frozen=True)
class ToolPermission:
    resource: str
    action: str
    scope_all: bool = False


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    group: str
    description: str
    method: str
    path: str
    read_only: bool
    destructive: bool = False
    owner_only: bool = False
    permissions: tuple[ToolPermission, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MCPAccess:
    """What a session may use: the admin's settings, narrowed by the API key's settings when one is used."""

    enable: bool
    read_only: bool
    disabled_tools: frozenset[str]

    @classmethod
    def build(cls, settings: MCPSettings, key_settings: MCPKeySettings | None = None) -> Self:
        if key_settings is None:
            return cls(settings.enable, settings.read_only, frozenset(settings.disabled_tools))
        return cls(
            settings.enable and key_settings.enable,
            settings.read_only or key_settings.read_only,
            frozenset(settings.disabled_tools) | frozenset(key_settings.disabled_tools),
        )


_SPECS: dict[str, ToolSpec] = {}
_HANDLERS: dict[str, Callable[..., Awaitable[Any]]] = {}


def register_tool(spec: ToolSpec, handler: Callable[..., Awaitable[Any]]) -> None:
    if spec.name in _SPECS:
        raise RuntimeError(f"MCP tool '{spec.name}' registered twice")
    _SPECS[spec.name] = spec
    _HANDLERS[spec.name] = handler


def clear_tools() -> None:
    _SPECS.clear()
    _HANDLERS.clear()


def get_tool_specs() -> list[ToolSpec]:
    return list(_SPECS.values())


def get_tool_spec(name: str) -> ToolSpec | None:
    return _SPECS.get(name)


def get_tool_handler(name: str) -> Callable[..., Awaitable[Any]] | None:
    return _HANDLERS.get(name)


def _enforce(admin: AdminDetails, spec: ToolSpec) -> None:
    if spec.owner_only and not admin.is_owner:
        raise PermissionDenied("Only the owner can perform this action")
    for permission in spec.permissions:
        enforce_permission(admin, permission.resource, permission.action)
        if permission.scope_all and not is_scope_all(admin, permission.resource, permission.action):
            raise PermissionDenied(f"Permission denied: {permission.resource}.{permission.action} requires scope=all")


def admin_can_use_tool(admin: AdminDetails, spec: ToolSpec) -> bool:
    try:
        _enforce(admin, spec)
    except PermissionDenied:
        return False
    return True


def tool_disabled_reason(spec: ToolSpec, access: MCPAccess) -> str | None:
    if spec.name in access.disabled_tools:
        return "disabled"
    if access.read_only and not spec.read_only:
        return "read_only"
    return None


def is_tool_visible(spec: ToolSpec, access: MCPAccess, admin: AdminDetails) -> bool:
    return tool_disabled_reason(spec, access) is None and admin_can_use_tool(admin, spec)


def _request_state(ctx: Context):
    return getattr(ctx.request_context.request, "state", None)


def get_admin_from_context(ctx: Context) -> AdminDetails:
    state = _request_state(ctx)
    admin = getattr(state, ADMIN_STATE_KEY, None) if state is not None else None
    if admin is None:
        raise ToolError("Unauthenticated MCP request")
    return admin


def get_access_from_context(ctx: Context) -> MCPAccess:
    state = _request_state(ctx)
    access = getattr(state, ACCESS_STATE_KEY, None) if state is not None else None
    if access is None:
        raise ToolError("Unauthenticated MCP request")
    return access


def check_tool_access(spec: ToolSpec, admin: AdminDetails, access: MCPAccess) -> None:
    reason = tool_disabled_reason(spec, access)
    if reason == "disabled":
        raise ToolError(f"Tool '{spec.name}' is disabled in the MCP settings")
    if reason == "read_only":
        raise ToolError("MCP access is read-only; write tools are unavailable")
    try:
        _enforce(admin, spec)
    except PermissionDenied as exc:
        raise ToolError(str(exc)) from exc


def tool_annotations(spec: ToolSpec) -> ToolAnnotations:
    return ToolAnnotations(
        title=spec.title,
        readOnlyHint=spec.read_only,
        destructiveHint=spec.destructive,
        idempotentHint=spec.read_only,
        openWorldHint=False,
    )

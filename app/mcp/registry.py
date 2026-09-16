from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.models.admin import AdminDetails
from app.models.settings import MCP as MCPSettings
from app.operation.permissions import PermissionDenied, enforce_permission, is_scope_all
from app.settings import mcp_settings

MCP_PATH = "/mcp"
ADMIN_STATE_KEY = "mcp_admin"


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


def tool_disabled_reason(spec: ToolSpec, settings: MCPSettings) -> str | None:
    if spec.name in settings.disabled_tools:
        return "disabled"
    if settings.read_only and not spec.read_only:
        return "read_only"
    return None


def is_tool_visible(spec: ToolSpec, settings: MCPSettings, admin: AdminDetails) -> bool:
    return tool_disabled_reason(spec, settings) is None and admin_can_use_tool(admin, spec)


def get_admin_from_context(ctx: Context) -> AdminDetails:
    state = getattr(ctx.request_context.request, "state", None)
    admin = getattr(state, ADMIN_STATE_KEY, None) if state is not None else None
    if admin is None:
        raise ToolError("Unauthenticated MCP request")
    return admin


async def check_tool_access(spec: ToolSpec, admin: AdminDetails) -> None:
    settings = await mcp_settings()
    if not settings.enable:
        raise ToolError("MCP server is disabled")
    reason = tool_disabled_reason(spec, settings)
    if reason == "disabled":
        raise ToolError(f"Tool '{spec.name}' is disabled by the panel administrator")
    if reason == "read_only":
        raise ToolError("MCP server is in read-only mode; write tools are unavailable")
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

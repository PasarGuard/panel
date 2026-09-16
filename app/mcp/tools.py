import inspect
import re
from typing import Annotated, Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from app.routers.authentication import get_current, get_current_with_metrics
from app.utils.logger import get_logger

from .auth import extract_credentials
from .catalog import TOOL_TEXT
from .registry import (
    ToolPermission,
    ToolSpec,
    check_tool_access,
    get_access_from_context,
    get_admin_from_context,
    register_tool,
)

logger = get_logger("mcp")

INTERNAL_BASE_URL = "http://mcp.internal"
DEFAULT_LIST_LIMIT = 50
CONFIRM_PARAM = "confirm"

# Streams logs; every other route without an admin dependency is skipped automatically
EXCLUDED_ROUTE_NAMES = {"node_logs"}
EXCLUDED_PATH_PREFIXES = ("/api/mcp",)
# Legacy duplicates of the username-based routes
EXCLUDED_PATH_PARTS = ("/by-username/", "/by-id/")

TAG_GROUPS = {
    "System": "system",
    "User": "users",
    "Admin": "admins",
    "Admin Roles": "admin_roles",
    "API Keys": "api_keys",
    "Node": "nodes",
    "Core": "cores",
    "Host": "hosts",
    "Groups": "groups",
    "User Template": "templates",
    "Client Template": "client_templates",
    "User HWID": "hwids",
    "Settings": "settings",
}
DESTRUCTIVE_PATTERN = re.compile(r"(delete|remove|revoke|reset|clear)")


def iter_api_routes(routes) -> list[APIRoute]:
    found: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
        elif hasattr(route, "original_router"):
            found.extend(iter_api_routes(route.original_router.routes))
        elif hasattr(route, "routes"):
            found.extend(iter_api_routes(route.routes))
    return found


def _route_permissions(dependant: Dependant) -> tuple[tuple[ToolPermission, ...], bool, bool]:
    """Permissions, owner-only flag and whether the route authenticates an admin at all."""
    permissions: list[ToolPermission] = []
    owner_only = False
    requires_admin = False
    for dep in dependant.dependencies:
        fn = dep.call
        permission = getattr(fn, "permission", None)
        if permission:
            permissions.append(ToolPermission(*permission, getattr(fn, "scope_all", False)))
        owner_only = owner_only or getattr(fn, "owner_only", False)
        requires_admin = (
            requires_admin
            or fn in (get_current, get_current_with_metrics)
            or bool(permission)
            or getattr(fn, "owner_only", False)
        )
        sub_permissions, sub_owner, sub_admin = _route_permissions(dep)
        permissions.extend(sub_permissions)
        owner_only = owner_only or sub_owner
        requires_admin = requires_admin or sub_admin
    return tuple(permissions), owner_only, requires_admin


def _collect_params(dependant: Dependant, kind: str) -> list:
    params = list(getattr(dependant, f"{kind}_params"))
    for dep in dependant.dependencies:
        params.extend(_collect_params(dep, kind))
    return params


def _field_annotation(model_field) -> Any:
    info = model_field.field_info
    annotation = info.annotation
    return Annotated[annotation, info] if info.description or info.metadata else annotation


def _is_required(model_field) -> bool:
    return model_field.field_info.is_required()


def _humanize(name: str) -> str:
    return name.replace("_", " ").capitalize()


def _description(route: APIRoute) -> str:
    if route.summary:
        return route.summary
    doc = inspect.getdoc(route.endpoint)
    if doc:
        return doc.strip().splitlines()[0]
    return f"{min(route.methods)} {route.path}"


def _group(route: APIRoute) -> str:
    tag = str(route.tags[0]) if route.tags else ""
    return TAG_GROUPS.get(tag, tag.lower().replace(" ", "_") or "other")


def _spec_for(route: APIRoute) -> ToolSpec | None:
    if route.name in EXCLUDED_ROUTE_NAMES:
        return None
    if not route.path.startswith("/api/") or route.path.startswith(EXCLUDED_PATH_PREFIXES):
        return None
    if any(part in route.path for part in EXCLUDED_PATH_PARTS):
        return None
    method = min(route.methods)
    permissions, owner_only, requires_admin = _route_permissions(route.dependant)
    # Login, setup and webhook routes have no admin behind them
    if not requires_admin:
        return None
    title, description = TOOL_TEXT.get(route.name, (_humanize(route.name), _description(route)))
    return ToolSpec(
        name=route.name,
        title=title,
        group=_group(route),
        description=description,
        method=method,
        path=route.path,
        read_only=method == "GET",
        destructive=method == "DELETE" or bool(DESTRUCTIVE_PATTERN.search(route.name)),
        owner_only=owner_only,
        permissions=permissions,
    )


def _build_handler(app: FastAPI, route: APIRoute, spec: ToolSpec):
    path_fields = _collect_params(route.dependant, "path")
    query_fields = _collect_params(route.dependant, "query")
    body_fields = _collect_params(route.dependant, "body")

    path_names = {f.name for f in path_fields}
    query_by_name = {f.name: f for f in query_fields}
    body_names = [f.name for f in body_fields]
    has_limit = "limit" in query_by_name

    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}
    seen: set[str] = set()
    for model_field in [*path_fields, *body_fields, *query_fields]:
        if model_field.name in seen:
            continue
        seen.add(model_field.name)
        annotation = _field_annotation(model_field)
        default = inspect.Parameter.empty if _is_required(model_field) else model_field.field_info.default
        parameters.append(
            inspect.Parameter(model_field.name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation)
        )
        annotations[model_field.name] = annotation
    parameters.sort(key=lambda p: p.default is not inspect.Parameter.empty)
    if spec.destructive:
        confirm_annotation = Annotated[bool, Field(description="Must be true. This action cannot be undone.")]
        parameters.append(
            inspect.Parameter(
                CONFIRM_PARAM, inspect.Parameter.KEYWORD_ONLY, default=False, annotation=confirm_annotation
            )
        )
        annotations[CONFIRM_PARAM] = confirm_annotation
    parameters.append(inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, annotation=Context))
    annotations["ctx"] = Context
    annotations["return"] = Any

    async def handler(ctx: Context, **kwargs):
        admin = get_admin_from_context(ctx)
        check_tool_access(spec, admin, get_access_from_context(ctx))
        if spec.destructive and kwargs.pop(CONFIRM_PARAM, False) is not True:
            raise ToolError(f"'{spec.name}' cannot be undone; call it again with {CONFIRM_PARAM}=true")

        path = route.path
        for name in path_names:
            path = path.replace("{" + name + "}", quote(str(kwargs.get(name)), safe=""))

        query: dict[str, Any] = {}
        for name, model_field in query_by_name.items():
            value = kwargs.get(name)
            if value is None:
                continue
            key = model_field.alias or name
            query[key] = value.value if hasattr(value, "value") else value
        if has_limit and query.get("limit") in (None, 0):
            query["limit"] = DEFAULT_LIST_LIMIT

        json_body: Any = None
        if len(body_names) == 1:
            value = kwargs.get(body_names[0])
            json_body = value.model_dump(mode="json", exclude_unset=True) if isinstance(value, BaseModel) else value
        elif body_names:
            json_body = {
                name: (
                    v.model_dump(mode="json", exclude_unset=True) if isinstance(v := kwargs.get(name), BaseModel) else v
                )
                for name in body_names
            }

        token, api_key = extract_credentials(ctx.request_context.request)
        headers = {"X-Api-Key": api_key} if api_key else {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=INTERNAL_BASE_URL) as client:
                response = await client.request(spec.method, path, params=query, json=json_body, headers=headers)
        except Exception as exc:
            logger.warning(f"MCP {admin.username} {spec.name} failed: {exc}")
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

        logger.info(f"MCP {admin.username} {spec.name} -> {response.status_code}")
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ToolError(str(detail))
        if response.status_code == 204 or not response.content:
            return {"ok": True}
        if response.headers.get("content-type", "").startswith("application/json"):
            data = response.json()
            return {"result": data} if isinstance(data, list) else data
        return response.text

    handler.__signature__ = inspect.Signature(parameters, return_annotation=Any)
    handler.__annotations__ = annotations
    handler.__name__ = spec.name
    handler.__doc__ = spec.description
    return handler


def build_route_tools(app: FastAPI) -> int:
    count = 0
    for route in iter_api_routes(app.routes):
        spec = _spec_for(route)
        if spec is None:
            continue
        register_tool(spec, _build_handler(app, route, spec))
        count += 1
    return count

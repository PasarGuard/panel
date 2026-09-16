import asyncio

from mcp.server.context import ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ListToolsResult
from starlette.routing import Route

from app.utils.logger import get_logger
from app.version import __version__

from .auth import MCPAuthMiddleware
from .oauth import oauth_routes
from .registry import (
    ACCESS_STATE_KEY,
    ADMIN_STATE_KEY,
    MCP_PATH,
    clear_tools,
    get_tool_handler,
    get_tool_spec,
    get_tool_specs,
    is_tool_visible,
    tool_annotations,
)
from .tools import build_route_tools

logger = get_logger("mcp")

SERVER_NAME = "PasarGuard"
SERVER_INSTRUCTIONS = (
    "PasarGuard proxy panel. Every tool maps to a panel REST endpoint and is limited to the "
    "permissions of the authenticated admin. Data sizes are in bytes; dates are ISO 8601. "
    "List tools default to 50 results; use offset/limit and search filters to page."
)


async def _visibility_middleware(ctx: ServerRequestContext, call_next):
    """Drop tools the caller cannot use from tools/list."""
    result = await call_next(ctx)
    if ctx.method != "tools/list":
        return result

    state = getattr(ctx.request, "state", None)
    admin = getattr(state, ADMIN_STATE_KEY, None) if state is not None else None
    access = getattr(state, ACCESS_STATE_KEY, None) if state is not None else None
    if admin is None or access is None:
        return result

    def _visible(tool_name: str) -> bool:
        spec = get_tool_spec(tool_name)
        return spec is None or is_tool_visible(spec, access, admin)

    # The SDK may pass the pydantic result or its serialized dict
    if isinstance(result, ListToolsResult):
        return result.model_copy(update={"tools": [tool for tool in result.tools if _visible(tool.name)]})
    if isinstance(result, dict) and isinstance(result.get("tools"), list):
        return {**result, "tools": [tool for tool in result["tools"] if _visible(tool.get("name", ""))]}
    return result


def build_mcp_server(app) -> MCPServer:
    clear_tools()
    build_route_tools(app)

    server = MCPServer(
        name=SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        version=__version__,
        middleware=[_visibility_middleware],
    )
    for spec in get_tool_specs():
        handler = get_tool_handler(spec.name)
        server.tool(name=spec.name, description=spec.description, annotations=tool_annotations(spec))(handler)
    return server


class _Transport:
    """Streamable HTTP transport kept alive in a dedicated task; rebuilt if the event loop changes."""

    def __init__(self, server: MCPServer):
        self._server = server
        self._manager: StreamableHTTPSessionManager | None = None
        self._asgi_app: StreamableHTTPASGIApp | None = None
        self._task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None
        self._ready: asyncio.Event | None = None

    def _build(self) -> None:
        self._manager = StreamableHTTPSessionManager(
            app=self._server._lowlevel_server,
            json_response=True,
            stateless=True,
            # Panel is served on arbitrary public hostnames; host validation belongs to the reverse proxy
            security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        self._asgi_app = StreamableHTTPASGIApp(self._manager)

    async def ensure_started(self) -> StreamableHTTPASGIApp:
        if self._task is not None and not self._task.done():
            await self._ready.wait()
            return self._asgi_app
        self._build()
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="pasarguard-mcp-session-manager")
        await self._ready.wait()
        return self._asgi_app

    async def _run(self) -> None:
        try:
            async with self._manager.run():
                self._ready.set()
                await self._stop.wait()
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"MCP session manager stopped unexpectedly: {exc}")
        finally:
            self._ready.set()

    async def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._task is not None:
            try:
                await self._task
            except Exception:
                pass
        self._task = None


class _MCPEndpoint:
    def __init__(self, transport: _Transport):
        self._transport = transport

    async def __call__(self, scope, receive, send) -> None:
        asgi_app = await self._transport.ensure_started()
        await asgi_app(scope, receive, send)


_server: MCPServer | None = None
_transport: _Transport | None = None


def get_mcp_server() -> MCPServer | None:
    return _server


def setup_mcp(app) -> None:
    global _server, _transport

    from app import on_shutdown, on_startup

    _server = build_mcp_server(app)
    _transport = _Transport(_server)
    # Route instead of Mount so /mcp is served without a trailing-slash redirect
    app.router.routes.append(Route(MCP_PATH, endpoint=MCPAuthMiddleware(_MCPEndpoint(_transport)), name="mcp"))
    app.router.routes.extend(oauth_routes())

    async def _start_mcp():
        await _transport.ensure_started()
        logger.info(f"MCP server mounted at {MCP_PATH} ({len(get_tool_specs())} tools)")

    async def _stop_mcp():
        await _transport.stop()

    on_startup(_start_mcp)
    on_shutdown(_stop_mcp)

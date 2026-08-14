import logging
import random
from time import perf_counter

from h11 import LocalProtocolError
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def safe_request_target(scope: Scope) -> tuple[str, str]:
    """Return a route template without path parameters or query contents."""
    route = scope.get("route")
    route_path = getattr(route, "path", None)
    if not isinstance(route_path, str) or not route_path:
        route_path = "/<unmatched>"

    query_bytes = scope.get("query_string", b"")
    request_target = f"{route_path}?<redacted>" if query_bytes else route_path
    return route_path, request_target


class RequestProcessTimeLoggingMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        access_logger: logging.Logger,
        success_sample_rate: float = 1.0,
        slow_request_ms: float = 1000,
        sampled_routes: frozenset[str] = frozenset(),
    ):
        self.app = app
        self.access_logger = access_logger
        self.success_sample_rate = min(max(success_sample_rate, 0), 1)
        self.slow_request_ms = max(slow_request_ms, 0)
        self.sampled_routes = sampled_routes

    def _log_level(self, route_path: str, status_code: int, process_time_ms: float) -> int:
        if status_code >= 400 or process_time_ms >= self.slow_request_ms:
            return logging.INFO
        if route_path not in self.sampled_routes:
            return logging.INFO
        return logging.INFO if random.random() < self.success_sample_rate else logging.DEBUG

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = perf_counter()
        status_code = 500
        connection_closed = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, connection_closed
            if connection_closed:
                return

            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))

            try:
                await send(message)
            except LocalProtocolError as exc:
                # Connection has already transitioned to MUST_CLOSE.
                if "MUST_CLOSE" in str(exc):
                    connection_closed = True
                    return
                raise

        try:
            await self.app(scope, receive, send_wrapper)
        except LocalProtocolError as exc:
            if "MUST_CLOSE" not in str(exc):
                raise
        finally:
            process_time_ms = (perf_counter() - start_time) * 1000
            route_path, request_target = safe_request_target(scope)
            http_version = scope.get("http_version", "1.1")
            client = scope.get("client")
            client_addr = client[0] if client else "-"
            method = scope.get("method", "-")
            log_level = self._log_level(route_path, status_code, process_time_ms)

            self.access_logger.log(
                log_level,
                '%s - "%s %s HTTP/%s" %d',
                client_addr,
                method,
                request_target,
                http_version,
                status_code,
                extra={"process_time": f"{process_time_ms:.2f}ms"},
            )

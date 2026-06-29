import logging
from time import perf_counter

from h11 import LocalProtocolError
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestProcessTimeLoggingMiddleware:
    def __init__(self, app: ASGIApp, access_logger: logging.Logger):
        self.app = app
        self.access_logger = access_logger

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
            path = scope.get("path", "")
            query_bytes = scope.get("query_string", b"")
            if query_bytes:
                path = f"{path}?{query_bytes.decode(errors='replace')}"
            http_version = scope.get("http_version", "1.1")
            client = scope.get("client")
            client_addr = client[0] if client else "-"
            method = scope.get("method", "-")

            self.access_logger.info(
                '%s - "%s %s HTTP/%s" %d',
                client_addr,
                method,
                path,
                http_version,
                status_code,
                extra={"process_time": f"{process_time_ms:.2f}ms"},
            )

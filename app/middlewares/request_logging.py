import logging
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestProcessTimeLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, access_logger: logging.Logger):
        super().__init__(app)
        self.access_logger = access_logger

    async def dispatch(self, request: Request, call_next):
        start_time = perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            process_time_ms = (perf_counter() - start_time) * 1000
            path = request.url.path
            if request.url.query:
                path = f"{path}?{request.url.query}"
            http_version = request.scope.get("http_version", "1.1")
            client_addr = request.client.host if request.client else "-"

            self.access_logger.info(
                '%s - "%s %s HTTP/%s" %d',
                client_addr,
                request.method,
                path,
                http_version,
                status_code,
                extra={"process_time": f"{process_time_ms:.2f}ms"},
            )

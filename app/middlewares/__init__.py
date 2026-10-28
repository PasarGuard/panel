from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.utils.logger import get_logger
from config import cors_settings, server_settings

from .request_limits import MaxRequestBodySizeMiddleware
from .request_logging import RequestProcessTimeLoggingMiddleware


def setup_middleware(app: FastAPI):
    allowed_origins = cors_settings.allowed_origins
    # With a wildcard plus credentials, Starlette echoes every Origin back with Allow-Credentials.
    allow_credentials = "*" not in allowed_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if server_settings.proxy_headers:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=server_settings.forwarded_allow_ips)
    app.add_middleware(RequestProcessTimeLoggingMiddleware, access_logger=get_logger("uvicorn.access"))
    # Added last so it is the outermost user middleware: oversized uploads are rejected before
    # any endpoint buffers them, and it can still turn a streamed overflow into a clean 413.
    if server_settings.max_request_body_size > 0:
        app.add_middleware(MaxRequestBodySizeMiddleware, max_body_size=server_settings.max_request_body_size)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.utils.logger import get_logger
from config import cors_settings, server_settings

from .request_logging import RequestProcessTimeLoggingMiddleware


def setup_middleware(app: FastAPI):
    # Security: reject wildcard origin with credentials enabled
    allowed_origins = cors_settings.allowed_origins
    if "*" in allowed_origins:
        import warnings

        warnings.warn(
            "CORS allow_origins contains '*' with allow_credentials=True is insecure. "
            "Set ALLOWED_ORIGINS to explicit origins in production.",
            stacklevel=2,
        )
        allow_credentials = False
    else:
        allow_credentials = True

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

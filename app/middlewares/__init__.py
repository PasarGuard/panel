from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.utils.logger import get_logger
from config import cors_settings, server_settings

from .request_logging import RequestProcessTimeLoggingMiddleware


def setup_middleware(app: FastAPI):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if server_settings.proxy_headers:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=server_settings.forwarded_allow_ips)
    app.add_middleware(RequestProcessTimeLoggingMiddleware, access_logger=get_logger("uvicorn.access"))

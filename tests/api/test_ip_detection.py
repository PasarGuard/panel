from fastapi import FastAPI, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.middlewares import setup_middleware
from app.routers.admin import get_client_ip
from config import server_settings
from tests.api import client


def test_get_client_ip_no_proxy():
    """Test that get_client_ip returns the direct client host when no proxy is involved."""
    # Use a real Request object with a minimal ASGI scope
    scope = {
        "type": "http",
        "client": ("1.1.1.1", 12345),
        "headers": [],
    }
    request = Request(scope=scope)
    assert get_client_ip(request) == "1.1.1.1"


def test_get_client_ip_with_proxy_middleware_behavior(access_token):
    """
    Test the behavior of IP detection via the TestClient.
    Since we enabled proxy_headers in conftest.py, the middleware should process X-Forwarded-For.
    """

    # We use an endpoint that returns the IP, like /api/admin/token (indirectly via notification)
    # or we can check a subscription info endpoint which also uses request.client.host

    # In tests/conftest.py we set:
    # server_settings.proxy_headers = True
    # server_settings.forwarded_allow_ips = "*"

    # This means X-Forwarded-For should be trusted.
    ip = "203.0.113.10"
    # We use a known endpoint that returns IP in response for easy verification
    # Based on grep, user_subscription_info returns IP

    from tests.api.helpers import (
        create_core,
        create_group,
        create_user,
        delete_core,
        delete_group,
        delete_user,
    )

    core = create_core(access_token)
    group = create_group(access_token)
    user = create_user(
        access_token,
        group_ids=[group["id"]],
        payload={"username": "iptestuser"},
    )
    try:
        response = client.get(f"{user['subscription_url']}/info", headers={"X-Forwarded-For": ip})
        assert response.status_code == 200
        # The subscription router uses request.client.host
        # If ProxyHeadersMiddleware is working, it will swap request.client.host with the value from X-Forwarded-For
        assert response.json()["ip"] == ip
    finally:
        delete_user(access_token, "iptestuser")
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_proxy_headers_disabled_logic():
    """
    Verify that if proxy_headers was False, the middleware wouldn't be added.
    This is a logic check on the middleware setup.
    """

    app = FastAPI()
    original_val = server_settings.proxy_headers
    try:
        server_settings.proxy_headers = False
        setup_middleware(app)

        # Check if ProxyHeadersMiddleware is in the app.user_middleware list
        # Note: Middleware are wrapped, but we can check the classes
        middleware_classes = [m.cls for m in app.user_middleware]
        assert ProxyHeadersMiddleware not in middleware_classes

        # Now enable it
        app_with_proxy = FastAPI()
        server_settings.proxy_headers = True
        setup_middleware(app_with_proxy)
        middleware_classes_proxy = [m.cls for m in app_with_proxy.user_middleware]
        assert ProxyHeadersMiddleware in middleware_classes_proxy
    finally:
        server_settings.proxy_headers = original_val

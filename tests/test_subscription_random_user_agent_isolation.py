import json

from app.models.subscription import WebSocketTransportConfig, XHTTPTransportConfig
from app.subscription.links import StandardLinks
from app.subscription.xray import XrayConfiguration

USER_AGENT_TEMPLATE = '{"list": ["UA-Test/1.0"]}'


def _xray() -> XrayConfiguration:
    return XrayConfiguration(
        user_agent_template_content=USER_AGENT_TEMPLATE,
        grpc_user_agent_template_content=USER_AGENT_TEMPLATE,
    )


def _links() -> StandardLinks:
    return StandardLinks(
        user_agent_template_content=USER_AGENT_TEMPLATE,
        grpc_user_agent_template_content=USER_AGENT_TEMPLATE,
    )


def test_xray_ws_does_not_write_random_user_agent_into_shared_headers():
    cfg = WebSocketTransportConfig(
        path="/ws", host="cdn.example.com", http_headers={"X-Custom": "1"}, random_user_agent=True
    )
    shared = cfg.http_headers
    expected = dict(shared)

    result = _xray()._transport_ws(cfg, "/ws")

    assert "User-Agent" in result["headers"]
    assert result["headers"]["X-Custom"] == "1"
    assert cfg.http_headers is shared
    assert cfg.http_headers == expected


def test_xray_httpupgrade_does_not_write_random_user_agent_into_shared_headers():
    cfg = WebSocketTransportConfig(
        path="/hu", host="cdn.example.com", http_headers={"X-Custom": "1"}, random_user_agent=True
    )
    shared = cfg.http_headers
    expected = dict(shared)

    result = _xray()._transport_httpupgrade(cfg, "/hu")

    assert "User-Agent" in result["headers"]
    assert cfg.http_headers is shared
    assert cfg.http_headers == expected


def test_xray_xhttp_does_not_write_random_user_agent_into_shared_headers():
    cfg = XHTTPTransportConfig(
        path="/up", host="cdn.example.com", mode="stream-up", http_headers={"X-Custom": "1"}, random_user_agent=True
    )
    shared = cfg.http_headers
    expected = dict(shared)

    result = _xray()._transport_xhttp(cfg, "/up")

    assert "User-Agent" in result["extra"]["headers"]
    assert cfg.http_headers is shared
    assert cfg.http_headers == expected


def test_links_xhttp_does_not_write_random_user_agent_into_shared_headers():
    cfg = XHTTPTransportConfig(
        path="/up", host="cdn.example.com", mode="stream-up", http_headers={"X-Custom": "1"}, random_user_agent=True
    )
    shared = cfg.http_headers
    expected = dict(shared)
    payload = {}

    _links()._transport_xhttp(payload, "vless", cfg, "/up")

    assert "User-Agent" in json.loads(payload["extra"])["headers"]
    assert cfg.http_headers is shared
    assert cfg.http_headers == expected

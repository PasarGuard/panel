"""Regressions for the existing VLESS, VMess and Trojan pipeline."""

import base64
import json
from copy import deepcopy
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from app.core.xray import XRayConfig
from app.models.subscription import SubscriptionInboundData, TLSConfig, WebSocketTransportConfig, XHTTPTransportConfig
from app.subscription.links import StandardLinks
from app.subscription.xray import XrayConfiguration
from config import subscription_env_settings
from scripts.generate_xray_config import build_config

USER_ID = "11111111-1111-4111-8111-111111111111"


def inbound(protocol, *, network="ws", transport=None):
    return SubscriptionInboundData(
        remark="test",
        inbound_tag="test",
        protocol=protocol,
        address="edge.example.com",
        port=443,
        network=network,
        tls_config=TLSConfig(tls="tls", sni="edge.example.com"),
        transport_config=transport or WebSocketTransportConfig(path=f"/pasarguard/{protocol}"),
        priority=0,
    )


@pytest.mark.parametrize("protocol", ["vless", "vmess", "trojan"])
def test_tls_ws_links_keep_credentials_and_transport(protocol):
    links = StandardLinks()
    links.add("نام تست", "edge.example.com", inbound(protocol), {"id": USER_ID, "password": "p@ss/#?word"})
    link = links.links[0]
    assert link.startswith(protocol + "://")
    if protocol == "vmess":
        payload = json.loads(base64.b64decode(link.removeprefix("vmess://")))
        assert payload["id"] == USER_ID
        assert payload["net"] == "ws"
        assert payload["tls"] == "tls"
        assert payload["path"] == "/pasarguard/vmess"
        assert payload["ps"] == "نام تست"
    else:
        parsed = urlsplit(link)
        assert unquote(parsed.username) == (USER_ID if protocol == "vless" else "p@ss/#?word")
        query = parse_qs(parsed.query)
        assert query["security"] == ["tls"]
        assert query["type"] == ["ws"]
        assert query["path"] == [f"/pasarguard/{protocol}"]
        assert unquote(parsed.fragment) == "نام تست"


@pytest.mark.parametrize("protocol", ["vless", "trojan"])
@pytest.mark.parametrize("address", ["2001:db8::1", "[2001:db8::1]"])
def test_ipv6_uri_authority(protocol, address):
    links = StandardLinks()
    links.add("test", address, inbound(protocol), {"id": USER_ID, "password": "secret"})
    parsed = urlsplit(links.links[0])
    assert parsed.hostname == "2001:db8::1"
    assert parsed.port == 443


def test_links_render_is_idempotent(monkeypatch):
    monkeypatch.setattr(subscription_env_settings, "external_config", "vless://external")
    links = StandardLinks()
    links.add_link("trojan://example")
    assert links.render() == links.render() == "trojan://example\nvless://external"
    assert links.links == ["trojan://example"]


@pytest.mark.parametrize("direction", ["inbounds", "outbounds"])
def test_xray_rejects_duplicate_tags(direction):
    config = build_config(behind_tls_proxy=True)
    config[direction].append(deepcopy(config[direction][0]))
    with pytest.raises(ValueError, match="unique tag"):
        XRayConfig(config)


def test_xray_does_not_mutate_caller_exclusion_set():
    excluded = {"excluded"}
    XRayConfig(build_config(behind_tls_proxy=True), exclude_inbound_tags=excluded, fallbacks_inbound_tags={"fallback"})
    assert excluded == {"excluded"}


def test_generated_protocols_are_resolved_by_panel():
    config = XRayConfig(build_config(behind_tls_proxy=True))
    assert {p.name for p in config.protocols} == {"vless", "vmess", "trojan"}


@pytest.mark.parametrize("mode", ["packet-up", "stream-up"])
def test_empty_user_agent_templates_do_not_crash_xhttp(mode):
    transport = XHTTPTransportConfig(path="/up", mode=mode, random_user_agent=True)
    data = inbound("vless", network="xhttp", transport=transport)
    for conf in (StandardLinks(), XrayConfiguration(xray_template_content='{"outbounds":[]}')):
        conf.add("test", "edge.example.com", data, {"id": USER_ID})


def test_xray_transport_does_not_mutate_source_headers():
    transport = WebSocketTransportConfig(path="/ws", http_headers={"X-Test": "value"}, random_user_agent=True)
    conf = XrayConfiguration(user_agent_template_content='{"list":["test-agent"]}')
    result = conf._transport_ws(transport, "/ws")
    assert result["headers"]["User-Agent"] == "test-agent"
    assert transport.http_headers == {"X-Test": "value"}

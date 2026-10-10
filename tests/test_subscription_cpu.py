"""CPU-oriented subscription render, cache, and host-copy behaviour."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db.models import UserStatus
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription import config_cache
from app.subscription.base import dumps_compact
from app.subscription.clash import ClashConfiguration
from app.subscription.outline import OutlineConfiguration
from app.subscription.share import generate_subscription, process_host
from app.subscription.singbox import SingBoxConfiguration
from app.subscription.xray import XrayConfiguration


@pytest.fixture(autouse=True)
def _clear_sub_config_cache():
    config_cache.clear_sub_config_cache()
    yield
    config_cache.clear_sub_config_cache()


def test_dumps_compact_has_no_pretty_whitespace():
    payload = [{"remarks": "a", "nested": {"k": 1}}]
    rendered = dumps_compact(payload)
    assert "\n" not in rendered
    assert "  " not in rendered
    assert json.loads(rendered) == payload


def test_xray_and_singbox_render_compact():
    xray = XrayConfiguration()
    xray.config = [{"remarks": "node", "outbounds": [{"tag": "direct"}]}]
    xray_text = xray.render()
    assert "\n" not in xray_text
    assert json.loads(xray_text) == xray.config

    singbox = SingBoxConfiguration(singbox_template_content="{}")
    singbox.config = {"outbounds": [{"type": "direct", "tag": "direct"}], "endpoints": []}
    singbox_text = singbox.render()
    assert "\n" not in singbox_text
    parsed = json.loads(singbox_text)
    assert parsed["outbounds"][0]["tag"] == "direct"


def test_outline_render_compact():
    outline = OutlineConfiguration()
    outline.add_directly({"method": "aes-256-gcm", "password": "x"})
    text = outline.render()
    assert "\n" not in text
    assert json.loads(text) == {"method": "aes-256-gcm", "password": "x"}


def test_clash_render_returns_template_output_without_yaml_roundtrip():
    conf = ClashConfiguration(clash_template_content="count={{ proxy_remarks | length }}")
    conf.proxy_remarks = ["a", "b"]
    assert conf.render() == "count=2"


def test_sub_config_cache_expires_and_evicts():
    key = (1, "links", False, False, "active", None, None, ())
    config_cache.put_sub_config(key, "v1")
    assert config_cache.get_sub_config(key) == "v1"

    original_ttl = config_cache.SUB_CONFIG_CACHE_TTL_S
    config_cache.SUB_CONFIG_CACHE_TTL_S = 0
    try:
        config_cache.put_sub_config(key, "v2")
        time.sleep(0.01)
        assert config_cache.get_sub_config(key) is None
    finally:
        config_cache.SUB_CONFIG_CACHE_TTL_S = original_ttl

    original_max = config_cache.SUB_CONFIG_CACHE_MAX
    config_cache.SUB_CONFIG_CACHE_MAX = 2
    try:
        config_cache.clear_sub_config_cache()
        config_cache.put_sub_config(("a",), "1")
        config_cache.put_sub_config(("b",), "2")
        config_cache.put_sub_config(("c",), "3")
        assert config_cache.get_sub_config(("a",)) is None
        assert config_cache.get_sub_config(("b",)) == "2"
        assert config_cache.get_sub_config(("c",)) == "3"
    finally:
        config_cache.SUB_CONFIG_CACHE_MAX = original_max


@pytest.mark.asyncio
async def test_generate_subscription_returns_cached_payload(monkeypatch: pytest.MonkeyPatch):
    user = SimpleNamespace(id=7, status=UserStatus.active, inbounds=["tag"], data_limit=None, expire=None)
    monkeypatch.setattr(
        "app.subscription.share.subscription_client_templates",
        AsyncMock(side_effect=AssertionError("cache hit should skip rebuild")),
    )
    key = config_cache.make_sub_config_key(user, "links", False, False)
    config_cache.put_sub_config(key, "cached-links")
    assert await generate_subscription(user, "links", False) == "cached-links"


@pytest.mark.asyncio
async def test_process_host_does_not_mutate_cached_inbound():
    inbound = SubscriptionInboundData(
        remark="{USERNAME}",
        inbound_tag="in1",
        protocol="vless",
        address=["host.example"],
        port=[443],
        network="tcp",
        tls_config=TLSConfig(tls="tls", sni=["sni.example"], reality_short_id="abc"),
        transport_config=TCPTransportConfig(path="/{USERNAME}", host=["cdn.example"]),
        priority=0,
    )
    original_sni = list(inbound.tls_config.sni)
    original_host = list(inbound.transport_config.host)
    original_path = inbound.transport_config.path

    result = await process_host(
        inbound,
        defaultdict(lambda: "<missing>", {"USERNAME": "u1"}),
        ["in1"],
        {"vless": {"id": "11111111-1111-1111-1111-111111111111"}},
    )

    assert result is not None
    copy, settings = result
    assert inbound.tls_config.sni == original_sni
    assert inbound.transport_config.host == original_host
    assert inbound.transport_config.path == original_path
    assert copy is not inbound
    assert copy.tls_config is not inbound.tls_config
    assert copy.transport_config is not inbound.transport_config
    assert copy.tls_config.sni == "sni.example"
    assert copy.transport_config.path == "/u1"
    assert settings["id"] == "11111111-1111-1111-1111-111111111111"

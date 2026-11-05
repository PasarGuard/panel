import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.db.models import UserStatus
from app.models.settings import Subscription
from app.models.subscription import (
    GRPCTransportConfig,
    SubscriptionInboundData,
    TCPTransportConfig,
    TLSConfig,
    WebSocketTransportConfig,
    XHTTPTransportConfig,
)
from app.subscription import config_cache
from app.subscription.clash import ClashConfiguration, ClashMetaConfiguration
from app.subscription.links import StandardLinks
from app.subscription.outline import OutlineConfiguration
from app.subscription.share import generate_subscription, process_inbounds_and_tags
from app.subscription.singbox import SingBoxConfiguration
from app.subscription.xray import XrayConfiguration
from config import subscription_env_settings

XRAY_TEMPLATE = json.dumps({"outbounds": [{"protocol": "freedom", "tag": "direct"}]})
UUID = "c90cff8e-d651-414e-8e83-1a187622d957"


def _host(protocol: str, network: str, transport, tls: TLSConfig | None = None, **kwargs) -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="External",
        inbound_tag="external",
        protocol=protocol,
        address="203.0.113.10",
        port=443,
        network=network,
        tls_config=tls or TLSConfig(),
        transport_config=transport,
        **kwargs,
    )


HOSTS = {
    "vless-reality-tcp": (
        _host(
            "vless",
            "tcp",
            TCPTransportConfig(),
            TLSConfig(
                tls="reality",
                sni="www.example.com",
                fingerprint="chrome",
                reality_public_key="pbk",
                reality_short_id="ab12",
                reality_spx="/",
            ),
            inbound_flow="xtls-rprx-vision",
        ),
        {"id": UUID},
    ),
    "vless-ws-tls": (
        _host(
            "vless",
            "ws",
            WebSocketTransportConfig(path="/ws?ed=2048", host="cdn.example.com"),
            TLSConfig(tls="tls", sni="cdn.example.com", fingerprint="chrome", alpn_list=["h2", "http/1.1"]),
        ),
        {"id": UUID},
    ),
    "vless-xhttp-tls": (
        _host(
            "vless",
            "xhttp",
            XHTTPTransportConfig(path="/x", host="cdn.example.com", mode="packet-up", x_padding_bytes="100-1000"),
            TLSConfig(tls="tls", sni="cdn.example.com"),
        ),
        {"id": UUID},
    ),
    "trojan-grpc-tls": (
        _host(
            "trojan",
            "grpc",
            GRPCTransportConfig(path="/svc/Tun", multi_mode=False),
            TLSConfig(tls="tls", sni="grpc.example.com", allowinsecure=True),
        ),
        {"password": "p@ss:w/rd#1"},
    ),
    "vmess-ws-tls": (
        _host(
            "vmess",
            "ws",
            WebSocketTransportConfig(path="/vm", host="cdn.example.com"),
            TLSConfig(tls="tls", sni="cdn.example.com", fingerprint="firefox"),
        ),
        {"id": UUID},
    ),
    "vmess-grpc": (
        _host("vmess", "grpc", GRPCTransportConfig(path="svc", multi_mode=True)),
        {"id": UUID},
    ),
    # A custom stream name keeps the "/", which the link builder percent-encodes.
    "vmess-grpc-path": (
        _host("vmess", "grpc", GRPCTransportConfig(path="/svc/Stream", multi_mode=False)),
        {"id": UUID},
    ),
    "shadowsocks": (
        _host("shadowsocks", "tcp", TCPTransportConfig()),
        {"method": "chacha20-ietf-poly1305", "password": "secret"},
    ),
    "shadowsocks-2022": (
        _host(
            "shadowsocks",
            "tcp",
            TCPTransportConfig(),
            is_2022=True,
            method="2022-blake3-aes-128-gcm",
            password="AAAAAAAAAAAAAAAAAAAAAA==",
        ),
        {"method": "2022-blake3-aes-128-gcm", "password": "user"},
    ),
}


def _share_link(inbound: SubscriptionInboundData, settings: dict) -> str:
    links = StandardLinks()
    links.add(remark=inbound.remark, address=inbound.address, inbound=inbound, settings=settings)
    return links.links[0]


def _render_xray(links: list[str]) -> list[dict]:
    conf = XrayConfiguration(xray_template_content=XRAY_TEMPLATE)
    conf.add_share_links(links)
    return json.loads(conf.render())


def _proxies(conf: ClashConfiguration | SingBoxConfiguration) -> list[dict]:
    return conf.config["outbounds"] if isinstance(conf, SingBoxConfiguration) else conf.data["proxies"]


@pytest.mark.parametrize("name", HOSTS)
def test_xray_external_link_matches_host_configuration(name):
    inbound, settings = HOSTS[name]
    expected = XrayConfiguration(xray_template_content=XRAY_TEMPLATE)
    expected.add(remark=inbound.remark, address=inbound.address, inbound=inbound, settings=settings)

    assert _render_xray([_share_link(inbound, settings)]) == expected.config


@pytest.mark.parametrize("builder", [ClashConfiguration, ClashMetaConfiguration, SingBoxConfiguration])
@pytest.mark.parametrize("name", HOSTS)
def test_clash_and_sing_box_external_link_matches_host_proxy(builder, name):
    if builder is ClashConfiguration and name == "shadowsocks-2022":
        pytest.skip("Clash builds a 2022 host with the user key only; the link carries the full key")
    inbound, settings = HOSTS[name]
    link = _share_link(inbound, settings)
    expected = builder()
    expected.add(remark=inbound.remark, address=inbound.address, inbound=inbound, settings=settings)
    if "extra=" in link:
        # Only Xray JSON carries xHTTP extra, so the link is skipped rather than built without it.
        expected = builder()

    conf = builder()
    conf.add_share_links([link])

    assert _proxies(conf) == _proxies(expected)


@pytest.mark.parametrize(
    ("builder", "protocols"),
    [
        (ClashConfiguration, ["vmess"]),
        (ClashMetaConfiguration, ["vless", "vmess"]),
        (SingBoxConfiguration, ["vless", "vmess"]),
    ],
)
def test_clash_and_sing_box_read_each_external_link_and_skip_unsupported(builder, protocols):
    vless = _share_link(*HOSTS["vless-reality-tcp"])
    vmess = _share_link(*HOSTS["vmess-ws-tls"])
    conf = builder()

    conf.add_share_links(["hysteria2://auth@203.0.113.10:443#hy", vless, "not-a-link", "vless://broken", vmess])

    assert [proxy["type"] for proxy in _proxies(conf)] == protocols


def test_xray_external_links_read_each_link_and_skip_unsupported():
    vless = _share_link(*HOSTS["vless-reality-tcp"])
    vmess = _share_link(*HOSTS["vmess-ws-tls"])
    links = ["hysteria2://auth@203.0.113.10:443#hy", vless, "not-a-link", "vless://broken", vmess, "vmess://%%%"]

    configs = _render_xray(links)

    assert [config["outbounds"][0]["protocol"] for config in configs] == ["vless", "vmess"]


@pytest.mark.parametrize(
    ("link", "password"),
    [
        ("ss://" + base64.b64encode(b"aes-128-gcm:pa:ss@203.0.113.10:8388").decode() + "#Legacy", "pa:ss"),
        ("ss://aes-128-gcm:pa%3Ass@203.0.113.10:8388#Plain", "pa:ss"),
        ("ss://" + base64.urlsafe_b64encode(b"aes-128-gcm:pa:ss").decode().rstrip("=") + "@203.0.113.10:8388", "pa:ss"),
        # Standard base64 with "/", which would end the authority of a parsed URL.
        ("ss://" + base64.b64encode(b"aes-128-gcm:p??").decode() + "@203.0.113.10:8388/?plugin=#Slash", "p??"),
    ],
)
def test_xray_external_links_read_shadowsocks_link_forms(link, password):
    (config,) = _render_xray([link])

    assert config["outbounds"][0]["settings"]["servers"] == [
        {"address": "203.0.113.10", "port": 8388, "password": password, "method": "aes-128-gcm"}
    ]


@pytest.mark.parametrize("query", ["type=ws&path=%2Fws", "type=xhttp&path=%2Fx&extra=%7B%22noGRPCHeader%22%3Atrue%7D"])
def test_xray_external_links_skip_shadowsocks_link_with_transport(query):
    userinfo = base64.b64encode(b"aes-128-gcm:secret").decode()
    vless = _share_link(*HOSTS["vless-reality-tcp"])

    configs = _render_xray([f"ss://{userinfo}@203.0.113.10:8388?{query}#Transport", vless])

    assert [config["outbounds"][0]["protocol"] for config in configs] == ["vless"]


def test_links_format_carries_external_links_as_is():
    links = StandardLinks()
    links.add_share_links(["vless://anything", "hysteria2://auth@203.0.113.10:443#hy"])

    assert links.render().splitlines() == ["vless://anything", "hysteria2://auth@203.0.113.10:443#hy"]


def test_external_config_env_still_goes_to_links_format_only(monkeypatch):
    vless = _share_link(*HOSTS["vless-reality-tcp"])
    monkeypatch.setattr(subscription_env_settings, "external_config", vless)

    assert StandardLinks().render() == vless
    assert json.loads(XrayConfiguration(xray_template_content=XRAY_TEMPLATE).render()) == []


def test_subscription_settings_external_links_are_trimmed():
    subscription = Subscription(rules=[], external_links=["  vless://a  ", "", " \n", "ss://b"])

    assert subscription.external_links == ["vless://a", "ss://b"]
    assert Subscription(rules=[]).external_links == []
    with pytest.raises(ValidationError):
        Subscription(rules=[], external_links=["vless://a vless://b"])


@pytest.mark.parametrize(("conf", "carried"), [(StandardLinks(), True), (OutlineConfiguration(), False)])
async def test_process_inbounds_and_tags_adds_external_links_to_share_link_formats(monkeypatch, conf, carried):
    monkeypatch.setattr("app.subscription.share.host_manager", SimpleNamespace(get_hosts=AsyncMock(return_value={})))
    user = SimpleNamespace(id=1, status=UserStatus.active, inbounds=[], proxy_settings=SimpleNamespace(dict=dict))
    link = _share_link(*HOSTS["shadowsocks"])

    rendered = await process_inbounds_and_tags(user, {}, conf, {}, external_links=[link])

    assert rendered == (link if carried else "{}")


async def test_process_inbounds_and_tags_builds_xray_and_sing_box_from_external_links(monkeypatch):
    monkeypatch.setattr("app.subscription.share.host_manager", SimpleNamespace(get_hosts=AsyncMock(return_value={})))
    user = SimpleNamespace(id=1, status=UserStatus.active, inbounds=[], proxy_settings=SimpleNamespace(dict=dict))
    link = _share_link(*HOSTS["vless-reality-tcp"])

    xray = json.loads(
        await process_inbounds_and_tags(
            user, {}, XrayConfiguration(xray_template_content=XRAY_TEMPLATE), {}, external_links=[link]
        )
    )
    sing_box = json.loads(await process_inbounds_and_tags(user, {}, SingBoxConfiguration(), {}, external_links=[link]))

    assert [config["remarks"] for config in xray] == ["External"]
    assert [outbound["tag"] for outbound in sing_box["outbounds"]] == ["External"]


async def test_generate_subscription_passes_external_links_from_settings(monkeypatch):
    templates = {"USER_AGENT_TEMPLATE": "", "GRPC_USER_AGENT_TEMPLATE": "", "XRAY_SUBSCRIPTION_TEMPLATE": ""}
    process = AsyncMock(return_value="[]")
    monkeypatch.setattr("app.subscription.share.subscription_client_templates", AsyncMock(return_value=templates))
    monkeypatch.setattr("app.subscription.share.subscription_xray_templates", AsyncMock(return_value={}))
    monkeypatch.setattr(
        "app.subscription.share.subscription_settings",
        AsyncMock(return_value=Subscription(rules=[], external_links=["vless://a"])),
    )
    monkeypatch.setattr("app.subscription.share.get_effective_custom_variables", lambda *_: [])
    monkeypatch.setattr("app.subscription.share.setup_format_variables", lambda *_: {})
    monkeypatch.setattr("app.subscription.share.process_inbounds_and_tags", process)
    config_cache.clear_sub_config_cache()
    user = SimpleNamespace(id=1, status=UserStatus.active, inbounds=[], data_limit=None, expire=None)

    try:
        assert await generate_subscription(user, "xray", False) == "[]"
    finally:
        config_cache.clear_sub_config_cache()

    assert process.await_args.kwargs["external_links"] == ["vless://a"]

import base64
import json

import pytest

from app.models.subscription import (
    GRPCTransportConfig,
    SubscriptionInboundData,
    TCPTransportConfig,
    TLSConfig,
    WebSocketTransportConfig,
    XHTTPTransportConfig,
)
from app.subscription.links import StandardLinks
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


def _render_xray(monkeypatch, external_config: str) -> list[dict]:
    monkeypatch.setattr(subscription_env_settings, "external_config", external_config)
    return json.loads(XrayConfiguration(xray_template_content=XRAY_TEMPLATE).render())


@pytest.mark.parametrize("name", HOSTS)
def test_xray_external_config_link_matches_host_configuration(monkeypatch, name):
    inbound, settings = HOSTS[name]
    expected = XrayConfiguration(xray_template_content=XRAY_TEMPLATE)
    expected.add(remark=inbound.remark, address=inbound.address, inbound=inbound, settings=settings)

    assert _render_xray(monkeypatch, _share_link(inbound, settings)) == expected.config


def test_xray_external_config_reads_each_link_and_skips_unsupported(monkeypatch):
    vless = _share_link(*HOSTS["vless-reality-tcp"])
    vmess = _share_link(*HOSTS["vmess-ws-tls"])
    external_config = f"hysteria2://auth@203.0.113.10:443#hy {vless}\nnot-a-link vless://broken {vmess} vmess://%%%"

    configs = _render_xray(monkeypatch, external_config)

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
def test_xray_external_config_reads_shadowsocks_link_forms(monkeypatch, link, password):
    (config,) = _render_xray(monkeypatch, link)

    assert config["outbounds"][0]["settings"]["servers"] == [
        {"address": "203.0.113.10", "port": 8388, "password": password, "method": "aes-128-gcm"}
    ]


@pytest.mark.parametrize("query", ["type=ws&path=%2Fws", "type=xhttp&path=%2Fx&extra=%7B%22noGRPCHeader%22%3Atrue%7D"])
def test_xray_external_config_skips_shadowsocks_link_with_transport(monkeypatch, query):
    userinfo = base64.b64encode(b"aes-128-gcm:secret").decode()
    vless = _share_link(*HOSTS["vless-reality-tcp"])

    configs = _render_xray(monkeypatch, f"ss://{userinfo}@203.0.113.10:8388?{query}#Transport {vless}")

    assert [config["outbounds"][0]["protocol"] for config in configs] == ["vless"]


def test_xray_external_config_unset_adds_nothing(monkeypatch):
    assert _render_xray(monkeypatch, "") == []

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest
from pydantic import ValidationError

from app.db.models import UserStatus
from app.models.settings import Subscription
from app.models.subscription import (
    GRPCTransportConfig,
    KCPTransportConfig,
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
from config import SubscriptionEnvSettings

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


FINALMASK = {"tcp": [{"type": "fragment", "settings": {"packets": "tlshello", "maxSplit": "3-6"}}]}

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
    # VLESS and Trojan links percent-encode the encoded custom stream name a second time.
    "vless-grpc-path": (
        _host(
            "vless",
            "grpc",
            GRPCTransportConfig(path="/svc/Stream", multi_mode=False),
            TLSConfig(tls="tls", sni="grpc.example.com"),
        ),
        {"id": UUID},
    ),
    "trojan-grpc-path": (
        _host(
            "trojan",
            "grpc",
            GRPCTransportConfig(path="/svc/Stream", multi_mode=False),
            TLSConfig(tls="tls", sni="grpc.example.com"),
        ),
        {"password": "secret"},
    ),
    "vless-tls-peer-names": (
        _host(
            "vless",
            "tcp",
            TCPTransportConfig(),
            TLSConfig(tls="tls", sni="cdn.example.com", verify_peer_cert_by_name=["a.example.com", "b.example.com"]),
        ),
        {"id": UUID},
    ),
    # Every value the link builder writes is read back: KCP MTU and TTI, the WebSocket heartbeat,
    # cipher suites, the ECH query mode, finalmask.
    "vless-kcp": (
        _host("vless", "kcp", KCPTransportConfig(mtu=1200, tti=10)),
        {"id": UUID},
    ),
    "vmess-kcp": (
        _host("vmess", "kcp", KCPTransportConfig(mtu=1200, tti=10)),
        {"id": UUID},
    ),
    "vless-ws-heartbeat": (
        _host(
            "vless",
            "ws",
            WebSocketTransportConfig(path="/ws", host="cdn.example.com", heartbeat_period=30),
            TLSConfig(tls="tls", sni="cdn.example.com"),
        ),
        {"id": UUID},
    ),
    "vless-tls-cipher-suites": (
        _host(
            "vless",
            "tcp",
            TCPTransportConfig(),
            TLSConfig(
                tls="tls",
                sni="cdn.example.com",
                fingerprint="unsafe",
                cipher_suites="TLS_AES_128_GCM_SHA256:TLS_CHACHA20_POLY1305_SHA256",
            ),
        ),
        {"id": UUID},
    ),
    "vless-tls-ech": (
        _host(
            "vless",
            "tcp",
            TCPTransportConfig(),
            TLSConfig(tls="tls", sni="cdn.example.com", ech_config_list="AEX+DQBBAAAgACB", ech_query_strategy="half"),
        ),
        {"id": UUID},
    ),
    "vless-finalmask": (
        _host(
            "vless",
            "tcp",
            TCPTransportConfig(),
            TLSConfig(tls="tls", sni="cdn.example.com"),
            finalmask=FINALMASK,
            finalmask_link=json.dumps(FINALMASK, separators=(",", ":")),
        ),
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


def test_xray_external_links_skip_shadowsocks_link_with_plugin():
    # SIP002: the client needs the plugin to connect; plain Shadowsocks without it would not work.
    userinfo = base64.b64encode(b"aes-128-gcm:secret").decode()
    vless = _share_link(*HOSTS["vless-reality-tcp"])
    plugin = quote("v2ray-plugin;mode=websocket;host=cdn.example.com", safe="")

    configs = _render_xray([f"ss://{userinfo}@203.0.113.10:8388/?plugin={plugin}#Plugin", vless])

    assert [config["outbounds"][0]["protocol"] for config in configs] == ["vless"]


@pytest.mark.parametrize(("query", "security"), [("type=tcp&sni=t.example.com", "tls"), ("security=none", "none")])
def test_xray_external_trojan_link_without_security_uses_tls(query, security):
    # Trojan servers expect TLS; only an explicit security=none keeps a plain connection.
    (config,) = _render_xray([f"trojan://secret@203.0.113.10:443?{query}#T"])

    assert config["outbounds"][0]["streamSettings"].get("security", "none") == security


def test_xray_external_link_matches_multi_mode_grpc_host_with_custom_path():
    # The link carries the client-side service name, which is not normalized a second time.
    inbound = _host("vmess", "grpc", GRPCTransportConfig(path="/svc/Tun|TunMulti", multi_mode=True))
    settings = {"id": UUID}
    expected = XrayConfiguration(xray_template_content=XRAY_TEMPLATE)
    expected.add(remark=inbound.remark, address=inbound.address, inbound=inbound, settings=settings)

    configs = _render_xray([_share_link(inbound, settings)])

    assert configs == expected.config
    grpc_settings = configs[0]["outbounds"][0]["streamSettings"]["grpcSettings"]
    assert (grpc_settings["serviceName"], grpc_settings["multiMode"]) == ("/svc/TunMulti", True)


@pytest.mark.parametrize("port", ["-1", "0", "65536", "abc"])
def test_external_link_with_port_outside_1_to_65535_is_skipped(port):
    vmess = (
        "vmess://"
        + base64.b64encode(
            json.dumps({"add": "203.0.113.10", "port": port, "id": UUID, "net": "tcp", "ps": "V"}).encode()
        ).decode()
    )
    links = [f"vless://{UUID}@203.0.113.10:{port}?type=tcp#L", f"trojan://secret@203.0.113.10:{port}#T", vmess]

    assert _render_xray(links) == []
    for builder in (ClashMetaConfiguration, SingBoxConfiguration):
        conf = builder()
        conf.add_share_links(links)
        assert _proxies(conf) == []


@pytest.mark.parametrize("extra", ["[1]", '"x"', "1", "0", "true"])
def test_external_link_with_non_object_xhttp_extra_is_skipped(extra):
    link = f"vless://{UUID}@203.0.113.10:443?type=xhttp&path=%2Fx&mode=auto&extra={quote(extra)}#X"

    assert _render_xray([link]) == []
    for builder in (ClashMetaConfiguration, SingBoxConfiguration):
        conf = builder()
        conf.add_share_links([link])
        assert _proxies(conf) == []


def test_links_format_carries_external_links_as_is():
    links = StandardLinks()
    links.add_share_links(["vless://anything", "hysteria2://auth@203.0.113.10:443#hy"])

    assert links.render().splitlines() == ["vless://anything", "hysteria2://auth@203.0.113.10:443#hy"]


def test_external_config_env_is_no_longer_read(monkeypatch):
    vless = _share_link(*HOSTS["vless-reality-tcp"])
    monkeypatch.setenv("EXTERNAL_CONFIG", vless)

    assert "external_config" not in SubscriptionEnvSettings(_env_file=None).model_dump()
    assert StandardLinks().render() == ""
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


def test_legacy_xray_fragment_is_ignored_while_singbox_and_finalmask_still_work():
    singbox_fragment = {"fragment": True, "fragment_fallback_delay": "100ms", "record_fragment": True}
    inbound = _host(
        "vless",
        "tcp",
        TCPTransportConfig(),
        TLSConfig(tls="tls", sni="cdn.example.com"),
        fragment_settings={
            "xray": {"packets": "tlshello", "length": "100-200", "interval": "10-20"},
            "sing_box": singbox_fragment,
        },
        finalmask=FINALMASK,
        finalmask_link=json.dumps(FINALMASK, separators=(",", ":")),
    )
    settings = {"id": UUID}
    link = _share_link(inbound, settings)
    assert "fragment=" not in link
    assert "fm=" in link

    xray = XrayConfiguration(xray_template_content=XRAY_TEMPLATE)
    xray.add(remark=inbound.remark, address=inbound.address, inbound=inbound, settings=settings)
    outbounds = xray.config[0]["outbounds"]
    assert all(outbound["tag"] not in ("dialer", "dsdialer") for outbound in outbounds)
    stream = next(outbound for outbound in outbounds if outbound["tag"] == "proxy")["streamSettings"]
    assert "sockopt" not in stream
    assert stream["finalmask"] == FINALMASK

    singbox = SingBoxConfiguration()
    singbox.add(remark=inbound.remark, address=inbound.address, inbound=inbound, settings=settings)
    tls = singbox.config["outbounds"][0]["tls"]
    assert all(tls[key] == value for key, value in singbox_fragment.items())

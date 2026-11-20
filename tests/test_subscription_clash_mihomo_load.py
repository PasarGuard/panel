"""Values that make Mihomo (and Clash) refuse to load the whole profile."""

import pytest
import yaml

from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.clash import ClashConfiguration, ClashMetaConfiguration

CLASH_CLASSES = (ClashConfiguration, ClashMetaConfiguration)
USER_ID = "11111111-1111-1111-1111-111111111111"
USER_AGENTS = '{"list": ["UA-Test/1.0"]}'

# Same proxy-groups shape as the default Clash template stored in the database.
GROUPS_TEMPLATE = """{{ conf | except("proxy-groups", "rules") | yaml }}
proxy-groups:
- name: 'PROXY'
  type: 'select'
  proxies:
  - 'Fastest'
  {{ proxy_remarks | yaml | indent(2) }}
- name: 'Fastest'
  type: 'url-test'
  proxies:
  {{ proxy_remarks | yaml | indent(2) }}
rules:
  - MATCH,PROXY
"""


def _tcp_http_inbound(
    *, host: str | list[str] = "", path: str = "", request: dict | None = None, random_user_agent: bool = False
) -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="vmess-http",
        inbound_tag="vmess-in",
        protocol="vmess",
        address="edge.example.com",
        port=80,
        network="tcp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(header_type="http", host=host, path=path, request=request),
        random_user_agent=random_user_agent,
    )


def _http_opts(config_class, inbound: SubscriptionInboundData) -> dict:
    config = config_class(user_agent_template_content=USER_AGENTS)
    config.add("vmess-http", "edge.example.com", inbound, {"id": USER_ID})
    node = config.data["proxies"][0]
    assert node["network"] == "http"
    assert "Host" not in node["http-opts"]
    return node["http-opts"]


def _assert_mihomo_http_opts_types(opts: dict):
    """Mihomo HTTPOptions: method string, path []string, headers map[string][]string."""
    assert set(opts) <= {"method", "path", "headers"}
    if "method" in opts:
        assert isinstance(opts["method"], str)
    if "path" in opts:
        assert isinstance(opts["path"], list)
        assert all(isinstance(item, str) for item in opts["path"])
    for name, values in opts.get("headers", {}).items():
        assert isinstance(name, str)
        assert isinstance(values, list), f"header {name} must be a list"
        assert all(isinstance(item, str) for item in values)


@pytest.mark.parametrize("config_class", CLASH_CLASSES)
def test_empty_proxy_list_still_gives_groups_a_proxy(config_class):
    config = config_class(clash_template_content=GROUPS_TEMPLATE)

    profile = yaml.safe_load(config.render())

    assert not profile.get("proxies")
    groups = {group["name"]: group["proxies"] for group in profile["proxy-groups"]}
    assert groups == {"PROXY": ["Fastest", "DIRECT"], "Fastest": ["DIRECT"]}
    assert config.proxy_remarks == []


@pytest.mark.parametrize("config_class", CLASH_CLASSES)
def test_proxy_groups_list_real_proxies_without_direct(config_class):
    config = config_class(clash_template_content=GROUPS_TEMPLATE)
    config.add("vmess-http", "edge.example.com", _tcp_http_inbound(), {"id": USER_ID})

    profile = yaml.safe_load(config.render())

    assert [proxy["name"] for proxy in profile["proxies"]] == ["vmess-http"]
    groups = {group["name"]: group["proxies"] for group in profile["proxy-groups"]}
    assert groups == {"PROXY": ["Fastest", "vmess-http"], "Fastest": ["vmess-http"]}


@pytest.mark.parametrize(
    ("interval", "expected"),
    [("30", 30), (45, 45), ("30s", 30), ("10-60", "10-60"), ("10-60s", "10-60"), ("abc", None), ("-5", None)],
)
def test_mihomo_hysteria2_hop_interval_has_no_seconds_suffix(interval, expected):
    inbound = SubscriptionInboundData(
        remark="hy2",
        inbound_tag="hy2-in",
        protocol="hysteria",
        address="edge.example.com",
        port=443,
        network="tcp",
        tls_config=TLSConfig(tls="tls", sni="cert.example.com"),
        transport_config=TCPTransportConfig(),
        finalmask={"quicParams": {"udpHop": {"ports": "20000-20010", "interval": interval}}},
    )
    meta = ClashMetaConfiguration()
    meta.add("hy2", "edge.example.com", inbound, {"auth": "auth-password"})

    node = meta.data["proxies"][0]
    assert node["ports"] == "20000-20010"
    assert node.get("hop-interval") == expected
    assert type(node.get("hop-interval")) is type(expected)


def test_mihomo_hysteria2_without_hop_interval_omits_it():
    inbound = SubscriptionInboundData(
        remark="hy2",
        inbound_tag="hy2-in",
        protocol="hysteria",
        address="edge.example.com",
        port=443,
        network="tcp",
        tls_config=TLSConfig(tls="tls", sni="cert.example.com"),
        transport_config=TCPTransportConfig(),
        finalmask={"quicParams": {"udpHop": {"ports": "20000-20010"}}},
    )
    meta = ClashMetaConfiguration()
    meta.add("hy2", "edge.example.com", inbound, {"auth": "auth-password"})

    assert "hop-interval" not in meta.data["proxies"][0]


@pytest.mark.parametrize("config_class", CLASH_CLASSES)
def test_http_opts_random_user_agent_is_a_header_list(config_class):
    opts = _http_opts(config_class, _tcp_http_inbound(host="cdn.example.com", path="/video", random_user_agent=True))

    _assert_mihomo_http_opts_types(opts)
    assert opts["path"] == ["/video"]
    assert opts["headers"]["Host"] == ["cdn.example.com"]
    assert opts["headers"]["User-Agent"] == ["UA-Test/1.0"]


@pytest.mark.parametrize("config_class", CLASH_CLASSES)
def test_http_opts_without_random_user_agent_or_host(config_class):
    opts = _http_opts(config_class, _tcp_http_inbound(path="/video"))

    _assert_mihomo_http_opts_types(opts)
    assert opts == {"path": ["/video"]}


@pytest.mark.parametrize("config_class", CLASH_CLASSES)
def test_http_opts_host_list_is_not_a_single_host(config_class):
    opts = _http_opts(config_class, _tcp_http_inbound(host=["a.example.com", "b.example.com"]))

    _assert_mihomo_http_opts_types(opts)
    assert "Host" not in opts.get("headers", {})


@pytest.mark.parametrize("config_class", CLASH_CLASSES)
def test_http_opts_take_only_method_path_headers_from_request(config_class):
    request = {
        "version": "1.1",
        "method": "POST",
        "path": "/from-request",
        "headers": {
            "Host": ["old.example.com"],
            "Accept-Encoding": ["gzip, deflate"],
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        },
    }
    opts = _http_opts(config_class, _tcp_http_inbound(host="cdn.example.com", request=request, random_user_agent=True))

    _assert_mihomo_http_opts_types(opts)
    assert "version" not in opts
    assert opts["method"] == "POST"
    assert opts["path"] == ["/from-request"]
    headers = opts["headers"]
    assert headers["Host"] == ["cdn.example.com"]
    assert headers["Accept-Encoding"] == ["gzip, deflate"]
    assert headers["Pragma"] == ["no-cache"]
    assert headers["Connection"] == ["keep-alive"]
    assert headers["User-Agent"] == ["UA-Test/1.0"]


@pytest.mark.parametrize("config_class", CLASH_CLASSES)
def test_http_opts_host_path_override_request_and_request_host_is_kept_without_host(config_class):
    request = {"path": ["/a", "/b"], "headers": {"Host": ["old.example.com"]}}

    with_host = _http_opts(config_class, _tcp_http_inbound(host="cdn.example.com", path="/host-path", request=request))
    assert with_host["path"] == ["/host-path"]
    assert with_host["headers"] == {"Host": ["cdn.example.com"]}

    without_host = _http_opts(config_class, _tcp_http_inbound(request=request))
    _assert_mihomo_http_opts_types(without_host)
    assert without_host["path"] == ["/a", "/b"]
    assert without_host["headers"] == {"Host": ["old.example.com"]}


@pytest.mark.parametrize("config_class", CLASH_CLASSES)
@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("xchacha20-poly1305", "xchacha20-ietf-poly1305"),
        ("chacha20-poly1305", "chacha20-ietf-poly1305"),
        ("chacha20-ietf-poly1305", "chacha20-ietf-poly1305"),
        ("aes-256-gcm", "aes-256-gcm"),
    ],
)
def test_shadowsocks_cipher_uses_mihomo_names(config_class, method, expected):
    inbound = SubscriptionInboundData(
        remark="ss",
        inbound_tag="ss-in",
        protocol="shadowsocks",
        address="edge.example.com",
        port=443,
        network="tcp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(),
        method=method,
        password="server-password",
    )
    config = config_class()
    config.add("ss", "edge.example.com", inbound, {"method": method, "password": "user-password"})

    node = config.data["proxies"][0]
    assert node["cipher"] == expected
    if "method" in node:
        assert node["method"] == expected

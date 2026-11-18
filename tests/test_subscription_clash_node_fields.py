from urllib.parse import urlparse

import pytest

from app.models.subscription import (
    SubscriptionInboundData,
    TCPTransportConfig,
    TLSConfig,
    XHTTPTransportConfig,
)
from app.subscription.clash import ClashConfiguration, ClashMetaConfiguration
from app.subscription.links import StandardLinks

USER_ID = "11111111-1111-1111-1111-111111111111"


def _inbound(
    *,
    protocol: str = "vless",
    network: str = "tcp",
    address: str = "edge.example.com",
    tls_config: TLSConfig | None = None,
    transport_config=None,
    **extra,
) -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="node",
        inbound_tag="node-inbound",
        protocol=protocol,
        address=address,
        port=443,
        network=network,
        tls_config=tls_config or TLSConfig(),
        transport_config=transport_config or TCPTransportConfig(path="", host=[]),
        priority=0,
        **extra,
    )


def _meta_node(address: str, inbound: SubscriptionInboundData, settings: dict | None = None) -> dict:
    conf = ClashMetaConfiguration()
    conf.add("node", address, inbound, settings or {"id": USER_ID})
    assert len(conf.data["proxies"]) == 1
    return conf.data["proxies"][0]


# --- server address: bracketed IPv6 -------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("[2001:db8::1]", "2001:db8::1"),
        ("[::1]", "::1"),
        ("2001:db8::1", "2001:db8::1"),
        ("edge.example.com", "edge.example.com"),
        ("203.0.113.10", "203.0.113.10"),
    ],
)
@pytest.mark.parametrize("conf_class", [ClashConfiguration, ClashMetaConfiguration])
def test_clash_server_has_no_ipv6_brackets(conf_class, address, expected):
    conf = conf_class()
    conf.add("node", address, _inbound(protocol="vmess", address=address), {"id": USER_ID})

    assert conf.data["proxies"][0]["server"] == expected


def test_clash_meta_xhttp_download_server_has_no_ipv6_brackets():
    download = _inbound(address="[2001:db8::2]", network="xhttp", transport_config=XHTTPTransportConfig(path="/d"))
    inbound = _inbound(network="xhttp", transport_config=XHTTPTransportConfig(path="/u", download_settings=download))

    node = _meta_node("[2001:db8::1]", inbound)

    assert node["server"] == "2001:db8::1"
    assert node["xhttp-opts"]["download-settings"]["server"] == "2001:db8::2"


def test_clash_meta_xhttp_raw_xray_download_server_has_no_ipv6_brackets():
    transport = XHTTPTransportConfig(path="/u", download_settings={"address": "[2001:db8::3]", "port": 443})

    node = _meta_node("edge.example.com", _inbound(network="xhttp", transport_config=transport))

    assert node["xhttp-opts"]["download-settings"]["server"] == "2001:db8::3"


def test_links_keep_ipv6_brackets():
    links = StandardLinks()
    links.add("node", "[2001:db8::1]", _inbound(address="[2001:db8::1]"), {"id": USER_ID})

    assert urlparse(links.links[0]).netloc == f"{USER_ID}@[2001:db8::1]:443"


# --- client-fingerprint ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fingerprint", "expected"),
    [("randomizednoalpn", "random"), ("unsafe", "chrome"), ("ios", "ios"), ("randomized", "randomized")],
)
def test_clash_meta_client_fingerprint_uses_mihomo_names(fingerprint, expected):
    tls = TLSConfig(tls="reality", sni="sni.example.com", fingerprint=fingerprint, reality_public_key="pk")

    node = _meta_node("edge.example.com", _inbound(tls_config=tls))

    assert node["client-fingerprint"] == expected


def test_clash_meta_xhttp_download_fingerprint_uses_mihomo_names():
    download = _inbound(
        network="xhttp",
        tls_config=TLSConfig(tls="tls", sni="d.example.com", fingerprint="randomizednoalpn"),
        transport_config=XHTTPTransportConfig(path="/d"),
    )
    inbound = _inbound(network="xhttp", transport_config=XHTTPTransportConfig(path="/u", download_settings=download))

    node = _meta_node("edge.example.com", inbound)

    assert node["xhttp-opts"]["download-settings"]["client-fingerprint"] == "random"


# --- xhttp session-table / session-length ---------------------------------------------------------


def _xhttp_opts(table, length) -> dict:
    transport = XHTTPTransportConfig(path="/u", session_id_table=table, session_id_length=length)
    return _meta_node("edge.example.com", _inbound(network="xhttp", transport_config=transport))["xhttp-opts"]


@pytest.mark.parametrize(
    ("table", "length"),
    [("number", "16-32"), ("hex", "8"), ("abcdefghijklmnopqrstuvwxyz0123456789", "10-12"), ("ab", "31")],
)
def test_clash_meta_xhttp_writes_valid_session_id_pair(table, length):
    opts = _xhttp_opts(table, length)

    assert opts["session-table"] == table
    assert opts["session-length"] == length


def test_clash_meta_xhttp_session_table_without_length_uses_mihomo_default():
    opts = _xhttp_opts("number", None)

    assert opts["session-table"] == "number"
    assert "session-length" not in opts


@pytest.mark.parametrize(
    ("table", "length"),
    [
        ("number", "4"),  # 10^4 is below Mihomo's 2<<30 floor
        ("hex", "7"),  # 16^7 = 2^28
        ("ab", "30"),  # 2^30 = (2<<30) / 2
        ("x", "16-32"),  # one-character table
        ("number", "0"),  # length must be > 0
        ("number", "12-8"),  # min > max
        ("hex", "9999999999999999"),  # a length Mihomo cannot size
        ("ascii-only-é-table-ABCDEFGHIJKLMNOP", "16"),  # Mihomo accepts ASCII only
    ],
)
def test_clash_meta_xhttp_skips_session_id_pair_mihomo_rejects(table, length):
    opts = _xhttp_opts(table, length)

    assert "session-table" not in opts
    assert "session-length" not in opts


@pytest.mark.parametrize(("table", "length"), [(None, None), (None, "16"), ("", "16"), ("uuid", None)])
def test_clash_meta_xhttp_omits_session_id_when_not_set(table, length):
    opts = _xhttp_opts(table, length)

    assert "session-table" not in opts
    assert "session-length" not in opts


@pytest.mark.parametrize(
    ("table", "length", "expected"),
    [
        ("number", "10", True),  # 10^10 >= 2^31
        ("number", "9", False),  # 10^9 < 2^31
        ("number", "9-10", True),
        ("ab", "1-31", True),  # 2 + 4 + ... + 2^31: Mihomo sums every length in the range
        ("ab", "1-30", False),  # 2^31 - 2
    ],
)
def test_mihomo_session_id_room_matches_go_threshold(table, length, expected):
    assert bool(ClashMetaConfiguration._mihomo_session_id_opts(table, length)) is expected


# --- wireguard ------------------------------------------------------------------------------------


def _wireguard_node(conf_class, **extra) -> dict:
    conf = conf_class()
    inbound = _inbound(protocol="wireguard", network="", wireguard_public_key="server-pub", **extra)
    conf.add("wg", "wg.example.com", inbound, {"private_key": "client-priv", "peer_ips": ["10.0.0.2/32"]})
    return conf.data["proxies"][0]


def test_clash_meta_wireguard_writes_keepalive_and_ip_dns():
    node = _wireguard_node(ClashMetaConfiguration, wireguard_keepalive=25, wireguard_dns=["1.1.1.1", "2606:4700::1111"])

    assert node["persistent-keepalive"] == 25
    assert node["dns"] == ["1.1.1.1", "2606:4700::1111"]
    assert node["remote-dns-resolve"] is True


@pytest.mark.parametrize(
    "dns", [None, [], ["1.1.1.1", "dns.example.com"], ["https://1.1.1.1/dns-query"], ["fe80::1%eth0"]]
)
def test_clash_meta_wireguard_skips_unset_or_non_ip_dns(dns):
    node = _wireguard_node(ClashMetaConfiguration, wireguard_keepalive=None, wireguard_dns=dns)

    assert "persistent-keepalive" not in node
    assert "dns" not in node
    assert "remote-dns-resolve" not in node


def test_clash_meta_wireguard_skips_zero_keepalive():
    node = _wireguard_node(ClashMetaConfiguration, wireguard_keepalive=0)

    assert "persistent-keepalive" not in node


def test_classic_clash_wireguard_gets_no_mihomo_only_fields():
    node = _wireguard_node(ClashConfiguration, wireguard_keepalive=25, wireguard_dns=["1.1.1.1"])

    assert "persistent-keepalive" not in node
    assert "remote-dns-resolve" not in node
    assert "dns" not in node

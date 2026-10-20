from urllib.parse import parse_qs, urlparse

from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.links import StandardLinks, _mtproto_client_secret

SECRET = "00112233445566778899aabbccddeeff"


def _inbound(*, modes: dict[str, bool] | None = None, tls_domain: str = "") -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="mtproto",
        inbound_tag="mtproto",
        protocol="mtproto",
        address="edge.example.com",
        port=443,
        network="tcp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(),
        mtproto_modes=modes or {},
        mtproto_tls_domain=tls_domain,
        priority=0,
    )


def test_mtproto_client_secret_classic():
    assert _mtproto_client_secret(SECRET, _inbound(modes={"classic": True})) == SECRET


def test_mtproto_client_secret_secure():
    assert _mtproto_client_secret(SECRET, _inbound(modes={"secure": True})) == "dd" + SECRET


def test_mtproto_client_secret_tls_prefers_fake_tls():
    inbound = _inbound(modes={"classic": True, "secure": True, "tls": True}, tls_domain="cloudflare.com")
    assert _mtproto_client_secret(SECRET, inbound) == "ee" + SECRET + b"cloudflare.com".hex()


def test_mtproto_subscription_link():
    links = StandardLinks()
    inbound = _inbound(modes={"secure": True})
    links.add("EU proxy", "edge.example.com", inbound, {"secret": SECRET})
    assert len(links.links) == 1
    parsed = urlparse(links.links[0])
    assert parsed.scheme == "https"
    assert parsed.netloc == "t.me"
    assert parsed.path == "/proxy"
    query = parse_qs(parsed.query)
    assert query["server"] == ["edge.example.com"]
    assert query["port"] == ["443"]
    assert query["secret"] == ["dd" + SECRET]

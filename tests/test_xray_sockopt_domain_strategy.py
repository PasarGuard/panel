from app.models.host import XraySockoptDomainStrategy
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.xray import XrayConfiguration


def _inbound(
    protocol: str,
    *,
    network: str = "tcp",
    strategy: XraySockoptDomainStrategy = XraySockoptDomainStrategy.as_is,
) -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark=protocol,
        inbound_tag=f"{protocol}-inbound",
        protocol=protocol,
        address="edge.example.com",
        port=443,
        network=network,
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(),
        xray_sockopt_domain_strategy=strategy,
        priority=0,
    )


def test_hysteria_uses_host_sockopt_domain_strategy():
    xray = XrayConfiguration()
    outbound, _ = xray._build_hysteria(
        "edge.example.com",
        _inbound(
            "hysteria",
            network="hysteria",
            strategy=XraySockoptDomainStrategy.force_ipv4,
        ),
        {"auth": "test-password"},
    )

    assert outbound["streamSettings"]["sockopt"]["domainStrategy"] == "ForceIPv4"


def test_shadowsocks_uses_host_sockopt_domain_strategy(monkeypatch):
    xray = XrayConfiguration()
    monkeypatch.setattr(
        xray,
        "detect_shadowsocks_2022",
        lambda *args: ("aes-128-gcm", "test-password"),
    )
    outbound, _ = xray._build_shadowsocks(
        "edge.example.com",
        _inbound(
            "shadowsocks",
            strategy=XraySockoptDomainStrategy.use_ipv6,
        ),
        {
            "method": "aes-128-gcm",
            "password": "test-password",
        },
    )

    assert outbound["streamSettings"]["sockopt"]["domainStrategy"] == "UseIPv6"


def test_wireguard_keeps_protocol_specific_domain_strategy():
    xray = XrayConfiguration()
    inbound = _inbound(
        "wireguard",
        strategy=XraySockoptDomainStrategy.use_ip,
    )
    inbound.wireguard_public_key = "public-key"
    inbound.wireguard_allowed_ips = ["0.0.0.0/0", "::/0"]

    outbound, _ = xray._build_wireguard(
        "edge.example.com",
        inbound,
        {
            "private_key": "private-key",
            "peer_ips": ["10.0.0.2/32"],
        },
    )

    assert outbound["settings"]["domainStrategy"] == "ForceIP"
    assert "sockopt" not in outbound.get("streamSettings", {})

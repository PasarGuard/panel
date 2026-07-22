from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.clash import ClashMetaConfiguration


USER_ID = "11111111-1111-1111-1111-111111111111"


def _inbound(protocol: str, network: str = "tcp") -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark=protocol,
        inbound_tag=f"{protocol}-inbound",
        protocol=protocol,
        address="edge.example.com",
        port=443,
        network=network,
        tls_config=TLSConfig(tls="tls", sni="cert.example.com"),
        transport_config=TCPTransportConfig(),
        priority=0,
    )


def test_clash_meta_hysteria2_uses_sni_not_servername():
    meta = ClashMetaConfiguration()
    meta.add("meta hysteria", "edge.example.com", _inbound("hysteria"), {"auth": "auth-password"})

    assert len(meta.data["proxies"]) == 1
    node = meta.data["proxies"][0]
    assert node["type"] == "hysteria2"
    assert node["sni"] == "cert.example.com"
    assert "servername" not in node


def test_clash_meta_trojan_still_uses_sni():
    meta = ClashMetaConfiguration()
    meta.add("meta trojan", "edge.example.com", _inbound("trojan"), {"password": "trojan-password"})

    node = meta.data["proxies"][0]
    assert node["type"] == "trojan"
    assert node["sni"] == "cert.example.com"
    assert "servername" not in node


def test_clash_meta_vless_still_uses_servername():
    meta = ClashMetaConfiguration()
    meta.add("meta vless", "edge.example.com", _inbound("vless"), {"id": USER_ID})

    node = meta.data["proxies"][0]
    assert node["type"] == "vless"
    assert node["servername"] == "cert.example.com"
    assert "sni" not in node

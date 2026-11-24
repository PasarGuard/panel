import json
from urllib.parse import parse_qs, urlparse

from app.core.xray import XRayConfig
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.clash import ClashConfiguration, ClashMetaConfiguration
from app.subscription.links import StandardLinks
from app.subscription.singbox import SingBoxConfiguration
from app.subscription.xray import XrayConfiguration


SETTINGS = {"method": "chacha20-ietf-poly1305", "password": "user-password"}


def _shadowsocks_inbound(*, header_type="http"):
    return SubscriptionInboundData(
        remark="ss-obfs",
        inbound_tag="ss-in",
        protocol="shadowsocks",
        address="edge.example.com",
        port=443,
        network="tcp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(
            header_type=header_type,
            host="obfs.example.com",
            path="/",
        ),
        method="aes-256-gcm",
        password="server-password",
    )


def test_shadowsocks_http_obfs_is_serialized_in_supported_formats():
    inbound = _shadowsocks_inbound()

    links = StandardLinks()
    links.add("ss", "edge.example.com", inbound, SETTINGS)
    link = links.links[0]
    plugin = parse_qs(urlparse(link).query)["plugin"][0]
    assert plugin == "obfs-local;obfs=http;obfs-host=obfs.example.com"

    for config in (ClashConfiguration(), ClashMetaConfiguration()):
        config.add("ss", "edge.example.com", inbound, SETTINGS)
        node = config.data["proxies"][0]
        assert node["plugin"] == "obfs"
        assert node["plugin-opts"] == {"mode": "http", "host": "obfs.example.com"}

    singbox = SingBoxConfiguration()
    singbox.add("ss", "edge.example.com", inbound, SETTINGS)
    outbound = singbox.config["outbounds"][0]
    assert outbound["plugin"] == "obfs-local"
    assert outbound["plugin_opts"] == "obfs=http;obfs-host=obfs.example.com"

    xray = XrayConfiguration(xray_template_content=json.dumps({"outbounds": []}))
    xray.add("ss", "edge.example.com", inbound, SETTINGS)
    stream_settings = xray.config[0]["outbounds"][0]["streamSettings"]
    assert stream_settings["network"] == "tcp"
    assert stream_settings["tcpSettings"]["header"] == {
        "type": "http",
        "request": {"path": ["/"], "headers": {"Host": ["obfs.example.com"]}},
    }


def test_shadowsocks_without_http_obfs_keeps_existing_serialization():
    inbound = _shadowsocks_inbound(header_type="none")

    links = StandardLinks()
    links.add("ss", "edge.example.com", inbound, SETTINGS)
    assert "?plugin=" not in links.links[0]

    clash = ClashMetaConfiguration()
    clash.add("ss", "edge.example.com", inbound, SETTINGS)
    assert "plugin" not in clash.data["proxies"][0]

    singbox = SingBoxConfiguration()
    singbox.add("ss", "edge.example.com", inbound, SETTINGS)
    assert "plugin" not in singbox.config["outbounds"][0]


def test_xray_core_preserves_shadowsocks_http_header_metadata():
    core = XRayConfig(
        {
            "inbounds": [
                {
                    "tag": "ss-in",
                    "protocol": "shadowsocks",
                    "port": 443,
                    "settings": {"method": "aes-256-gcm", "password": "server-password"},
                    "streamSettings": {
                        "network": "tcp",
                        "tcpSettings": {
                            "header": {
                                "type": "http",
                                "request": {"path": ["/"], "headers": {"Host": ["obfs.example.com"]}},
                            }
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        }
    )

    inbound = core.inbounds_by_tag["ss-in"]
    assert inbound["header_type"] == "http"
    assert inbound["host"] == ["obfs.example.com"]
    assert inbound["path"] == "/"

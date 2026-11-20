import pytest

from app.models.proxy import ShadowsocksMethods
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.singbox import SingBoxConfiguration

# Method names sing-box 1.14 accepts for a classic (non-2022) shadowsocks outbound.
SINGBOX_METHODS = {
    "aes-128-gcm",
    "aes-192-gcm",
    "aes-256-gcm",
    "chacha20-ietf-poly1305",
    "xchacha20-ietf-poly1305",
}


def _inbound() -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="ss",
        inbound_tag="ss-in",
        protocol="shadowsocks",
        address="edge.example.com",
        port=443,
        network="tcp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(),
        method="aes-256-gcm",
        password="server-password",
    )


def _method_for(user_method: str) -> str:
    config = SingBoxConfiguration()
    config.add("ss", "edge.example.com", _inbound(), {"method": user_method, "password": "user-password"})
    return config.config["outbounds"][0]["method"]


@pytest.mark.parametrize(
    ("user_method", "expected"),
    [
        ("xchacha20-poly1305", "xchacha20-ietf-poly1305"),
        ("chacha20-poly1305", "chacha20-ietf-poly1305"),
        ("chacha20-ietf-poly1305", "chacha20-ietf-poly1305"),
        ("aes-256-gcm", "aes-256-gcm"),
    ],
)
def test_singbox_shadowsocks_method_uses_names_singbox_knows(user_method, expected):
    assert _method_for(user_method) == expected


@pytest.mark.parametrize("user_method", [method.value for method in ShadowsocksMethods])
def test_every_panel_shadowsocks_method_is_accepted_by_singbox(user_method):
    assert _method_for(user_method) in SINGBOX_METHODS

import io
import zipfile
from app.models.host import AmneziaProperties
from app.models.subscription import TCPTransportConfig, SubscriptionInboundData, TLSConfig
from app.subscription.wireguard import WireGuardConfiguration
from app.subscription.singbox import SingBoxConfiguration


def test_amnezia_properties_v31():
    props = AmneziaProperties(
        jc=4,
        jmin=40,
        jmax=70,
        s1=0,
        s2=0,
        s3=0,
        s4=0,
        h1="1",
        h2="2",
        h3="3",
        h4="4",
        i1="some_mimic",
        header_protection_key="secret_key_base64",
        content_padding_addition="0-16",
        rekey_after_time=120,
        rekey_timeout=5,
        reject_after_time=180,
        keepalive_timeout=10,
        max_handshake_attempts=18,
        random_trailers="on",
        disable_cookies="off",
    )
    dumped = props.model_dump(exclude_none=True)
    assert dumped["jc"] == 4
    assert dumped["header_protection_key"] == "secret_key_base64"
    assert dumped["content_padding_addition"] == "0-16"
    assert dumped["rekey_after_time"] == 120
    assert dumped["rekey_timeout"] == 5
    assert dumped["reject_after_time"] == 180
    assert dumped["keepalive_timeout"] == 10
    assert dumped["max_handshake_attempts"] == 18
    assert dumped["random_trailers"] == "on"
    assert dumped["disable_cookies"] == "off"


def test_amnezia_properties_empty_and_bool_normalization():
    props = AmneziaProperties(
        jc="",
        header_protection_key="",
        rekey_after_time="",
        random_trailers=True,
        disable_cookies=False,
    )
    assert props.jc is None
    assert props.header_protection_key is None
    assert props.rekey_after_time is None
    assert props.random_trailers == "on"
    assert props.disable_cookies == "off"


def test_wireguard_config_generator_v31():
    inbound = SubscriptionInboundData(
        remark="test_profile",
        inbound_tag="wg_inbound",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(),
        priority=1,
        protocol="wireguard",
        network="udp",
        port=51820,
        wireguard_public_key="server_pub_key",
        wireguard_allowed_ips=["0.0.0.0/0"],
        wireguard_amnezia={
            "jc": 4,
            "jmin": 40,
            "jmax": 70,
            "s1": 0,
            "s2": 0,
            "s3": 0,
            "s4": 0,
            "h1": "1",
            "h2": "2",
            "h3": "3",
            "h4": "4",
            "header_protection_key": "my_hp_key",
            "content_padding_addition": "0-16",
            "rekey_after_time": 120,
            "rekey_timeout": 5,
            "reject_after_time": 180,
            "keepalive_timeout": 10,
            "max_handshake_attempts": 18,
            "random_trailers": "on",
            "disable_cookies": "off",
        },
    )

    generator = WireGuardConfiguration()
    generator.add(
        remark="test_profile",
        address="198.51.100.1",
        inbound=inbound,
        settings={
            "private_key": "client_priv_key",
            "peer_ips": ["10.0.0.2/32"],
        },
    )

    rendered_bytes = generator.render()
    with zipfile.ZipFile(io.BytesIO(rendered_bytes)) as zf:
        conf_names = zf.namelist()
        assert len(conf_names) == 1
        content = zf.read(conf_names[0]).decode("utf-8")
        assert "HeaderProtectionKey = my_hp_key" in content
        assert "ContentPaddingAddition = 0-16" in content
        assert "RekeyAfterTime = 120" in content
        assert "RekeyTimeout = 5" in content
        assert "RejectAfterTime = 180" in content
        assert "KeepaliveTimeout = 10" in content
        assert "MaxHandshakeAttempts = 18" in content
        assert "RandomTrailers = on" in content
        assert "DisableCookies = off" in content


def test_singbox_config_ignores_amnezia():
    inbound = SubscriptionInboundData(
        remark="test_profile",
        inbound_tag="wg_inbound",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(),
        priority=1,
        protocol="wireguard",
        network="udp",
        port=51820,
        wireguard_public_key="server_pub_key",
        wireguard_allowed_ips=["0.0.0.0/0"],
        wireguard_amnezia={
            "jc": 4,
            "header_protection_key": "my_hp_key",
            "content_padding_addition": "0-16",
            "rekey_after_time": "120",
            "random_trailers": "on",
            "disable_cookies": "off",
        },
    )

    builder = SingBoxConfiguration()
    endpoint = builder._build_wireguard(
        remark="test_profile",
        address="198.51.100.1",
        inbound=inbound,
        settings={
            "private_key": "client_priv_key",
            "peer_ips": ["10.0.0.2/32"],
        },
    )

    # Sing-box does not support AmneziaWG; verify standard WireGuard endpoint without amnezia properties
    assert "jc" not in endpoint
    assert "header_protection_key" not in endpoint
    assert "content_padding_addition" not in endpoint
    assert "rekey_after_time" not in endpoint
    assert "random_trailers" not in endpoint
    assert "disable_cookies" not in endpoint
    assert endpoint["type"] == "wireguard"
    assert endpoint["tag"] == "test_profile"

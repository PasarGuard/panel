import base64
import io
import zipfile

from app.models.host import AmneziaProperties
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.singbox import SingBoxConfiguration
from app.subscription.wireguard import WireGuardConfiguration


def test_amnezia_properties_v31():
    valid_key = base64.b64encode(b"k" * 32).decode()
    props = AmneziaProperties(
        jc=4,
        jmin=40,
        jmax=70,
        s1=12,
        s2=12,
        s3=12,
        s4=12,
        h1="1",
        h2="2",
        h3="3",
        h4="4",
        i1="some_mimic",
        header_protection_key=valid_key,
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
    assert dumped["header_protection_key"] == valid_key
    assert dumped["content_padding_addition"] == "0-16"
    assert dumped["rekey_after_time"] == 120
    assert dumped["rekey_timeout"] == 5
    assert dumped["reject_after_time"] == 180
    assert dumped["keepalive_timeout"] == 10
    assert dumped["max_handshake_attempts"] == 18
    assert dumped["random_trailers"] == "on"
    assert dumped["disable_cookies"] == "off"


def test_amnezia_properties_empty_normalization():
    props = AmneziaProperties(
        jc="",
        header_protection_key="",
        rekey_after_time="",
        random_trailers="on",
        disable_cookies="off",
    )
    assert props.jc is None
    assert props.header_protection_key is None
    assert props.rekey_after_time is None
    assert props.random_trailers == "on"
    assert props.disable_cookies == "off"


def test_header_protection_validation():
    import pytest
    from pydantic import ValidationError

    valid_key = base64.b64encode(b"a" * 32).decode()

    # Valid HP key and s1-s4 >= 12
    p = AmneziaProperties(header_protection_key=valid_key, s1=12, s2=12, s3=12, s4=12)
    assert p.header_protection_key == valid_key

    # HP not configured (None or "") allows s1-s4 < 12
    p2 = AmneziaProperties(header_protection_key=None, s1=0, s2=0, s3=0, s4=0)
    assert p2.s1 == 0
    p3 = AmneziaProperties(header_protection_key="", s1=0, s2=0, s3=0, s4=0)
    assert p3.header_protection_key is None

    # Invalid base64
    with pytest.raises(ValidationError):
        AmneziaProperties(header_protection_key="not-base64-@@", s1=12, s2=12, s3=12, s4=12)

    # Invalid length (16 bytes instead of 32)
    short_key = base64.b64encode(b"a" * 16).decode()
    with pytest.raises(ValidationError):
        AmneziaProperties(header_protection_key=short_key, s1=12, s2=12, s3=12, s4=12)

    # S1 < 12
    with pytest.raises(ValidationError):
        AmneziaProperties(header_protection_key=valid_key, s1=11, s2=12, s3=12, s4=12)

    # S4 is None
    with pytest.raises(ValidationError):
        AmneziaProperties(header_protection_key=valid_key, s1=12, s2=12, s3=12, s4=None)


def test_amnezia_numeric_ranges_and_toggles():
    import pytest
    from pydantic import ValidationError

    # Integer inputs normalized to int
    p1 = AmneziaProperties(rekey_after_time=120, rekey_timeout="5")
    assert p1.rekey_after_time == 120
    assert p1.rekey_timeout == 5

    # Range inputs accepted and formatted
    p2 = AmneziaProperties(
        rekey_after_time="120-180",
        rekey_timeout=" 5 - 10 ",
        reject_after_time="150-200",
        keepalive_timeout="10-25",
        max_handshake_attempts="15-20",
    )
    assert p2.rekey_after_time == "120-180"
    assert p2.rekey_timeout == "5-10"
    assert p2.reject_after_time == "150-200"
    assert p2.keepalive_timeout == "10-25"
    assert p2.max_handshake_attempts == "15-20"

    # Invalid ranges: lower > upper
    with pytest.raises(ValidationError):
        AmneziaProperties(rekey_after_time="180-120")

    # Invalid non-numeric / negative / exceeding 65535
    for bad in ("abc", "-5", "70000", "10-70000", True):
        with pytest.raises(ValidationError):
            AmneziaProperties(rekey_after_time=bad)

    # Toggle validation: strictly "on" or "off" via pattern r"^(on|off)$"
    assert AmneziaProperties(random_trailers="on").random_trailers == "on"
    assert AmneziaProperties(random_trailers="off").random_trailers == "off"
    assert AmneziaProperties(disable_cookies="on").disable_cookies == "on"
    assert AmneziaProperties(disable_cookies="off").disable_cookies == "off"
    assert AmneziaProperties(random_trailers=None).random_trailers is None
    assert AmneziaProperties(random_trailers="").random_trailers is None

    # Unsupported toggle values
    for invalid_toggle in ("maybe", "unknown", "1", "0", 123, True, False, "true", "false", "ON", "OFF"):
        with pytest.raises(ValidationError):
            AmneziaProperties(random_trailers=invalid_toggle)
        with pytest.raises(ValidationError):
            AmneziaProperties(disable_cookies=invalid_toggle)


def test_content_padding_addition_validation():
    import pytest
    from pydantic import ValidationError

    # Valid values
    assert AmneziaProperties(content_padding_addition=None).content_padding_addition is None
    assert AmneziaProperties(content_padding_addition="").content_padding_addition is None
    assert AmneziaProperties(content_padding_addition="0").content_padding_addition == "0"
    assert AmneziaProperties(content_padding_addition="16").content_padding_addition == "16"
    assert AmneziaProperties(content_padding_addition="0-16").content_padding_addition == "0-16"
    assert AmneziaProperties(content_padding_addition="1234567890123456").content_padding_addition == "1234567890123456"
    assert (
        AmneziaProperties(content_padding_addition="1-1234567890123456").content_padding_addition
        == "1-1234567890123456"
    )

    # Invalid values
    for invalid in ("abc", "0-16-32", "12345678901234567", "0-", "-16", "0 16", "0,16", "1.5"):
        with pytest.raises(ValidationError):
            AmneziaProperties(content_padding_addition=invalid)


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


def test_wireguard_toggles_controlled_and_serialized():
    from app.subscription.base import BaseSubscription

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
            "random_trailers": "on",
            "disable_cookies": "off",
        },
    )

    # 1. Test WireGuardConfiguration outputs strictly "on" and "off"
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
        content = zf.read(zf.namelist()[0]).decode("utf-8")
        assert "RandomTrailers = on" in content
        assert "DisableCookies = off" in content
        assert "True" not in content
        assert "False" not in content

    # 2. Test BaseSubscription URI outputs strictly "on" and "off"
    base = BaseSubscription()
    built = base._build_wireguard_components(
        remark="test_profile",
        address="198.51.100.1",
        inbound=inbound,
        settings={
            "private_key": "client_priv_key",
            "peer_ips": ["10.0.0.2/32"],
        },
    )
    assert built is not None
    assert built["payload"]["random_trailers"] == "on"
    assert built["payload"]["disable_cookies"] == "off"
    assert "random_trailers=on" in built["uri"]
    assert "disable_cookies=off" in built["uri"]

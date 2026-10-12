import base64
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.core.wireguard import WireGuardConfig
from app.core.xray import XRayConfig
from app.db.crud.wireguard import wg_core_interfaces, wg_core_tags, wg_namespaces
from app.models.core import CoreType
from app.models.protocol import ProxyProtocol
from app.node.user import _serialize_user_for_node
from app.utils.crypto import generate_wireguard_keypair


def xray_config(secret, *, address=None):
    return {
        "inbounds": [
            {
                "tag": "xray-wg",
                "protocol": "wireguard",
                "port": 51821,
                "settings": {
                    "secretKey": secret,
                    "address": address if address is not None else ["10.90.0.1/24", "fd90::1/64"],
                    "peers": [],
                    "mtu": 1380,
                    "reserved": [1, 2, 3],
                },
            }
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
    }


@pytest.mark.parametrize("encoding", ["base64", "unpadded", "url", "hex"])
def test_xray_wireguard_metadata_and_node_credentials(encoding):
    secret, public = generate_wireguard_keypair()
    raw = base64.b64decode(secret)
    encoded = {
        "base64": secret,
        "unpadded": secret.rstrip("="),
        "url": base64.urlsafe_b64encode(raw).decode().rstrip("="),
        "hex": raw.hex(),
    }[encoding]
    config = xray_config(encoded)
    original = deepcopy(config)
    parsed = XRayConfig(config)
    assert parsed.type == CoreType.xray
    assert parsed.protocols == {ProxyProtocol.wireguard}
    metadata = parsed.inbounds_by_tag["xray-wg"]
    assert metadata["public_key"] == public
    assert metadata["private_key"] == secret
    assert metadata["listen_port"] == 51821
    assert metadata["network"] == "udp"
    assert metadata["address"] == ["10.90.0.1/24", "fd90::1/64"]
    assert metadata["mtu"] == 1380
    assert metadata["reserved"] == "1,2,3"
    assert config == original == dict(parsed)
    assert "clients" not in parsed["inbounds"][0]["settings"]
    restored = XRayConfig.from_json(parsed.to_json())
    assert restored.inbounds_by_tag == parsed.inbounds_by_tag
    assert restored.protocols == parsed.protocols

    user = _serialize_user_for_node(
        42,
        {"wireguard": {"public_key": public, "peer_ips": ["10.90.0.2/32", "fd90::2/128"]}},
        parsed.inbounds,
        parsed.protocols,
    )
    assert user.email == "42"
    assert list(user.inbounds) == ["xray-wg"]
    assert user.proxies.wireguard.public_key == public
    assert list(user.proxies.wireguard.peer_ips) == ["10.90.0.2/32", "fd90::2/128"]


@pytest.mark.parametrize("address", [[], ["10.90.0.1"], ["10.90.0.1/32"], ["10.90.0.1/31"], ["fd90::1/128"]])
def test_xray_wireguard_without_allocatable_subnet_is_left_unmanaged(address):
    secret, _ = generate_wireguard_keypair()
    parsed = XRayConfig(xray_config(secret, address=address))
    assert not parsed.inbounds
    assert not parsed.protocols


def test_xray_wireguard_with_null_address_is_left_unmanaged():
    secret, _ = generate_wireguard_keypair()
    config = xray_config(secret)
    config["inbounds"][0]["settings"]["address"] = None
    parsed = XRayConfig(config)
    assert not parsed.inbounds
    assert not parsed.protocols


@pytest.mark.parametrize(
    ("address", "allocatable"),
    [
        (["10.90.0.1/32", "10.90.0.1/24"], ["10.90.0.1/24"]),
        (["10.90.0.1/31", "10.90.0.1/30"], ["10.90.0.1/30"]),
    ],
)
def test_xray_wireguard_allocates_only_from_subnets(address, allocatable):
    secret, _ = generate_wireguard_keypair()
    parsed = XRayConfig(xray_config(secret, address=address))
    assert parsed.inbounds == ["xray-wg"]
    assert parsed.inbounds_by_tag["xray-wg"]["address"] == allocatable


@pytest.mark.parametrize(
    ("address", "message"),
    [
        (["invalid"], "valid IP addresses or CIDRs"),
        (["10.90.0.1/24", 42], "valid IP addresses or CIDRs"),
        ("10.90.0.1/24", "needs address CIDRs"),
    ],
)
def test_managed_xray_wireguard_rejects_invalid_addresses(address, message):
    secret, _ = generate_wireguard_keypair()
    with pytest.raises(ValueError, match=message):
        XRayConfig(xray_config(secret, address=address))


@pytest.mark.parametrize("port", [None, True, 0, 65536, "1000-2000", [51820]])
def test_xray_wireguard_rejects_invalid_listen_port(port):
    secret, _ = generate_wireguard_keypair()
    config = xray_config(secret)
    config["inbounds"][0]["port"] = port
    with pytest.raises(ValueError, match="single port"):
        XRayConfig(config)


@pytest.mark.parametrize("mtu", [False, True, 0, 575, 9001, 1420.0, "1420", [], {}])
def test_xray_wireguard_rejects_invalid_mtu(mtu):
    secret, _ = generate_wireguard_keypair()
    config = xray_config(secret)
    config["inbounds"][0]["settings"]["mtu"] = mtu
    with pytest.raises(ValueError, match="xray-wg WireGuard mtu must be an integer between 576 and 9000"):
        XRayConfig(config)


@pytest.mark.parametrize("mtu,expected", [(None, 1420), (576, 576), (9000, 9000)])
def test_xray_wireguard_accepts_default_and_valid_mtu(mtu, expected):
    secret, _ = generate_wireguard_keypair()
    config = xray_config(secret)
    config["inbounds"][0]["settings"]["mtu"] = mtu
    assert XRayConfig(config).inbounds_by_tag["xray-wg"]["mtu"] == expected


def test_excluded_xray_wireguard_and_outbound_are_not_managed():
    config = xray_config("externally-managed")
    config["outbounds"].append({"tag": "wg-out", "protocol": "wireguard", "settings": {"secretKey": "external"}})
    parsed = XRayConfig(config, exclude_inbound_tags={"xray-wg"})
    assert not parsed.inbounds
    assert not parsed.protocols
    assert dict(parsed) == config
    core = SimpleNamespace(
        type=CoreType.xray, config=config, exclude_inbound_tags={"xray-wg"}, fallbacks_inbound_tags=[]
    )
    assert wg_namespaces([core]) == {}
    assert wg_core_tags([core]) == set()


def test_xray_wireguard_without_address_is_left_unmanaged():
    secret, public = generate_wireguard_keypair()
    config = xray_config(secret)
    static = config["inbounds"][0]
    del static["settings"]["address"]
    static["port"] = "51820-51830"
    static["settings"]["peers"] = [{"publicKey": public, "allowedIPs": ["10.9.0.2/32"]}]
    config["inbounds"].insert(
        0,
        {
            "tag": "vless-tcp",
            "protocol": "vless",
            "port": 443,
            "settings": {"clients": [], "decryption": "none"},
            "streamSettings": {"network": "tcp"},
        },
    )
    parsed = XRayConfig(config)
    assert parsed.inbounds == ["vless-tcp"]
    assert parsed.protocols == {ProxyProtocol.vless}
    core = SimpleNamespace(type=CoreType.xray, config=config, exclude_inbound_tags=[], fallbacks_inbound_tags=[])
    assert wg_namespaces([core]) == {}
    assert wg_core_tags([core]) == set()


@pytest.mark.parametrize(
    "address",
    [[], None, ["10.90.0.1"], ["10.90.0.1/32"], ["10.90.0.1/31"], ["invalid"], "10.90.0.1/24"],
)
def test_wireguard_pools_skip_xray_inbounds_the_parser_does_not_manage(address):
    secret, _ = generate_wireguard_keypair()
    config = xray_config(secret)
    config["inbounds"][0]["settings"]["address"] = address
    core = SimpleNamespace(type=CoreType.xray, config=config, exclude_inbound_tags=[], fallbacks_inbound_tags=[])
    assert wg_core_interfaces(core) == []
    assert wg_namespaces([core]) == {}
    assert wg_core_tags([core]) == set()


def test_wireguard_pools_skip_xray_inbounds_with_malformed_settings():
    config = xray_config("unused")
    config["inbounds"][0]["settings"] = ["10.90.0.1/24"]
    core = SimpleNamespace(type=CoreType.xray, config=config, exclude_inbound_tags=[], fallbacks_inbound_tags=[])
    assert wg_core_interfaces(core) == []


def test_wireguard_pools_use_the_parser_subnets():
    secret, _ = generate_wireguard_keypair()
    config = xray_config(secret, address=["10.90.0.1/32", "10.90.0.1/24", "fd90::1/64"])
    core = SimpleNamespace(type=CoreType.xray, config=config, exclude_inbound_tags=[], fallbacks_inbound_tags=[])
    interfaces = wg_core_interfaces(core)
    assert [interface["interface_name"] for interface in interfaces] == ["xray-wg"]
    assert interfaces[0]["address"] == ["10.90.0.1/24", "fd90::1/64"]
    assert interfaces[0]["address"] == XRayConfig(config).inbounds_by_tag["xray-wg"]["address"]
    assert set(wg_namespaces([core])) == {"10.90.0.0/24", "fd90::/64"}
    assert wg_core_tags([core]) == {"xray-wg"}


@pytest.mark.parametrize(
    ("address", "reserved"),
    [
        (["10.90.0.1", "10.90.0.0/24"], {0, 1, 255}),
        (["10.90.0.5/32", "10.90.0.1/24"], {0, 1, 5, 255}),
        (["10.90.0.1/24", "10.90.0.9"], {0, 1, 9, 255}),
    ],
)
def test_wireguard_pools_reserve_every_xray_server_address(address, reserved):
    # Xray binds each entry as a server address, so none may be handed to a client,
    # while only the subnet becomes an allocation pool.
    secret, _ = generate_wireguard_keypair()
    core = SimpleNamespace(
        type=CoreType.xray,
        config=xray_config(secret, address=address),
        exclude_inbound_tags=[],
        fallbacks_inbound_tags=[],
    )
    namespaces = wg_namespaces([core])
    assert set(namespaces) == {"10.90.0.0/24"}
    assert set(namespaces["10.90.0.0/24"].reserved) == reserved


@pytest.mark.parametrize("secret", ["", "invalid", "00" * 31, "gg" * 32])
def test_xray_wireguard_rejects_invalid_keys(secret):
    with pytest.raises(ValueError, match="secretKey"):
        XRayConfig(xray_config(secret))


@pytest.mark.parametrize("reserved", [[1, 2], [1, 2, 256], [True, 2, 3], "invalid"])
def test_xray_wireguard_rejects_invalid_reserved_bytes(reserved):
    secret, _ = generate_wireguard_keypair()
    config = xray_config(secret)
    config["inbounds"][0]["settings"]["reserved"] = reserved
    with pytest.raises(ValueError, match="reserved"):
        XRayConfig(config)


def test_xray_wireguard_preserves_finalmask_and_base64_reserved():
    secret, _ = generate_wireguard_keypair()
    config = xray_config(secret)
    config["inbounds"][0]["settings"]["reserved"] = "AQID"
    mask = {"udp": [{"type": "salamander", "settings": {"password": "test"}}]}
    config["inbounds"][0]["streamSettings"] = {"finalmask": mask}
    parsed = XRayConfig(config)
    metadata = parsed.inbounds_by_tag["xray-wg"]
    assert metadata["reserved"] == "1,2,3"
    assert metadata["finalmask"] == mask
    assert dict(parsed) == config


def test_kernel_and_xray_namespaces_share_identical_cidrs_and_reserve_both_servers():
    secret, _ = generate_wireguard_keypair()
    kernel = SimpleNamespace(
        type=CoreType.wg,
        config={
            "interface_name": "kernel-wg",
            "address": ["10.90.0.5/24"],
            "private_key": secret,
            "listen_port": 51820,
        },
    )
    before = WireGuardConfig(kernel.config).to_json()
    xray = SimpleNamespace(
        type=CoreType.xray, config=xray_config(secret), exclude_inbound_tags=[], fallbacks_inbound_tags=[]
    )
    namespaces = wg_namespaces([kernel, xray])
    assert namespaces["10.90.0.0/24"].tags == {"kernel-wg", "xray-wg"}
    assert namespaces["10.90.0.0/24"].reserved == {0, 1, 5, 255}
    assert namespaces["fd90::/64"].tags == {"xray-wg"}
    assert wg_core_tags([kernel, xray]) == {"kernel-wg", "xray-wg"}
    assert WireGuardConfig(kernel.config).to_json() == before

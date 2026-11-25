import io
import zipfile

import pytest

from app.core.hosts import _prepare_subscription_inbound_data
from app.core.manager import core_manager
from app.core.wireguard import WireGuardConfig
from app.models.host import BaseHost
from app.subscription.wireguard import WireGuardConfiguration
from app.utils.crypto import generate_wireguard_keypair


@pytest.mark.asyncio
@pytest.mark.parametrize("amnezia_enabled", [False, True])
async def test_wireguard_archive_uses_native_core_amnezia_profile(monkeypatch, amnezia_enabled):
    server_key, server_public = generate_wireguard_keypair()
    client_key, _ = generate_wireguard_keypair()
    header_key, _ = generate_wireguard_keypair()
    config = {
        "interface_name": "wg0",
        "private_key": server_key,
        "listen_port": 51820,
        "address": ["10.23.5.1/24"],
    }
    if amnezia_enabled:
        config["amnezia"] = {
            "header_protection_key": header_key.rstrip("="),
            "s1": 24,
            "s2": 24,
            "s3": 24,
            "s4": 24,
            "i1": "<r 20>",
            "content_padding_addition": "3-12",
            "random_trailers": True,
            "disable_cookies": False,
            "jc": 0,
        }
    core = WireGuardConfig(config)
    if amnezia_enabled:
        assert core["amnezia"]["header_protection_key"] == header_key

    async def get_inbound(tag):
        return core.inbounds_by_tag[tag]

    monkeypatch.setattr(core_manager, "get_inbound_by_tag", get_inbound)
    host = BaseHost(remark="Corporate", inbound_tag="wg0", address=["vpn.example"], priority=0)
    inbound = await _prepare_subscription_inbound_data(host)
    # Subscription generation resolves one port and address for each user.
    inbound = inbound.model_copy(update={"port": 51820})
    archive = WireGuardConfiguration()
    archive.add(host.remark, "vpn.example", inbound, {"private_key": client_key, "peer_ips": ["10.23.5.2/32"]})

    with zipfile.ZipFile(io.BytesIO(archive.render())) as profiles:
        profile = profiles.read("Corporate.conf").decode()
    interface, peer = profile.split("[Peer]")
    assert client_key in interface
    assert server_public in peer
    assert server_key not in profile
    assert (f"HeaderProtectionKey = {header_key}" in interface) is amnezia_enabled
    assert ("ContentPaddingAddition = 3-12" in interface) is amnezia_enabled
    assert ("I1 = <r 20>" in interface) is amnezia_enabled
    assert ("RandomTrailers = on" in interface) is amnezia_enabled
    assert ("DisableCookies = off" in interface) is amnezia_enabled
    assert ("Jc = 0" in interface) is amnezia_enabled


def test_amnezia_core_rejects_injected_config_lines():
    private_key, _ = generate_wireguard_keypair()
    with pytest.raises(ValueError, match=r"amnezia\.i1 must be a single-line"):
        WireGuardConfig(
            {
                "interface_name": "wg0",
                "private_key": private_key,
                "listen_port": 51820,
                "address": ["10.23.5.1/24"],
                "amnezia": {"i1": "<r 20>\n[Peer]"},
            }
        )

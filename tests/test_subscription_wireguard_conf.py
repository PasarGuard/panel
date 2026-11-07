import io
import json
import zipfile
from urllib.parse import parse_qs, urlsplit

from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.links import StandardLinks
from app.subscription.singbox import SingBoxConfiguration
from app.subscription.wireguard import WireGuardConfiguration

INTERFACE_KEYS_EVERY_OFFICIAL_CLIENT_ACCEPTS = {"privatekey", "listenport", "address", "dns", "mtu"}
PEER_KEYS_EVERY_OFFICIAL_CLIENT_ACCEPTS = {"publickey", "presharedkey", "allowedips", "endpoint", "persistentkeepalive"}


def _inbound(**overrides) -> SubscriptionInboundData:
    fields = {
        "remark": "wg-warp",
        "inbound_tag": "wg-warp-inbound",
        "protocol": "wireguard",
        "address": "edge.example.com",
        "port": 51820,
        "network": "udp",
        "tls_config": TLSConfig(tls=None),
        "transport_config": TCPTransportConfig(),
        "wireguard_public_key": "server-pub",
        "wireguard_pre_shared_key": "shared-psk",
        "wireguard_allowed_ips": ["0.0.0.0/0", "::/0"],
        "wireguard_keepalive": 25,
        "wireguard_mtu": 1280,
        "wireguard_reserved": "1,2,3",
        "wireguard_dns": ["1.1.1.1"],
        "priority": 0,
    }
    fields.update(overrides)
    return SubscriptionInboundData(**fields)


def _settings() -> dict:
    return {"private_key": "client-priv", "peer_ips": ["10.0.0.2/32"]}


def _conf_files(inbound: SubscriptionInboundData) -> dict[str, str]:
    conf = WireGuardConfiguration()
    conf.add("wg-warp", "edge.example.com", inbound, _settings())
    with zipfile.ZipFile(io.BytesIO(conf.render())) as archive:
        return {name: archive.read(name).decode() for name in archive.namelist()}


def _sections(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1].lower(), {})
            continue
        key, _, value = line.partition("=")
        current[key.strip().lower()] = value.strip()
    return sections


def test_the_conf_file_carries_only_keys_every_official_wireguard_client_accepts():
    files = _conf_files(_inbound())
    assert len(files) == 1
    sections = _sections(next(iter(files.values())))
    assert set(sections) == {"interface", "peer"}
    assert set(sections["interface"]) <= INTERFACE_KEYS_EVERY_OFFICIAL_CLIENT_ACCEPTS, sections["interface"]
    assert set(sections["peer"]) <= PEER_KEYS_EVERY_OFFICIAL_CLIENT_ACCEPTS, sections["peer"]
    assert "reserved" not in next(iter(files.values())).lower()


def test_the_conf_file_keeps_every_standard_setting_of_a_reserved_host():
    sections = _sections(next(iter(_conf_files(_inbound()).values())))
    assert sections["interface"] == {
        "privatekey": "client-priv",
        "address": "10.0.0.2/32",
        "mtu": "1280",
        "dns": "1.1.1.1",
    }
    assert sections["peer"] == {
        "publickey": "server-pub",
        "allowedips": "0.0.0.0/0, ::/0",
        "endpoint": "edge.example.com:51820",
        "presharedkey": "shared-psk",
        "persistentkeepalive": "25",
    }


def test_formats_that_understand_reserved_still_carry_it():
    links = StandardLinks()
    links.add("wg-warp", "edge.example.com", _inbound(), _settings())
    uri = links.render().strip().splitlines()[0]
    assert uri.startswith("wireguard://")
    assert parse_qs(urlsplit(uri).query)["reserved"] == ["1,2,3"]

    singbox = SingBoxConfiguration()
    singbox.add("wg-warp", "edge.example.com", _inbound(), _settings())
    endpoint = json.loads(singbox.render())["endpoints"][0]
    assert endpoint["peers"][0]["reserved"] == [1, 2, 3]

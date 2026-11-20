import io
import re
import unicodedata
import zipfile

from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.wireguard import WireGuardConfiguration

TUNNEL_NAME = re.compile(r"[a-zA-Z0-9_=+.-]{1,15}")


def _inbound() -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="wg",
        inbound_tag="wg-in",
        protocol="wireguard",
        address="wg.example.com",
        port=51820,
        network="udp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(path="", host=[]),
        mux_settings=None,
        wireguard_public_key="cHViLWtleS1wdWIta2V5LXB1Yi1rZXktcHViLWtleTA=",
        wireguard_allowed_ips=["0.0.0.0/0"],
    )


def _archive_stems(*remarks: str) -> list[str]:
    conf = WireGuardConfiguration()
    inbound = _inbound()
    for remark in remarks:
        conf.add(remark, inbound.address, inbound, {"private_key": "cHJpdi1rZXk=", "peer_ips": ["10.0.0.2/32"]})
    assert len(conf.configs) == len(remarks)
    with zipfile.ZipFile(io.BytesIO(conf.render())) as archive:
        names = archive.namelist()
    assert len(names) == len(remarks)
    assert all(name.endswith(".conf") for name in names)
    return [name.removesuffix(".conf") for name in names]


def test_wireguard_add_path_keeps_android_sized_names_within_fifteen_characters():
    stems = _archive_stems(*["Berlin-Server1"] * 12)
    assert len(set(stems)) == 12, stems
    assert len({unicodedata.normalize("NFC", stem).casefold() for stem in stems}) == 12, stems
    assert all(TUNNEL_NAME.fullmatch(stem) for stem in stems), stems


def test_wireguard_add_path_gives_short_duplicate_remarks_a_tunnel_name_the_clients_accept():
    stems = _archive_stems("Berlin", "Berlin", "Berlin")
    assert all(TUNNEL_NAME.fullmatch(stem) for stem in stems), stems
    assert stems == ["Berlin", "Berlin-2", "Berlin-3"], stems


def test_wireguard_add_path_keeps_mixed_duplicate_remarks_unique_and_android_sized():
    stems = _archive_stems("Berlin", "Berlin", "Berlin (2)", "berlin", "Berlin-2", "Berlin")
    assert len({unicodedata.normalize("NFC", stem).casefold() for stem in stems}) == 6, stems
    assert all(len(stem) <= 15 for stem in stems), stems

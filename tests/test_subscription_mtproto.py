from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.hosts import _prepare_subscription_inbound_data
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.links import StandardLinks, _mtproto_client_secret

SECRET = "00112233445566778899aabbccddeeff"


def _inbound(*, modes: dict[str, bool] | None = None, tls_domain: str = "") -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="mtproto",
        inbound_tag="mtproto",
        protocol="mtproto",
        address="edge.example.com",
        port=443,
        network="tcp",
        tls_config=TLSConfig(),
        transport_config=TCPTransportConfig(),
        mtproto_modes=modes or {},
        mtproto_tls_domain=tls_domain,
        priority=0,
    )


def _telegram_links(address: str, inbound: SubscriptionInboundData, settings: dict) -> list[str]:
    links = StandardLinks(include_telegram_proxy_links=True)
    links.add("EU", address, inbound, settings)
    return links.links


def test_mtproto_client_secret_classic():
    assert _mtproto_client_secret(SECRET, _inbound(modes={"classic": True})) == SECRET


def test_mtproto_client_secret_secure():
    assert _mtproto_client_secret(SECRET, _inbound(modes={"secure": True})) == "dd" + SECRET


def test_mtproto_client_secret_tls_prefers_fake_tls():
    inbound = _inbound(modes={"classic": True, "secure": True, "tls": True}, tls_domain="cloudflare.com")
    assert _mtproto_client_secret(SECRET, inbound) == "ee" + SECRET + b"cloudflare.com".hex()


def test_mtproto_client_secret_tls_without_domain_falls_back():
    inbound = _inbound(modes={"classic": True, "secure": True, "tls": True})
    assert _mtproto_client_secret(SECRET, inbound) == "dd" + SECRET


def test_mtproto_link_uses_telemt_form():
    inbound = _inbound(modes={"classic": False, "secure": True, "tls": False})
    assert _telegram_links("edge.example.com", inbound, {"secret": SECRET}) == [
        f"tg://proxy?server=edge.example.com&port=443&secret=dd{SECRET}"
    ]


def test_mtproto_link_tls_prefers_fake_tls():
    inbound = _inbound(modes={"classic": False, "secure": True, "tls": True}, tls_domain="www.example.org")
    assert _telegram_links("edge.example.com", inbound, {"secret": SECRET}) == [
        f"tg://proxy?server=edge.example.com&port=443&secret=ee{SECRET}{b'www.example.org'.hex()}"
    ]


def test_links_format_skips_mtproto():
    links = StandardLinks()
    inbound = _inbound(modes={"classic": False, "secure": True, "tls": False})
    links.add("EU", "edge.example.com", inbound, {"secret": SECRET})
    assert links.links == []


@pytest.mark.parametrize("address", ["[2001:db8::1]", "2001:db8::1"])
def test_mtproto_link_ipv6_host(address):
    inbound = _inbound(modes={"classic": False, "secure": True, "tls": False})
    assert _telegram_links(address, inbound, {"secret": SECRET}) == [
        f"tg://proxy?server=2001:db8::1&port=443&secret=dd{SECRET}"
    ]


@pytest.mark.parametrize("settings", [{"secret": None}, {}])
def test_mtproto_link_without_secret_is_skipped(settings):
    inbound = _inbound(modes={"classic": False, "secure": True, "tls": False})
    assert _telegram_links("edge.example.com", inbound, settings) == []


def test_mtproto_link_without_usable_mode_is_skipped():
    inbound = _inbound(modes={"classic": False, "secure": False, "tls": True})
    assert _telegram_links("edge.example.com", inbound, {"secret": SECRET}) == []


def _mtproto_host(**overrides) -> SimpleNamespace:
    fields = {
        "remark": "mtproto",
        "inbound_tag": "mtproto",
        "address": [],
        "port": None,
        "transport_settings": None,
        "path": None,
        "final_mask_settings": None,
        "priority": 1,
        "status": None,
        "subscription_templates": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


async def test_prepare_inbound_data_for_mtproto_host(monkeypatch: pytest.MonkeyPatch):
    inbound_config = {
        "tag": "mtproto",
        "protocol": "mtproto",
        "network": "tcp",
        "tls": "none",
        "listen_port": 443,
        "port": 443,
        "modes": {"classic": False, "secure": False, "tls": True},
        "tls_domain": "www.example.org",
    }
    monkeypatch.setattr("app.core.hosts.core_manager.get_inbound_by_tag", AsyncMock(return_value=inbound_config))

    prepared = await _prepare_subscription_inbound_data(_mtproto_host())
    assert prepared.port == [443]
    assert prepared.address == ["{SERVER_IP}"]
    assert prepared.mtproto_tls_domain == "www.example.org"
    assert prepared.mtproto_modes == {"classic": False, "secure": False, "tls": True}
    assert prepared.fragment_settings is None
    assert prepared.noise_settings is None
    assert prepared.finalmask is None
    assert prepared.finalmask_link is None

    overridden = await _prepare_subscription_inbound_data(_mtproto_host(port=8443, address=["a.example.net"]))
    assert overridden.port == [8443]
    assert overridden.address == ["a.example.net"]

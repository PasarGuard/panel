import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.hosts import _prepare_subscription_inbound_data
from app.db.models import DataLimitResetStrategy, UserStatus
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.links import StandardLinks, _mtproto_client_secret, _telegram_web_link
from app.templates import render_template

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
        "id": 7,
        "remark": "mtproto",
        "inbound_tag": "mtproto",
        "address": [],
        "port": None,
        "sni": None,
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


WEB_SECRET = "000102030405060708090a0b0c0d0e0f"


def _typed_inbound(link_type: str, **fields) -> SubscriptionInboundData:
    inbound = _inbound(
        modes=fields.pop("modes", {"classic": True, "secure": True, "tls": True}),
        tls_domain=fields.pop("tls_domain", "www.example.org"),
    )
    return inbound.model_copy(update={"mtproto_link_type": link_type, **fields})


@pytest.mark.parametrize(
    ("modes", "tls_domain", "expected"),
    [
        ({"classic": True}, "", SECRET),
        ({"secure": True}, "", "dd" + SECRET),
        ({"classic": True, "secure": True, "tls": True}, "cloudflare.com", "ee" + SECRET + b"cloudflare.com".hex()),
        ({"classic": True, "secure": True, "tls": True}, "", "dd" + SECRET),
        ({"classic": False, "secure": False, "tls": True}, "", None),
    ],
)
def test_auto_host_link_unchanged(modes, tls_domain, expected):
    inbound = _inbound(modes=modes, tls_domain=tls_domain)
    assert inbound.mtproto_link_type == "auto"
    links = _telegram_links("edge.example.com", inbound, {"secret": SECRET})
    assert links == ([f"tg://proxy?server=edge.example.com&port=443&secret={expected}"] if expected else [])


def test_each_native_type():
    domains = ["a.example.org", "b.example.org"]
    tls = _typed_inbound("tls", mtproto_link_domains=domains)
    seen = set()
    for _ in range(50):
        (link,) = _telegram_links("edge.example.com", tls, {"secret": SECRET})
        seen.add(link)
    assert seen == {f"tg://proxy?server=edge.example.com&port=443&secret=ee{SECRET}{d.encode().hex()}" for d in domains}

    secure = _typed_inbound("secure")
    assert _telegram_links("edge.example.com", secure, {"secret": SECRET}) == [
        f"tg://proxy?server=edge.example.com&port=443&secret=dd{SECRET}"
    ]
    classic = _typed_inbound("classic")
    assert _telegram_links("edge.example.com", classic, {"secret": SECRET}) == [
        f"tg://proxy?server=edge.example.com&port=443&secret={SECRET}"
    ]


def test_tls_type_without_domain_gives_no_link():
    assert _telegram_links("edge.example.com", _typed_inbound("tls"), {"secret": SECRET}) == []


@pytest.mark.parametrize("secret", [WEB_SECRET, WEB_SECRET.upper()])
def test_web_link_vectors(secret):
    host = "proxy.example.com"
    assert _telegram_web_link(host, "", "plain", secret) == f"tg://webproxy?server={host}&secret={WEB_SECRET}"
    assert _telegram_web_link(host, "", "dd", secret) == f"tg://webproxy?server={host}&secret=dd{WEB_SECRET}"
    assert (
        _telegram_web_link(host, "dobry-cola/super_app", "plain", secret)
        == "tg://webproxy?server=proxy.example.com%2Fdobry-cola%2Fsuper_app&secret=cAABAgMEBQYHCAkKCwwNDg8"
    )
    assert (
        _telegram_web_link(host, "dobry-cola/super_app", "dd", secret)
        == "tg://webproxy?server=proxy.example.com%2Fdobry-cola%2Fsuper_app&secret=cN0AAQIDBAUGBwgJCgsMDQ4P"
    )


def test_web_link_uppercase_secret():
    test_web_link_vectors(WEB_SECRET.upper())


def test_web_link_uses_vhost_host():
    vhosts = [
        {"host": "other.example.com", "base_path": "", "secret_mode": "plain"},
        {"host": "proxy.example.com", "base_path": "app", "secret_mode": "dd"},
    ]
    web = _typed_inbound("web", mtproto_web_vhosts=vhosts, mtproto_native=False)
    assert _telegram_links("Proxy.Example.com", web, {"secret": WEB_SECRET}) == [
        "tg://webproxy?server=proxy.example.com%2Fapp&secret=cN0AAQIDBAUGBwgJCgsMDQ4P"
    ]
    assert _telegram_links("unknown.example.com", web, {"secret": WEB_SECRET}) == []
    assert _telegram_links("Proxy.Example.com", web, {"secret": None}) == []


def test_type_no_longer_served_gives_no_link():
    secure_off = _typed_inbound("secure", modes={"classic": True, "secure": False, "tls": True})
    assert _telegram_links("edge.example.com", secure_off, {"secret": SECRET}) == []

    web_gone = _typed_inbound("web", mtproto_web_vhosts=[])
    assert _telegram_links("proxy.example.com", web_gone, {"secret": SECRET}) == []

    for link_type in ("auto", "tls", "secure", "classic"):
        web_only = _typed_inbound(link_type, mtproto_link_domains=["www.example.org"], mtproto_native=False)
        assert _telegram_links("edge.example.com", web_only, {"secret": SECRET}) == [], link_type


def test_webproxy_open_button():
    link = 'tg://webproxy?server=proxy.example.com%2Fapp&secret=cN0A"><b>'
    html = render_template(
        "subscription/index.html",
        {
            "user": SimpleNamespace(
                username="page_user",
                status=UserStatus.active,
                data_limit=0,
                used_traffic=0,
                data_limit_reset_strategy=DataLimitResetStrategy.no_reset,
                on_hold_expire_duration=None,
                expire=None,
                on_hold_timeout=None,
            ),
            "links": [link],
            "announce": "",
            "announce_url": "",
            "apps": [],
        },
    )
    assert "<b>" not in html
    escaped = "tg://webproxy?server=proxy.example.com%2Fapp&amp;secret=cN0A&#34;&gt;&lt;b&gt;"
    assert f'<a class="open-button" href="{escaped}">Open in Telegram</a>' in html


async def test_prepare_inbound_data_link_settings(monkeypatch: pytest.MonkeyPatch):
    vhosts = [{"host": "proxy.example.com", "base_path": "", "secret_mode": "dd"}]
    inbound_config = {
        "tag": "mtproto",
        "protocol": "mtproto",
        "listen_port": 443,
        "modes": {"classic": False, "secure": True, "tls": True},
        "tls_domain": "www.example.org",
        "tls_domains": ["www.example.org", "b.example.org"],
        "native": False,
        "web_vhosts": vhosts,
    }
    monkeypatch.setattr("app.core.hosts.core_manager.get_inbound_by_tag", AsyncMock(return_value=inbound_config))

    default = await _prepare_subscription_inbound_data(_mtproto_host())
    assert default.mtproto_link_type == "auto"
    assert default.mtproto_link_domains == ["www.example.org"]
    assert default.mtproto_native is False
    assert default.mtproto_web_vhosts == vhosts

    tls_host = _mtproto_host(
        sni=["b.example.org", "gone.example.org"],
        transport_settings={"mtproto_settings": {"link_type": "tls"}},
    )
    prepared = await _prepare_subscription_inbound_data(tls_host)
    assert prepared.mtproto_link_type == "tls"
    assert prepared.mtproto_link_domains == ["b.example.org"]

    inbound_config["tls_domains"] = []
    tls_off = await _prepare_subscription_inbound_data(
        _mtproto_host(transport_settings={"mtproto_settings": {"link_type": "tls"}})
    )
    assert tls_off.mtproto_link_domains == []


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"transport_settings": {"mtproto_settings": {"link_type": "classic"}}}, 'mode "classic" is off'),
        ({"transport_settings": {"mtproto_settings": {"link_type": "secure"}}}, "no native listener"),
        ({"transport_settings": {"mtproto_settings": {"link_type": "tls"}}, "sni": ["gone.example.org"]}, "fake TLS"),
        (
            {"transport_settings": {"mtproto_settings": {"link_type": "web"}}, "address": ["old.example.com"]},
            "WEB vhost",
        ),
    ],
)
async def test_unserved_link_type_is_logged(monkeypatch: pytest.MonkeyPatch, caplog, overrides, reason):
    inbound_config = {
        "tag": "mtproto",
        "protocol": "mtproto",
        "listen_port": 443,
        "modes": {"classic": False, "secure": True, "tls": True},
        "tls_domain": "www.example.org",
        "tls_domains": ["www.example.org"],
        "native": "secure" not in str(overrides),
        "web_vhosts": [{"host": "proxy.example.com", "base_path": "", "secret_mode": "dd"}],
    }
    monkeypatch.setattr("app.core.hosts.core_manager.get_inbound_by_tag", AsyncMock(return_value=inbound_config))
    caplog.set_level(logging.WARNING)

    await _prepare_subscription_inbound_data(_mtproto_host(**overrides))
    assert 'MTProto host "7" gives no link' in caplog.text
    assert reason in caplog.text

    caplog.clear()
    inbound_config["native"] = True
    await _prepare_subscription_inbound_data(_mtproto_host())
    await _prepare_subscription_inbound_data(
        _mtproto_host(transport_settings={"mtproto_settings": {"link_type": "web"}}, address=["Proxy.Example.com"])
    )
    assert "gives no link" not in caplog.text

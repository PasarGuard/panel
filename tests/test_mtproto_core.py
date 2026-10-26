import re

import pytest
from PasarGuardNodeBridge.common import service_pb2 as service
from pydantic import ValidationError

from app.core.mtproto import TELEMT_DEFAULT_MODES, TELEMT_DEFAULT_PORT, TLS_DOMAIN_PLACEHOLDER, MtprotoConfig
from app.db.models import CoreType
from app.models.protocol import ProxyProtocol
from app.models.proxy import MtprotoSettings, ProxyTable, generate_mtproto_secret
from app.node.user import _serialize_user_for_node
from app.operation.node import backend_type_for_core


def _valid_config(**overrides) -> dict:
    config = {
        "inbound_tag": "mtproto",
        "general": {"use_middle_proxy": True, "modes": {"classic": True, "secure": True, "tls": True}},
        "server": {"port": 443, "listeners": [{"ip": "0.0.0.0"}]},
        "censorship": {"tls_domain": "cloudflare.com"},
    }
    config.update(overrides)
    return config


def test_mtproto_config_resolves_inbound():
    core = MtprotoConfig(_valid_config())
    assert core.type == CoreType.mtproto
    assert core.protocols == frozenset((ProxyProtocol.mtproto,))
    assert core.inbounds == ["mtproto"]
    inbound = core.inbounds_by_tag["mtproto"]
    assert inbound["protocol"] == "mtproto"
    assert inbound["network"] == "tcp"
    assert inbound["listen_port"] == 443
    assert inbound["modes"]["tls"] is True
    assert inbound["tls_domain"] == "cloudflare.com"


def test_mtproto_config_defaults_inbound_tag():
    config = _valid_config()
    del config["inbound_tag"]
    core = MtprotoConfig(config)
    assert core["inbound_tag"] == "mtproto"
    assert "mtproto" in core.inbounds_by_tag


def test_mtproto_config_custom_inbound_tag():
    core = MtprotoConfig(_valid_config(inbound_tag="mtp-eu"))
    assert core.inbounds == ["mtp-eu"]


def test_mtproto_config_rejects_xray_only_tags():
    with pytest.raises(ValueError, match="exclude_inbound_tags"):
        MtprotoConfig(_valid_config(), exclude_inbound_tags={"nope"})
    with pytest.raises(ValueError, match="fallbacks_inbound_tags"):
        MtprotoConfig(_valid_config(), fallbacks_inbound_tags={"nope"})


def test_mtproto_config_roundtrip_json():
    core = MtprotoConfig(_valid_config(inbound_tag="mtp-json"))
    restored = MtprotoConfig.from_json(core.to_json())
    assert restored.inbounds == ["mtp-json"]
    assert restored.inbounds_by_tag["mtp-json"]["listen_port"] == 443


_DOMAIN = "www.example.org"
_NODE_REJECTED_PATHS = (
    "include",
    "web.debug",
    "web.limits.max_profiles",
    "server.api",
    "server.admin_api",
    "server.metrics_port",
    "server.metrics_listen",
    "server.metrics_whitelist",
    "access.user_rate_limits",
    "access.user_source_deny",
)
_RESTRICTED_ACCESS_KEYS = (
    "users",
    "user_ad_tags",
    "user_max_tcp_conns",
    "user_expirations",
    "user_data_quota",
    "user_max_unique_ips",
    "user_enabled",
)
_OBJECT_PATHS = (
    "general",
    "general.telemetry",
    "general.modes",
    "server",
    "access",
    "logging",
    "censorship",
    "web",
    "web.limits",
)


def _tls_config(**overrides) -> dict:
    config = {"server": {"port": 443}, "censorship": {"tls_domain": _DOMAIN}}
    config.update(overrides)
    return config


def _with_path(config: dict, path: str, value) -> dict:
    *parents, last = path.split(".")
    target = config
    for key in parents:
        target = target.setdefault(key, {})
    target[last] = value
    return config


def _modes(**modes) -> dict:
    return {"general": {"modes": modes}}


def test_missing_modes_default_to_tls_only():
    core = MtprotoConfig({"server": {"port": 443}, "censorship": {"tls_domain": _DOMAIN}})
    inbound = core.inbounds_by_tag["mtproto"]
    assert inbound["modes"] == {"classic": False, "secure": False, "tls": True}
    assert inbound["tls_domain"] == _DOMAIN
    assert inbound["listen_port"] == 443


def test_missing_server_defaults_to_port_443():
    core = MtprotoConfig({"censorship": {"tls_domain": _DOMAIN}})
    inbound = core.inbounds_by_tag["mtproto"]
    assert inbound["listen_port"] == 443
    assert inbound["port"] == 443


def test_partial_modes_keep_telemt_defaults():
    core = MtprotoConfig(_tls_config(**_modes(secure=True)))
    assert core.inbounds_by_tag["mtproto"]["modes"] == {"classic": False, "secure": True, "tls": True}


def test_tls_without_domain_rejected():
    with pytest.raises(ValueError, match=r"censorship\.tls_domain"):
        MtprotoConfig({"server": {"port": 443}})


def test_no_mode_enabled_rejected():
    with pytest.raises(ValueError, match="at least one"):
        MtprotoConfig(_tls_config(**_modes(classic=False, secure=False, tls=False)))


def test_tls_off_needs_no_domain():
    core = MtprotoConfig({"server": {"port": 443}, **_modes(tls=False, secure=True)})
    inbound = core.inbounds_by_tag["mtproto"]
    assert inbound["modes"] == {"classic": False, "secure": True, "tls": False}
    assert inbound["tls_domain"] == ""


@pytest.mark.parametrize(
    ("domain", "stored"),
    [
        ("", None),
        ("  ", None),
        ("https://x.org", None),
        ("x.org:443", None),
        ("a b.org", None),
        ("your-domain.example", None),
        (5, None),
        # telemt hex-encodes its IDNA-normalized host, so anything but an ASCII host name gives a dead "ee" link.
        ("www.exämple.org", None),
        ("a@b.org", None),
        ("a.org?", None),
        ("a.org#x", None),
        ("a%20b.org", None),
        ("your-domain.example.", None),
        ("a.org..", None),
        ("-a.org", None),
        ("a_b.org", None),
        ("a" * 64 + ".org", None),
        (("a" * 63 + ".") * 3 + "a" * 62, None),
        (" www.example.org ", "www.example.org"),
        ("www.example.org.", "www.example.org."),
        ("xn--exmple-cua.org", "xn--exmple-cua.org"),
        ("localhost", "localhost"),
        (("a" * 63 + ".") * 3 + "a" * 61, ("a" * 63 + ".") * 3 + "a" * 61),
    ],
)
def test_tls_domain_rules(domain, stored):
    config = _tls_config(censorship={"tls_domain": domain})
    if stored is None:
        with pytest.raises((ValueError, TypeError), match=r"censorship\.tls_domain"):
            MtprotoConfig(config)
        return
    core = MtprotoConfig(config)
    assert core["censorship"]["tls_domain"] == stored
    assert core.inbounds_by_tag["mtproto"]["tls_domain"] == stored


def test_tls_domain_placeholder_asks_to_replace_it():
    assert TLS_DOMAIN_PLACEHOLDER == "your-domain.example"
    with pytest.raises(ValueError, match="replace"):
        MtprotoConfig(_tls_config(censorship={"tls_domain": TLS_DOMAIN_PLACEHOLDER}))


def test_tls_off_still_checks_a_set_domain():
    with pytest.raises(TypeError, match=r"censorship\.tls_domain"):
        MtprotoConfig({**_modes(tls=False, secure=True), "censorship": {"tls_domain": 5}})
    # telemt 3.5.14 normalizes censorship.tls_domain even with tls off and exits on these.
    for domain in ("", "  ", "a b.org", "x.org/path"):
        with pytest.raises(ValueError, match=r"censorship\.tls_domain"):
            MtprotoConfig({**_modes(tls=False, secure=True), "censorship": {"tls_domain": domain}})
    core = MtprotoConfig({**_modes(tls=False, secure=True), "censorship": {"tls_domain": " x.org:443 "}})
    assert core["censorship"]["tls_domain"] == "x.org:443"
    assert core.inbounds_by_tag["mtproto"]["tls_domain"] == ""
    MtprotoConfig({**_modes(tls=False, secure=True), "censorship": {"tls_domain": None}})


@pytest.mark.parametrize("modes", [{"tls": "true"}, {"tls": 1}, {"fast": True}])
def test_mode_values_and_names(modes):
    with pytest.raises((ValueError, TypeError), match=r"general\.modes"):
        MtprotoConfig(_tls_config(**_modes(**modes)))


def test_mode_null_means_not_set():
    core = MtprotoConfig(_tls_config(**_modes(tls=None, secure=True)))
    assert core.inbounds_by_tag["mtproto"]["modes"] == {"classic": False, "secure": True, "tls": True}


@pytest.mark.parametrize("port", ["443", True, 443.0, 0, 65536])
def test_port_rules(port):
    with pytest.raises((ValueError, TypeError), match=r"server\.port"):
        MtprotoConfig(_tls_config(server={"port": port}))


def test_port_null_means_default():
    core = MtprotoConfig(_tls_config(server={"port": None}))
    assert core.inbounds_by_tag["mtproto"]["listen_port"] == TELEMT_DEFAULT_PORT == 443


def test_listener_rules():
    with pytest.raises(ValueError, match=r"server\.listeners\[0\]\.port"):
        MtprotoConfig(_tls_config(server={"port": 443, "listeners": [{"ip": "0.0.0.0", "port": 8443}]}))
    with pytest.raises(ValueError, match=r"server\.listeners\[1\]\.port"):
        MtprotoConfig(_tls_config(server={"port": 443, "listeners": [{"ip": "0.0.0.0"}, {"ip": "::", "port": 8443}]}))
    with pytest.raises((ValueError, TypeError), match=r"server\.listeners\[0\]\.port"):
        MtprotoConfig(_tls_config(server={"port": 443, "listeners": [{"port": "443"}]}))
    core = MtprotoConfig(_tls_config(server={"port": 443, "listeners": [{"ip": "0.0.0.0", "port": 443}]}))
    assert core.inbounds_by_tag["mtproto"]["listen_port"] == 443
    defaulted = MtprotoConfig(_tls_config(server={"listeners": [{"ip": "0.0.0.0", "port": 443}]}))
    assert defaulted.inbounds_by_tag["mtproto"]["listen_port"] == 443

    with pytest.raises(ValueError, match=r"server\.listeners\[0\]\.transport"):
        MtprotoConfig(_tls_config(server={"port": 443, "listeners": [{"ip": "0.0.0.0", "transport": "socks"}]}))
    MtprotoConfig(_tls_config(server={"port": 443, "listeners": [{"ip": "0.0.0.0", "transport": "mtproxy"}]}))
    MtprotoConfig(_tls_config(server={"port": 443, "listeners": [{"ip": "0.0.0.0", "transport": None, "port": None}]}))

    with pytest.raises(TypeError, match=r"server\.listeners"):
        MtprotoConfig(_tls_config(server={"port": 443, "listeners": "x"}))
    with pytest.raises(TypeError, match=r"server\.listeners\[0\]"):
        MtprotoConfig(_tls_config(server={"port": 443, "listeners": [1]}))


@pytest.mark.parametrize("path", _NODE_REJECTED_PATHS)
def test_node_rejected_keys(path):
    with pytest.raises(ValueError, match=rf"{re.escape(path)} must not be set: "):
        MtprotoConfig(_with_path(_tls_config(), path, {}))
    MtprotoConfig(_with_path(_tls_config(), path, None))


@pytest.mark.parametrize(
    ("config", "path"),
    [
        (_tls_config(general={"include": "x"}), "general.include"),
        (_tls_config(server={"port": 443, "listeners": [{"ip": "::", "include": "x"}]}), "server.listeners[0].include"),
    ],
)
def test_nested_include_keys_rejected(config, path):
    with pytest.raises(ValueError, match=rf"{re.escape(path)} must not be set: telemt would read"):
        MtprotoConfig(config)


def test_keys_that_start_with_include_allowed():
    MtprotoConfig(_tls_config(general={"included": "x", "include": None}))


@pytest.mark.parametrize("key", _RESTRICTED_ACCESS_KEYS)
def test_restricted_access_keys(key):
    with pytest.raises(ValueError, match=rf"access\.{key} must not be set"):
        MtprotoConfig(_tls_config(access={key: {"alice": "00112233445566778899aabbccddeeff"}}))
    MtprotoConfig(_tls_config(access={key: None}))


@pytest.mark.parametrize("path", _OBJECT_PATHS)
def test_object_paths_must_be_objects(path):
    with pytest.raises(TypeError, match=rf"^{re.escape(path)} must be an object"):
        MtprotoConfig(_with_path(_tls_config(), path, "x"))


@pytest.mark.parametrize("tag", ["a,b", "a<=>b", "   ", "", 123, "x" * 257])
def test_inbound_tag_rules(tag):
    with pytest.raises((ValueError, TypeError), match="inbound_tag"):
        MtprotoConfig(_tls_config(inbound_tag=tag))


def test_inbound_tag_is_stripped_and_null_means_default():
    core = MtprotoConfig(_tls_config(inbound_tag="  mtp-eu "))
    assert core["inbound_tag"] == "mtp-eu"
    assert core.inbounds == ["mtp-eu"]
    assert MtprotoConfig(_tls_config(inbound_tag="x" * 256)).inbounds == ["x" * 256]
    defaulted = MtprotoConfig(_tls_config(inbound_tag=None))
    assert defaulted["inbound_tag"] == "mtproto"
    assert defaulted.inbounds == ["mtproto"]


def test_unknown_keys_pass_through():
    config = _tls_config(
        dc_overrides={"2": ["149.154.167.51:443"]},
        general={"ad_tag": "00112233445566778899aabbccddeeff", "modes": {"tls": True}},
        access={"user_max_unique_ips_global_each": 3},
    )
    stored = MtprotoConfig(config).to_json()["config"]
    assert stored["dc_overrides"] == {"2": ["149.154.167.51:443"]}
    assert stored["general"]["ad_tag"] == "00112233445566778899aabbccddeeff"
    assert stored["access"]["user_max_unique_ips_global_each"] == 3


def test_telemt_default_modes_constant():
    assert TELEMT_DEFAULT_MODES == {"classic": False, "secure": False, "tls": True}


@pytest.mark.parametrize(
    ("domains", "message"),
    [
        ("www.example.org", r"censorship\.tls_domains must be a list"),
        ([5], r"censorship\.tls_domains\[0\] must be a string"),
        (["a b.org"], r"censorship\.tls_domains\[0\]"),
        (["x.org:443"], r"censorship\.tls_domains\[0\]"),
        (["www.exämple.org"], r"censorship\.tls_domains\[0\]"),
        (["ok.org", "a_b.org"], r"censorship\.tls_domains\[1\]"),
        ([TLS_DOMAIN_PLACEHOLDER], r"censorship\.tls_domains\[0\] .*replace"),
    ],
)
def test_tls_domains_validated(domains, message):
    with pytest.raises((ValueError, TypeError), match=message):
        MtprotoConfig(_tls_config(censorship={"tls_domain": _DOMAIN, "tls_domains": domains}))


def test_tls_domains_metadata_primary_first():
    core = MtprotoConfig(
        _tls_config(
            censorship={
                "tls_domain": _DOMAIN,
                "tls_domains": [" Cdn.Example.net ", _DOMAIN, "", "cdn.example.net", "xn--exmple-cua.org."],
            }
        )
    )
    inbound = core.inbounds_by_tag["mtproto"]
    assert inbound["tls_domain"] == _DOMAIN
    assert inbound["tls_domains"] == [_DOMAIN, "Cdn.Example.net", "xn--exmple-cua.org."]
    # The list goes to the node as stored (telemt merges and deduplicates it itself), only trimmed.
    assert core["censorship"]["tls_domains"] == [
        "Cdn.Example.net",
        _DOMAIN,
        "",
        "cdn.example.net",
        "xn--exmple-cua.org.",
    ]


def test_tls_domains_metadata_without_extra_domains_or_tls():
    assert MtprotoConfig(_tls_config()).inbounds_by_tag["mtproto"]["tls_domains"] == [_DOMAIN]
    assert MtprotoConfig(_tls_config(censorship={"tls_domain": _DOMAIN, "tls_domains": None})).inbounds_by_tag[
        "mtproto"
    ]["tls_domains"] == [_DOMAIN]
    tls_off = MtprotoConfig(
        {**_modes(tls=False, secure=True), "censorship": {"tls_domain": _DOMAIN, "tls_domains": ["cdn.example.net"]}}
    )
    assert tls_off.inbounds_by_tag["mtproto"]["tls_domains"] == []


_WEB_HOST = "proxy.example.com"


def _web_listener(**overrides) -> dict:
    listener = {"ip": "127.0.0.1", "port": 18080, "transport": "web", "web_trusted_proxy_cidrs": ["127.0.0.1/32"]}
    listener.update(overrides)
    return listener


def _web_vhost(**overrides) -> dict:
    vhost = {
        "host": _WEB_HOST,
        "public_addr": "203.0.113.10:443",
        "decoy": {"mode": "http_upstream", "upstream": "http://127.0.0.1:18081"},
        "user_profile": {"secret_mode": "plain", "max_sessions": 8},
    }
    vhost.update(overrides)
    return vhost


def _web_config(listeners=None, vhosts=None, **web) -> dict:
    if listeners is None:
        listeners = [{"ip": "0.0.0.0"}, _web_listener()]
    if vhosts is None:
        vhosts = [_web_vhost()]
    return _tls_config(
        server={"port": 443, "listeners": listeners},
        web={"enabled": True, "vhosts": vhosts, **web},
    )


def test_web_config_accepted():
    core = MtprotoConfig(_web_config())
    inbound = core.inbounds_by_tag["mtproto"]
    assert inbound["web_vhosts"] == [{"host": _WEB_HOST, "base_path": "", "secret_mode": "plain"}]
    assert inbound["native"] is True
    assert inbound["listen_port"] == 443
    # The node strips user_profile; the panel stores the config as written.
    assert core["web"]["vhosts"][0]["user_profile"] == {"secret_mode": "plain", "max_sessions": 8}

    defaulted = MtprotoConfig(_web_config(vhosts=[_web_vhost(user_profile=None, base_path="dobry-cola/super_app")]))
    assert defaulted.inbounds_by_tag["mtproto"]["web_vhosts"] == [
        {"host": _WEB_HOST, "base_path": "dobry-cola/super_app", "secret_mode": "dd"}
    ]
    # telemt lowercases vhost hosts at load, so links must use the lowercase form
    mixed = MtprotoConfig(_web_config(vhosts=[_web_vhost(host="Proxy.Example.COM")]))
    assert mixed.inbounds_by_tag["mtproto"]["web_vhosts"][0]["host"] == _WEB_HOST
    no_mode = MtprotoConfig(_web_config(vhosts=[_web_vhost(user_profile={"max_streams": 4})]))
    assert no_mode.inbounds_by_tag["mtproto"]["web_vhosts"][0]["secret_mode"] == "dd"

    for ip in ("10.0.0.5", "172.16.0.1", "192.168.1.2", "::1", "fd00::1", "::ffff:10.0.0.5"):
        MtprotoConfig(_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip=ip)]))
    for upstream in ("http://10.1.2.3:8080", "http://[::1]:8080", "https://192.168.0.10/site"):
        MtprotoConfig(_web_config(vhosts=[_web_vhost(decoy={"mode": "http_upstream", "upstream": upstream})]))


def test_empty_or_disabled_web_section_accepted():
    for web in ({}, {"enabled": False}, {"enabled": False, "vhosts": [_web_vhost()]}):
        core = MtprotoConfig(_tls_config(web=web))
        assert core.inbounds_by_tag["mtproto"]["web_vhosts"] == []
    assert MtprotoConfig(_tls_config()).inbounds_by_tag["mtproto"]["web_vhosts"] == []


@pytest.mark.parametrize(
    ("config", "error", "message"),
    [
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip="0.0.0.0")]), ValueError, "private"),
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip="::")]), ValueError, "private"),
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip="198.51.100.1")]), ValueError, "private"),
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip=None)]), ValueError, "private"),
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip="localhost")]), ValueError, "private"),
        # The node uses Go's IsLoopback() || IsPrivate(): no link-local, shared or documentation ranges.
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip="169.254.1.1")]), ValueError, "private"),
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip="100.64.0.1")]), ValueError, "private"),
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip="::ffff:8.8.8.8")]), ValueError, "private"),
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(port=None)]), ValueError, r"listeners\[1\]\.port"),
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(port="18080")]), TypeError, r"listeners\[1\]\.port"),
        (
            _web_config(vhosts=[_web_vhost(decoy={"mode": "static_directory", "directory": "/srv"})]),
            ValueError,
            "static_directory",
        ),
        (
            _web_config(vhosts=[_web_vhost(decoy={"mode": "http_upstream", "upstream": "http://example.com"})]),
            ValueError,
            "private",
        ),
        (
            _web_config(vhosts=[_web_vhost(decoy={"mode": "http_upstream", "upstream": "http://8.8.8.8"})]),
            ValueError,
            "private",
        ),
        (
            _web_config(vhosts=[_web_vhost(decoy={"mode": "http_upstream", "upstream": "http://0.0.0.0:80"})]),
            ValueError,
            "private",
        ),
        (_web_config(vhosts=[_web_vhost(decoy=None)]), ValueError, r"web\.vhosts\[0\]\.decoy"),
        (
            _web_config(vhosts=[_web_vhost(profiles=[{"user": "a", "secret_mode": "dd"}])]),
            ValueError,
            r"web\.vhosts\[0\]\.profiles must not be set: ",
        ),
        (_web_config(debug={"enabled": True}), ValueError, r"web\.debug must not be set: "),
        (_web_config(limits={"max_profiles": 10}), ValueError, r"web\.limits\.max_profiles must not be set: "),
        (
            _web_config(vhosts=[_web_vhost(user_profile={"secret_mode": "ee"})]),
            ValueError,
            r"web\.vhosts\[0\]\.user_profile\.secret_mode",
        ),
        (
            _web_config(vhosts=[_web_vhost(user_profile={"max_sessions": -1})]),
            ValueError,
            r"web\.vhosts\[0\]\.user_profile\.max_sessions",
        ),
        (
            _web_config(vhosts=[_web_vhost(user_profile={"max_streams": 1.5})]),
            TypeError,
            r"web\.vhosts\[0\]\.user_profile\.max_streams",
        ),
        (
            _web_config(vhosts=[_web_vhost(user_profile={"max_streams_per_session": True})]),
            TypeError,
            r"web\.vhosts\[0\]\.user_profile\.max_streams_per_session",
        ),
        (
            _web_config(vhosts=[_web_vhost(user_profile={"max_sessions": 4294967296})]),
            ValueError,
            r"web\.vhosts\[0\]\.user_profile\.max_sessions",
        ),
        (_web_config(vhosts=[_web_vhost(user_profile="dd")]), TypeError, r"web\.vhosts\[0\]\.user_profile"),
        (
            _web_config(vhosts=[_web_vhost(user_profile={"max_session": 4})]),
            ValueError,
            r"web\.vhosts\[0\]\.user_profile\.max_session is not supported",
        ),
        # The node reads ip as a string and parses it with net.ParseIP, which has no integer form and no IPv6 zone.
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip=2130706433)]), ValueError, "private"),
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(ip="fd00::1%eth0")]), ValueError, "private"),
        # The node's url.Parse refuses whitespace and control characters; urlsplit would strip or drop them.
        (
            _web_config(vhosts=[_web_vhost(decoy={"mode": "http_upstream", "upstream": " http://127.0.0.1:18081"})]),
            ValueError,
            r"web\.vhosts\[0\]\.decoy\.upstream",
        ),
        (
            _web_config(vhosts=[_web_vhost(decoy={"mode": "http_upstream", "upstream": "http://127.0.0.1:18\t081"})]),
            ValueError,
            r"web\.vhosts\[0\]\.decoy\.upstream",
        ),
        (
            _web_config(vhosts=[_web_vhost(decoy={"mode": "http_upstream", "upstream": "http://[fd00::1%25eth0]:80"})]),
            ValueError,
            r"web\.vhosts\[0\]\.decoy\.upstream",
        ),
        (_web_config(listeners=[{"ip": "0.0.0.0"}]), ValueError, "web"),
        (_web_config(listeners=[]), ValueError, "web"),
        (_tls_config(server={"port": 443, "listeners": [{"ip": "0.0.0.0"}, _web_listener()]}), ValueError, "web"),
        (_web_config(enabled=False), ValueError, "web"),
        (_web_config(vhosts=[]), ValueError, "web"),
        (_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(transport="socks")]), ValueError, "transport"),
        (_web_config(enabled="yes"), TypeError, r"web\.enabled"),
        (_web_config(vhosts="x"), TypeError, r"web\.vhosts"),
        (_web_config(vhosts=[1]), TypeError, r"web\.vhosts\[0\]"),
    ],
)
def test_unsafe_web_rejected(config, error, message):
    with pytest.raises(error, match=message):
        MtprotoConfig(config)


def test_web_listener_port_clash():
    with pytest.raises(ValueError, match=r"server\.listeners\[1\]\.port"):
        MtprotoConfig(_web_config(listeners=[{"ip": "0.0.0.0"}, _web_listener(port=443)]))
    with pytest.raises(ValueError, match=r"server\.listeners\[1\]\.port"):
        MtprotoConfig(_web_config(listeners=[{"ip": "0.0.0.0", "port": 443}, _web_listener(port=443)]))
    # A WEB-only core still keeps telemt's default port free of the WEB listener.
    with pytest.raises(ValueError, match=r"server\.listeners\[0\]\.port"):
        MtprotoConfig(_web_config(listeners=[_web_listener(port=443)]))


def test_native_flag():
    assert MtprotoConfig(_tls_config()).inbounds_by_tag["mtproto"]["native"] is True
    assert (
        MtprotoConfig(_tls_config(server={"port": 443, "listeners": []})).inbounds_by_tag["mtproto"]["native"] is True
    )
    mixed = MtprotoConfig(_web_config(listeners=[_web_listener(), {"ip": "::", "transport": "mtproxy"}]))
    assert mixed.inbounds_by_tag["mtproto"]["native"] is True
    web_only = MtprotoConfig(_web_config(listeners=[_web_listener(), _web_listener(ip="10.0.0.5")]))
    assert web_only.inbounds_by_tag["mtproto"]["native"] is False


def test_port_rule_applies_to_mtproxy_only():
    core = MtprotoConfig(_web_config(listeners=[{"ip": "0.0.0.0", "port": 443}, _web_listener(port=18080)]))
    assert core.inbounds_by_tag["mtproto"]["listen_port"] == 443
    with pytest.raises(ValueError, match=r"server\.listeners\[0\]\.port must equal server\.port"):
        MtprotoConfig(_web_config(listeners=[{"ip": "0.0.0.0", "port": 8443}, _web_listener()]))


_SECRET = "00112233445566778899aabbccddeeff"


def test_secret_is_never_generated_on_read():
    assert ProxyTable().mtproto.secret is None
    assert ProxyTable.model_validate({}).mtproto.secret is None


def test_secret_normalized():
    assert MtprotoSettings(secret=" " + _SECRET.upper() + " ").secret == _SECRET
    assert MtprotoSettings(secret="").secret is None
    for value in ("not-hex", "ab" * 15, 123):
        with pytest.raises(ValidationError):
            MtprotoSettings(secret=value)


def test_ad_tag_rules():
    assert MtprotoSettings(user_ad_tag="").user_ad_tag == ""
    assert MtprotoSettings(user_ad_tag=None).user_ad_tag == ""
    assert MtprotoSettings(user_ad_tag="AB" * 16).user_ad_tag == "ab" * 16
    for value in ("not-hex", "ab" * 15, 5):
        with pytest.raises(ValidationError):
            MtprotoSettings(user_ad_tag=value)


@pytest.mark.parametrize("field", ["max_tcp_conns", "max_unique_ips"])
def test_limits_are_strict_uint32(field):
    assert getattr(MtprotoSettings(**{field: 0}), field) == 0
    assert getattr(MtprotoSettings(**{field: 4294967295}), field) == 4294967295
    for value in (-1, 4294967296, True, "7", 7.0):
        with pytest.raises(ValidationError):
            MtprotoSettings(**{field: value})


def test_generate_mtproto_secret_is_random_hex():
    first = generate_mtproto_secret()
    second = generate_mtproto_secret()
    assert re.fullmatch(r"[0-9a-f]{32}", first)
    assert re.fullmatch(r"[0-9a-f]{32}", second)
    assert first != second


def test_backend_type_for_core_maps_mtproto():
    assert backend_type_for_core(CoreType.mtproto) == service.BackendType.MTPROTO == 2
    assert backend_type_for_core(CoreType.wg) == service.BackendType.WIREGUARD
    assert backend_type_for_core(CoreType.xray) == service.BackendType.XRAY


def test_serializer_sends_mtproto_only_for_the_mtproto_protocol():
    settings = {"mtproto": {"secret": "00112233445566778899aabbccddeeff"}}
    proto = _serialize_user_for_node(7, settings, ["mtproto"], frozenset({ProxyProtocol.mtproto}))
    assert proto.proxies.HasField("mtproto") and proto.proxies.mtproto.secret == "00112233445566778899aabbccddeeff"
    other = _serialize_user_for_node(7, settings, ["vless-in"], frozenset({ProxyProtocol.vless}))
    assert not other.proxies.HasField("mtproto")

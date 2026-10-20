import re

import pytest
from PasarGuardNodeBridge.common import service_pb2 as service
from pydantic import ValidationError

from app.core.mtproto import TELEMT_DEFAULT_MODES, TELEMT_DEFAULT_PORT, TLS_DOMAIN_PLACEHOLDER, MtprotoConfig
from app.db.models import CoreType
from app.models.protocol import ProxyProtocol
from app.models.proxy import MtprotoSettings, ProxyTable, generate_mtproto_secret
from app.node.user import _serialize_user_for_node
from app.operation.node import _backend_type_for_core


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
    "web",
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
_OBJECT_PATHS = ("general", "general.telemetry", "general.modes", "server", "access", "logging", "censorship")


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
        (" www.example.org ", "www.example.org"),
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
        MtprotoConfig(_tls_config(server={"port": 443, "listeners": [{"ip": "0.0.0.0", "transport": "web"}]}))
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


def test_mtproto_secret_generation_and_validation():
    secret = generate_mtproto_secret()
    assert len(secret) == 32
    settings = MtprotoSettings(secret=secret.upper())
    assert settings.secret == secret.lower()
    with pytest.raises(ValidationError):
        MtprotoSettings(secret="not-hex")


def test_proxy_table_includes_mtproto_secret():
    table = ProxyTable()
    dumped = table.dict()
    assert len(dumped["mtproto"]["secret"]) == 32
    assert dumped["mtproto"]["max_tcp_conns"] == 0


def test_backend_type_for_core_maps_mtproto():
    assert _backend_type_for_core(CoreType.mtproto) == service.BackendType.MTPROTO == 2
    assert _backend_type_for_core(CoreType.wg) == service.BackendType.WIREGUARD
    assert _backend_type_for_core(CoreType.xray) == service.BackendType.XRAY


def test_serializer_sends_mtproto_only_for_the_mtproto_protocol():
    settings = {"mtproto": {"secret": "00112233445566778899aabbccddeeff"}}
    proto = _serialize_user_for_node(7, settings, ["mtproto"], frozenset({ProxyProtocol.mtproto}))
    assert proto.proxies.HasField("mtproto") and proto.proxies.mtproto.secret == "00112233445566778899aabbccddeeff"
    other = _serialize_user_for_node(7, settings, ["vless-in"], frozenset({ProxyProtocol.vless}))
    assert not other.proxies.HasField("mtproto")

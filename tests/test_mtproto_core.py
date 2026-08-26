import pytest
from pydantic import ValidationError

from app.core.mtproto import MtprotoConfig
from app.db.models import CoreType
from app.models.protocol import ProxyProtocol
from app.models.proxy import MtprotoSettings, ProxyTable, generate_mtproto_secret


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


def test_mtproto_config_rejects_restricted_access_keys():
    with pytest.raises(ValueError, match="access.users"):
        MtprotoConfig(_valid_config(access={"users": {"alice": "deadbeef"}}))


def test_mtproto_config_rejects_missing_server_port():
    with pytest.raises(ValueError, match="server.port"):
        MtprotoConfig(_valid_config(server={"listeners": [{"ip": "0.0.0.0"}]}))


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

"""Tests for the protocols property added to WireGuardConfig and XRayConfig,
and the _protocols_from_inbounds_by_tag helper function.

Covered changes:
- app/core/abstract_core.py: protocols abstract property
- app/core/wireguard.py: protocols property returning frozenset({ProxyProtocol.wireguard})
- app/core/xray.py: _protocols_from_inbounds_by_tag + XRayConfig.protocols property
"""
import pytest

from app.models.protocol import ProxyProtocol
from app.core.xray import XRayConfig, _protocols_from_inbounds_by_tag
from app.core.wireguard import WireGuardConfig


# ---------------------------------------------------------------------------
# _protocols_from_inbounds_by_tag
# ---------------------------------------------------------------------------

class TestProtocolsFromInboundsByTag:
    """Unit tests for the pure helper function."""

    def test_empty_dict_returns_empty_frozenset(self):
        result = _protocols_from_inbounds_by_tag({})
        assert result == frozenset()

    def test_single_known_protocol(self):
        inbounds = {"tag1": {"protocol": "vmess"}}
        result = _protocols_from_inbounds_by_tag(inbounds)
        assert result == frozenset({ProxyProtocol.vmess})

    def test_multiple_different_protocols(self):
        inbounds = {
            "a": {"protocol": "vmess"},
            "b": {"protocol": "vless"},
            "c": {"protocol": "trojan"},
        }
        result = _protocols_from_inbounds_by_tag(inbounds)
        assert result == frozenset({ProxyProtocol.vmess, ProxyProtocol.vless, ProxyProtocol.trojan})

    def test_all_six_protocols(self):
        inbounds = {
            "a": {"protocol": "vmess"},
            "b": {"protocol": "vless"},
            "c": {"protocol": "trojan"},
            "d": {"protocol": "shadowsocks"},
            "e": {"protocol": "wireguard"},
            "f": {"protocol": "hysteria"},
        }
        result = _protocols_from_inbounds_by_tag(inbounds)
        assert result == frozenset(ProxyProtocol)

    def test_unknown_protocol_is_skipped(self):
        inbounds = {
            "a": {"protocol": "unknown_proto"},
            "b": {"protocol": "vmess"},
        }
        result = _protocols_from_inbounds_by_tag(inbounds)
        assert result == frozenset({ProxyProtocol.vmess})

    def test_all_unknown_protocols_returns_empty(self):
        inbounds = {
            "a": {"protocol": "http"},
            "b": {"protocol": "dns"},
        }
        result = _protocols_from_inbounds_by_tag(inbounds)
        assert result == frozenset()

    def test_duplicate_protocols_deduplicated(self):
        inbounds = {
            "tag1": {"protocol": "vless"},
            "tag2": {"protocol": "vless"},
            "tag3": {"protocol": "vless"},
        }
        result = _protocols_from_inbounds_by_tag(inbounds)
        assert result == frozenset({ProxyProtocol.vless})
        assert len(result) == 1

    def test_returns_frozenset(self):
        result = _protocols_from_inbounds_by_tag({"a": {"protocol": "trojan"}})
        assert isinstance(result, frozenset)

    def test_mixed_known_and_unknown(self):
        inbounds = {
            "a": {"protocol": "shadowsocks"},
            "b": {"protocol": "not-real"},
            "c": {"protocol": "hysteria"},
        }
        result = _protocols_from_inbounds_by_tag(inbounds)
        assert ProxyProtocol.shadowsocks in result
        assert ProxyProtocol.hysteria in result
        assert len(result) == 2


# ---------------------------------------------------------------------------
# WireGuardConfig.protocols
# ---------------------------------------------------------------------------

class TestWireGuardConfigProtocols:
    """WireGuardConfig.protocols must always return frozenset({ProxyProtocol.wireguard})."""

    def _make_wg_config(self) -> WireGuardConfig:
        """Create a WireGuardConfig with skip_validation to avoid needing real keys."""
        return WireGuardConfig(
            config={
                "interface_name": "wg0",
                "private_key": "fake_key",
                "listen_port": 51820,
                "address": ["10.0.0.1/24"],
            },
            skip_validation=True,
        )

    def test_protocols_returns_frozenset(self):
        wg = self._make_wg_config()
        assert isinstance(wg.protocols, frozenset)

    def test_protocols_contains_wireguard(self):
        wg = self._make_wg_config()
        assert ProxyProtocol.wireguard in wg.protocols

    def test_protocols_does_not_contain_other_protocols(self):
        wg = self._make_wg_config()
        for protocol in ProxyProtocol:
            if protocol != ProxyProtocol.wireguard:
                assert protocol not in wg.protocols

    def test_protocols_length_is_one(self):
        wg = self._make_wg_config()
        assert len(wg.protocols) == 1

    def test_protocols_is_correct_singleton(self):
        wg = self._make_wg_config()
        assert wg.protocols == frozenset({ProxyProtocol.wireguard})

    def test_from_json_protocols_is_wireguard(self):
        """from_json path should also produce the correct protocols."""
        data = {
            "config": {},
            "inbounds": ["wg0"],
            "inbounds_by_tag": {"wg0": {"protocol": "wireguard"}},
        }
        wg = WireGuardConfig.from_json(data)
        # WireGuardConfig.protocols is a fixed class-level constant, not derived from inbounds
        assert wg.protocols == frozenset({ProxyProtocol.wireguard})


# ---------------------------------------------------------------------------
# XRayConfig.protocols
# ---------------------------------------------------------------------------

class TestXRayConfigProtocols:
    """XRayConfig.protocols derived from inbounds during _resolve_inbounds."""

    def _make_xray_config(self, inbounds: list) -> XRayConfig:
        """Create XRayConfig with specified inbounds."""
        cfg = XRayConfig(
            config={"inbounds": inbounds},
        )
        return cfg

    def _make_xray_config_skip_validation(self, inbounds_by_tag: dict) -> XRayConfig:
        """Create XRayConfig using from_json to set inbounds_by_tag directly."""
        data = {
            "config": {},
            "inbounds": list(inbounds_by_tag.keys()),
            "inbounds_by_tag": inbounds_by_tag,
        }
        return XRayConfig.from_json(data)

    def test_empty_config_protocols_is_empty(self):
        cfg = XRayConfig(config={}, skip_validation=True)
        assert cfg.protocols == frozenset()

    def test_from_json_no_inbounds_empty_protocols(self):
        cfg = self._make_xray_config_skip_validation({})
        assert cfg.protocols == frozenset()

    def test_from_json_single_vless_inbound(self):
        cfg = self._make_xray_config_skip_validation(
            {"tag1": {"protocol": "vless"}}
        )
        assert cfg.protocols == frozenset({ProxyProtocol.vless})

    def test_from_json_multiple_protocols(self):
        cfg = self._make_xray_config_skip_validation(
            {
                "tag1": {"protocol": "vmess"},
                "tag2": {"protocol": "trojan"},
                "tag3": {"protocol": "shadowsocks"},
            }
        )
        assert cfg.protocols == frozenset({
            ProxyProtocol.vmess,
            ProxyProtocol.trojan,
            ProxyProtocol.shadowsocks,
        })

    def test_from_json_unknown_protocol_excluded(self):
        cfg = self._make_xray_config_skip_validation(
            {
                "tag1": {"protocol": "vmess"},
                "tag_bad": {"protocol": "unknown-proto"},
            }
        )
        assert cfg.protocols == frozenset({ProxyProtocol.vmess})

    def test_protocols_returns_frozenset(self):
        cfg = self._make_xray_config_skip_validation({"t": {"protocol": "hysteria"}})
        assert isinstance(cfg.protocols, frozenset)

    def test_protocols_is_immutable(self):
        cfg = self._make_xray_config_skip_validation({"t": {"protocol": "trojan"}})
        # frozenset is immutable – confirm it raises AttributeError on add
        with pytest.raises(AttributeError):
            cfg.protocols.add(ProxyProtocol.vmess)

    def test_protocols_population_via_resolve_inbounds(self):
        """Test that protocols is populated during full config resolution (not skip_validation)."""
        # Minimal valid xray config with a vless inbound
        config = {
            "inbounds": [
                {
                    "tag": "test-vless",
                    "listen": "0.0.0.0",
                    "port": 1080,
                    "protocol": "vless",
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {"network": "tcp"},
                }
            ]
        }
        cfg = XRayConfig(config=config)
        assert ProxyProtocol.vless in cfg.protocols


# ---------------------------------------------------------------------------
# AbstractCore.protocols contract
# ---------------------------------------------------------------------------

class TestAbstractCoreProtocolsContract:
    """Verify that AbstractCore defines protocols as abstract."""

    def test_abstract_core_has_protocols_abstract_property(self):
        from app.core.abstract_core import AbstractCore
        import inspect

        # protocols must be listed as an abstract method
        abstract_methods = getattr(AbstractCore, "__abstractmethods__", set())
        assert "protocols" in abstract_methods, (
            "AbstractCore.protocols must be declared as an abstract property"
        )

    def test_concrete_classes_implement_protocols(self):
        """Both WireGuardConfig and XRayConfig should implement the protocols property."""
        from app.core.abstract_core import AbstractCore

        for cls in (WireGuardConfig, XRayConfig):
            assert hasattr(cls, "protocols"), f"{cls.__name__} should have protocols property"
            # It should NOT be in abstractmethods (i.e., it must be implemented)
            abstract_methods = getattr(cls, "__abstractmethods__", set())
            assert "protocols" not in abstract_methods, (
                f"{cls.__name__}.protocols should be implemented, not abstract"
            )
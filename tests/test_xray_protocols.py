"""
Tests for protocol-related changes in app/core/xray.py and app/core/wireguard.py:
- _protocols_from_inbounds_by_tag: extracts ProxyProtocol from inbound configs
- XRayConfig.protocols property: frozenset of detected protocols
- WireGuardConfig.protocols property: always frozenset({ProxyProtocol.wireguard})
- AbstractCore.protocols abstract property added
"""

import pytest

from app.models.protocol import ProxyProtocol


class TestProtocolsFromInboundsByTag:
    """Tests for the _protocols_from_inbounds_by_tag function in app/core/xray.py."""

    def _call(self, inbounds_by_tag: dict) -> frozenset:
        from app.core.xray import _protocols_from_inbounds_by_tag

        return _protocols_from_inbounds_by_tag(inbounds_by_tag)

    def test_empty_inbounds_returns_empty_frozenset(self):
        result = self._call({})
        assert result == frozenset()
        assert isinstance(result, frozenset)

    def test_single_vmess_inbound(self):
        inbounds = {"tag1": {"protocol": "vmess"}}
        result = self._call(inbounds)
        assert result == frozenset({ProxyProtocol.vmess})

    def test_single_vless_inbound(self):
        inbounds = {"tag1": {"protocol": "vless"}}
        result = self._call(inbounds)
        assert result == frozenset({ProxyProtocol.vless})

    def test_single_trojan_inbound(self):
        inbounds = {"tag1": {"protocol": "trojan"}}
        result = self._call(inbounds)
        assert result == frozenset({ProxyProtocol.trojan})

    def test_single_shadowsocks_inbound(self):
        inbounds = {"tag1": {"protocol": "shadowsocks"}}
        result = self._call(inbounds)
        assert result == frozenset({ProxyProtocol.shadowsocks})

    def test_single_hysteria_inbound(self):
        inbounds = {"tag1": {"protocol": "hysteria"}}
        result = self._call(inbounds)
        assert result == frozenset({ProxyProtocol.hysteria})

    def test_multiple_same_protocol_returns_single_entry(self):
        inbounds = {
            "tag1": {"protocol": "vmess"},
            "tag2": {"protocol": "vmess"},
            "tag3": {"protocol": "vmess"},
        }
        result = self._call(inbounds)
        assert result == frozenset({ProxyProtocol.vmess})
        assert len(result) == 1

    def test_multiple_distinct_protocols(self):
        inbounds = {
            "tag1": {"protocol": "vmess"},
            "tag2": {"protocol": "vless"},
            "tag3": {"protocol": "trojan"},
            "tag4": {"protocol": "shadowsocks"},
        }
        result = self._call(inbounds)
        assert result == frozenset({
            ProxyProtocol.vmess,
            ProxyProtocol.vless,
            ProxyProtocol.trojan,
            ProxyProtocol.shadowsocks,
        })

    def test_unknown_protocol_excluded(self):
        inbounds = {
            "tag1": {"protocol": "unknown_protocol"},
            "tag2": {"protocol": "vmess"},
        }
        result = self._call(inbounds)
        assert result == frozenset({ProxyProtocol.vmess})

    def test_all_unknown_protocols_returns_empty(self):
        inbounds = {
            "tag1": {"protocol": "http"},
            "tag2": {"protocol": "socks"},
        }
        result = self._call(inbounds)
        assert result == frozenset()

    def test_mixed_known_and_unknown_protocols(self):
        inbounds = {
            "tag1": {"protocol": "vless"},
            "tag2": {"protocol": "not-a-protocol"},
            "tag3": {"protocol": "shadowsocks"},
        }
        result = self._call(inbounds)
        assert ProxyProtocol.vless in result
        assert ProxyProtocol.shadowsocks in result
        assert len(result) == 2

    def test_returns_frozenset_type(self):
        result = self._call({"tag1": {"protocol": "vmess"}})
        assert isinstance(result, frozenset)

    def test_result_is_immutable(self):
        result = self._call({"tag1": {"protocol": "vmess"}})
        with pytest.raises(AttributeError):
            result.add(ProxyProtocol.vless)


class TestXRayConfigProtocols:
    """Tests for XRayConfig.protocols property."""

    def _make_xray_config_from_json(self, inbounds_by_tag: dict) -> object:
        """Use from_json to construct XRayConfig with specific inbounds_by_tag."""
        from app.core.xray import XRayConfig

        data = {
            "config": {},
            "exclude_inbound_tags": [],
            "fallbacks_inbound_tags": [],
            "inbounds": list(inbounds_by_tag.keys()),
            "inbounds_by_tag": inbounds_by_tag,
        }
        return XRayConfig.from_json(data)

    def test_empty_inbounds_by_tag_gives_empty_protocols(self):
        config = self._make_xray_config_from_json({})
        assert config.protocols == frozenset()

    def test_vmess_inbound_gives_vmess_protocol(self):
        config = self._make_xray_config_from_json({"tag1": {"protocol": "vmess"}})
        assert ProxyProtocol.vmess in config.protocols

    def test_vless_inbound_gives_vless_protocol(self):
        config = self._make_xray_config_from_json({"tag1": {"protocol": "vless"}})
        assert ProxyProtocol.vless in config.protocols

    def test_multiple_protocols_all_present(self):
        inbounds_by_tag = {
            "vmess_tag": {"protocol": "vmess"},
            "vless_tag": {"protocol": "vless"},
            "trojan_tag": {"protocol": "trojan"},
        }
        config = self._make_xray_config_from_json(inbounds_by_tag)
        assert config.protocols == frozenset({
            ProxyProtocol.vmess,
            ProxyProtocol.vless,
            ProxyProtocol.trojan,
        })

    def test_unknown_protocol_not_in_protocols(self):
        config = self._make_xray_config_from_json({"http_proxy": {"protocol": "http"}})
        assert config.protocols == frozenset()

    def test_protocols_is_frozenset(self):
        config = self._make_xray_config_from_json({"tag1": {"protocol": "shadowsocks"}})
        assert isinstance(config.protocols, frozenset)

    def test_protocols_set_from_resolve_inbounds(self):
        """
        Test that when XRayConfig is built from a valid minimal config,
        _protocols is set from _resolve_inbounds (via _protocols_from_inbounds_by_tag).
        """
        from app.core.xray import XRayConfig

        # Minimal but valid xray config
        minimal_config = {
            "inbounds": [
                {
                    "tag": "vless-in",
                    "protocol": "vless",
                    "port": 1234,
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {"network": "tcp"},
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        }
        config = XRayConfig(minimal_config)
        assert ProxyProtocol.vless in config.protocols

    def test_from_json_sets_protocols_from_inbounds_by_tag(self):
        """from_json reconstructs protocols from inbounds_by_tag."""
        from app.core.xray import XRayConfig

        data = {
            "config": {},
            "exclude_inbound_tags": [],
            "fallbacks_inbound_tags": [],
            "inbounds": ["ss-tag"],
            "inbounds_by_tag": {"ss-tag": {"protocol": "shadowsocks"}},
        }
        config = XRayConfig.from_json(data)
        assert config.protocols == frozenset({ProxyProtocol.shadowsocks})


class TestWireGuardConfigProtocols:
    """Tests for WireGuardConfig.protocols property."""

    def test_protocols_always_returns_wireguard(self):
        from app.core.wireguard import WireGuardConfig

        config = WireGuardConfig(skip_validation=True)
        assert config.protocols == frozenset({ProxyProtocol.wireguard})

    def test_protocols_is_frozenset(self):
        from app.core.wireguard import WireGuardConfig

        config = WireGuardConfig(skip_validation=True)
        assert isinstance(config.protocols, frozenset)

    def test_protocols_contains_only_wireguard(self):
        from app.core.wireguard import WireGuardConfig

        config = WireGuardConfig(skip_validation=True)
        assert len(config.protocols) == 1
        assert ProxyProtocol.wireguard in config.protocols

    def test_protocols_does_not_contain_other_protocols(self):
        from app.core.wireguard import WireGuardConfig

        config = WireGuardConfig(skip_validation=True)
        assert ProxyProtocol.vmess not in config.protocols
        assert ProxyProtocol.vless not in config.protocols
        assert ProxyProtocol.trojan not in config.protocols
        assert ProxyProtocol.shadowsocks not in config.protocols
        assert ProxyProtocol.hysteria not in config.protocols

    def test_module_level_constant_is_frozenset_with_wireguard(self):
        from app.core.wireguard import _WIREGUARD_PROTOCOLS

        assert _WIREGUARD_PROTOCOLS == frozenset({ProxyProtocol.wireguard})

    def test_protocols_returns_same_constant(self):
        from app.core.wireguard import WireGuardConfig, _WIREGUARD_PROTOCOLS

        config = WireGuardConfig(skip_validation=True)
        assert config.protocols is _WIREGUARD_PROTOCOLS


class TestAbstractCoreProtocolsProperty:
    """Tests for the new protocols abstract property in AbstractCore."""

    def test_abstract_core_has_protocols_property(self):
        from app.core.abstract_core import AbstractCore

        # protocols should be an abstractmethod
        assert "protocols" in AbstractCore.__abstractmethods__

    def test_xray_config_satisfies_protocols_abstract(self):
        """XRayConfig must implement the protocols property."""
        from app.core.xray import XRayConfig

        assert hasattr(XRayConfig, "protocols")
        # Check it's a property
        assert isinstance(XRayConfig.__dict__.get("protocols"), property)

    def test_wireguard_config_satisfies_protocols_abstract(self):
        """WireGuardConfig must implement the protocols property."""
        from app.core.wireguard import WireGuardConfig

        assert hasattr(WireGuardConfig, "protocols")
        assert isinstance(WireGuardConfig.__dict__.get("protocols"), property)

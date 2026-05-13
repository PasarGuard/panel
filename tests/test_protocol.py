"""Tests for app/models/protocol.py - ProxyProtocol enum and from_value classmethod."""

import pytest

from app.models.protocol import ProxyProtocol, _PROXY_PROTOCOL_BY_NAME


class TestProxyProtocolValues:
    """Test that ProxyProtocol enum has the expected values."""

    def test_vmess_value(self):
        assert ProxyProtocol.vmess == 1

    def test_vless_value(self):
        assert ProxyProtocol.vless == 2

    def test_trojan_value(self):
        assert ProxyProtocol.trojan == 3

    def test_shadowsocks_value(self):
        assert ProxyProtocol.shadowsocks == 4

    def test_wireguard_value(self):
        assert ProxyProtocol.wireguard == 5

    def test_hysteria_value(self):
        assert ProxyProtocol.hysteria == 6

    def test_total_protocols_count(self):
        assert len(ProxyProtocol) == 6

    def test_is_int_enum(self):
        assert isinstance(ProxyProtocol.vmess, int)
        assert int(ProxyProtocol.vmess) == 1

    def test_all_protocol_names(self):
        expected_names = {"vmess", "vless", "trojan", "shadowsocks", "wireguard", "hysteria"}
        actual_names = {p.name for p in ProxyProtocol}
        assert actual_names == expected_names


class TestProxyProtocolFromValue:
    """Test the from_value classmethod."""

    def test_from_value_vmess(self):
        result = ProxyProtocol.from_value("vmess")
        assert result == ProxyProtocol.vmess

    def test_from_value_vless(self):
        result = ProxyProtocol.from_value("vless")
        assert result == ProxyProtocol.vless

    def test_from_value_trojan(self):
        result = ProxyProtocol.from_value("trojan")
        assert result == ProxyProtocol.trojan

    def test_from_value_shadowsocks(self):
        result = ProxyProtocol.from_value("shadowsocks")
        assert result == ProxyProtocol.shadowsocks

    def test_from_value_wireguard(self):
        result = ProxyProtocol.from_value("wireguard")
        assert result == ProxyProtocol.wireguard

    def test_from_value_hysteria(self):
        result = ProxyProtocol.from_value("hysteria")
        assert result == ProxyProtocol.hysteria

    def test_from_value_unknown_returns_none(self):
        assert ProxyProtocol.from_value("unknown") is None

    def test_from_value_empty_string_returns_none(self):
        assert ProxyProtocol.from_value("") is None

    def test_from_value_uppercase_returns_none(self):
        # Names are case-sensitive (uses dict lookup by name)
        assert ProxyProtocol.from_value("VMESS") is None
        assert ProxyProtocol.from_value("Vless") is None

    def test_from_value_partial_name_returns_none(self):
        assert ProxyProtocol.from_value("vmes") is None
        assert ProxyProtocol.from_value("vless2") is None

    def test_from_value_all_protocols(self):
        """Every protocol name should resolve to its enum member."""
        for protocol in ProxyProtocol:
            result = ProxyProtocol.from_value(protocol.name)
            assert result is protocol, f"from_value({protocol.name!r}) returned {result!r}, expected {protocol!r}"

    def test_from_value_returns_protocol_type(self):
        result = ProxyProtocol.from_value("shadowsocks")
        assert isinstance(result, ProxyProtocol)


class TestProxyProtocolFrozenset:
    """Test ProxyProtocol usage in frozensets (as used in the codebase)."""

    def test_protocol_in_frozenset(self):
        protocols = frozenset(ProxyProtocol)
        assert ProxyProtocol.vmess in protocols
        assert ProxyProtocol.wireguard in protocols

    def test_frozenset_of_single_protocol(self):
        wireguard_set = frozenset((ProxyProtocol.wireguard,))
        assert ProxyProtocol.wireguard in wireguard_set
        assert ProxyProtocol.vmess not in wireguard_set

    def test_frozenset_membership_check(self):
        allowed = frozenset({ProxyProtocol.vmess, ProxyProtocol.vless})
        assert ProxyProtocol.vmess in allowed
        assert ProxyProtocol.vless in allowed
        assert ProxyProtocol.trojan not in allowed
        assert ProxyProtocol.shadowsocks not in allowed

    def test_all_protocols_frozenset(self):
        all_protocols = frozenset(ProxyProtocol)
        assert len(all_protocols) == 6


class TestProxyProtocolByNameDict:
    """Test the module-level _PROXY_PROTOCOL_BY_NAME dict."""

    def test_dict_contains_all_protocols(self):
        assert len(_PROXY_PROTOCOL_BY_NAME) == 6

    def test_dict_maps_name_to_protocol(self):
        assert _PROXY_PROTOCOL_BY_NAME["vmess"] == ProxyProtocol.vmess
        assert _PROXY_PROTOCOL_BY_NAME["vless"] == ProxyProtocol.vless
        assert _PROXY_PROTOCOL_BY_NAME["trojan"] == ProxyProtocol.trojan
        assert _PROXY_PROTOCOL_BY_NAME["shadowsocks"] == ProxyProtocol.shadowsocks
        assert _PROXY_PROTOCOL_BY_NAME["wireguard"] == ProxyProtocol.wireguard
        assert _PROXY_PROTOCOL_BY_NAME["hysteria"] == ProxyProtocol.hysteria

    def test_dict_missing_key_raises_key_error(self):
        with pytest.raises(KeyError):
            _ = _PROXY_PROTOCOL_BY_NAME["unknown"]
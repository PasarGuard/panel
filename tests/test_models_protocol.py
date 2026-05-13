"""Tests for app/models/protocol.py — new ProxyProtocol enum."""
import pytest

from app.models.protocol import ProxyProtocol


class TestProxyProtocolValues:
    """Verify every enum member exists with the correct integer value."""

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

    def test_member_count(self):
        assert len(ProxyProtocol) == 6

    def test_is_int_enum(self):
        assert isinstance(ProxyProtocol.vmess, int)


class TestProxyProtocolFromValue:
    """Tests for the ProxyProtocol.from_value classmethod."""

    def test_from_value_vmess(self):
        assert ProxyProtocol.from_value("vmess") is ProxyProtocol.vmess

    def test_from_value_vless(self):
        assert ProxyProtocol.from_value("vless") is ProxyProtocol.vless

    def test_from_value_trojan(self):
        assert ProxyProtocol.from_value("trojan") is ProxyProtocol.trojan

    def test_from_value_shadowsocks(self):
        assert ProxyProtocol.from_value("shadowsocks") is ProxyProtocol.shadowsocks

    def test_from_value_wireguard(self):
        assert ProxyProtocol.from_value("wireguard") is ProxyProtocol.wireguard

    def test_from_value_hysteria(self):
        assert ProxyProtocol.from_value("hysteria") is ProxyProtocol.hysteria

    def test_from_value_unknown_returns_none(self):
        assert ProxyProtocol.from_value("unknown_protocol") is None

    def test_from_value_empty_string_returns_none(self):
        assert ProxyProtocol.from_value("") is None

    def test_from_value_case_sensitive_upper_returns_none(self):
        # Names are stored lowercase; uppercase should not match
        assert ProxyProtocol.from_value("VMESS") is None

    def test_from_value_partial_name_returns_none(self):
        assert ProxyProtocol.from_value("vmes") is None

    def test_from_value_integer_string_returns_none(self):
        # The lookup is by name, not by numeric value string
        assert ProxyProtocol.from_value("1") is None

    def test_all_names_resolvable(self):
        """Every enum member name should be resolvable via from_value."""
        for member in ProxyProtocol:
            assert ProxyProtocol.from_value(member.name) is member


class TestProxyProtocolFrozenset:
    """Verify that protocol values can be used in frozensets as expected."""

    def test_frozenset_membership(self):
        protocols = frozenset({ProxyProtocol.vmess, ProxyProtocol.vless})
        assert ProxyProtocol.vmess in protocols
        assert ProxyProtocol.trojan not in protocols

    def test_frozenset_of_all_protocols(self):
        all_protocols = frozenset(ProxyProtocol)
        assert len(all_protocols) == 6
        for member in ProxyProtocol:
            assert member in all_protocols

    def test_singleton_frozenset_wireguard(self):
        wg = frozenset((ProxyProtocol.wireguard,))
        assert ProxyProtocol.wireguard in wg
        assert ProxyProtocol.vmess not in wg
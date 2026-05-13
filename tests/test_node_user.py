"""Tests for app/node/user.py — _serialize_user_for_node with allowed_protocols filtering.

The PR refactored _serialize_user_for_node to conditionally include proxy
parameters based on the allowed_protocols frozenset. Previously it always
passed all proxy kwargs (filtering only by what create_proxy accepted via
_CREATE_PROXY_PARAMS). Now it explicitly guards each protocol block.

PasarGuardNodeBridge is mocked because it is not available in the test env.
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch, call

import pytest

from app.models.protocol import ProxyProtocol


# ---------------------------------------------------------------------------
# Bootstrap: create a minimal mock of the PasarGuardNodeBridge package so
# the module under test can be imported without the real library.
# ---------------------------------------------------------------------------

def _make_bridge_mock():
    bridge_pkg = ModuleType("PasarGuardNodeBridge")
    bridge_pkg.create_proxy = MagicMock(return_value=MagicMock(name="proxy_obj"))
    bridge_pkg.create_user = MagicMock(return_value=MagicMock(name="user_obj"))

    common_pkg = ModuleType("PasarGuardNodeBridge.common")
    service_pb2_pkg = ModuleType("PasarGuardNodeBridge.common.service_pb2")
    service_pb2_pkg.User = MagicMock(name="ProtoUser")

    bridge_pkg.common = common_pkg
    common_pkg.service_pb2 = service_pb2_pkg

    sys.modules.setdefault("PasarGuardNodeBridge", bridge_pkg)
    sys.modules.setdefault("PasarGuardNodeBridge.common", common_pkg)
    sys.modules.setdefault("PasarGuardNodeBridge.common.service_pb2", service_pb2_pkg)

    return bridge_pkg


_BRIDGE_MOCK = _make_bridge_mock()


# Now safe to import
from app.node.user import _serialize_user_for_node, _ALL_PROXY_PROTOCOLS  # noqa: E402


# ---------------------------------------------------------------------------
# Sample user settings covering all six protocols
# ---------------------------------------------------------------------------

FULL_USER_SETTINGS = {
    "vmess": {"id": "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb"},
    "vless": {"id": "11112222-3333-4444-5555-666677778888"},
    "trojan": {"password": "trojan-pass"},
    "shadowsocks": {"password": "ss-pass", "method": "chacha20-ietf-poly1305"},
    "wireguard": {"public_key": "wg-pub-key", "peer_ips": ["10.0.0.2/32"]},
    "hysteria": {"auth": "hysteria-auth"},
}


def _call_serialize(user_settings: dict, allowed_protocols=None):
    """Helper that resets mocks, calls _serialize_user_for_node, and returns (create_proxy_kwargs, create_user_args)."""
    _BRIDGE_MOCK.create_proxy.reset_mock()
    _BRIDGE_MOCK.create_user.reset_mock()
    _BRIDGE_MOCK.create_proxy.return_value = MagicMock(name="proxy_obj")

    _serialize_user_for_node(
        id=1,
        username="testuser",
        user_settings=user_settings,
        inbounds=["tag1"],
        allowed_protocols=allowed_protocols,
    )

    assert _BRIDGE_MOCK.create_proxy.call_count == 1
    kwargs_passed = _BRIDGE_MOCK.create_proxy.call_args.kwargs
    return kwargs_passed


class TestSerializeUserForNodeAllProtocolsDefault:
    """When allowed_protocols is None, all six protocols should be included."""

    def test_none_allowed_protocols_includes_vmess(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, allowed_protocols=None)
        assert "vmess_id" in kwargs

    def test_none_allowed_protocols_includes_vless(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, allowed_protocols=None)
        assert "vless_id" in kwargs

    def test_none_allowed_protocols_includes_trojan(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, allowed_protocols=None)
        assert "trojan_password" in kwargs

    def test_none_allowed_protocols_includes_shadowsocks(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, allowed_protocols=None)
        assert "shadowsocks_password" in kwargs
        assert "shadowsocks_method" in kwargs

    def test_none_allowed_protocols_includes_wireguard(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, allowed_protocols=None)
        assert "wireguard_public_key" in kwargs
        assert "wireguard_peer_ips" in kwargs

    def test_none_allowed_protocols_includes_hysteria(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, allowed_protocols=None)
        assert "hysteria_auth" in kwargs

    def test_empty_frozenset_equivalent_to_none(self):
        """_ALL_PROXY_PROTOCOLS covers all six protocols."""
        assert _ALL_PROXY_PROTOCOLS == frozenset(ProxyProtocol)


class TestSerializeUserForNodeFilteredProtocols:
    """When a restricted frozenset is passed, only those protocols appear in kwargs."""

    def test_only_vmess_allowed(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.vmess}))
        assert "vmess_id" in kwargs
        assert "vless_id" not in kwargs
        assert "trojan_password" not in kwargs
        assert "shadowsocks_password" not in kwargs
        assert "wireguard_public_key" not in kwargs
        assert "hysteria_auth" not in kwargs

    def test_only_vless_allowed(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.vless}))
        assert "vless_id" in kwargs
        assert "vmess_id" not in kwargs

    def test_only_trojan_allowed(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.trojan}))
        assert "trojan_password" in kwargs
        assert "vmess_id" not in kwargs

    def test_only_shadowsocks_allowed(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.shadowsocks}))
        assert "shadowsocks_password" in kwargs
        assert "shadowsocks_method" in kwargs
        assert "vmess_id" not in kwargs
        assert "vless_id" not in kwargs

    def test_only_wireguard_allowed(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.wireguard}))
        assert "wireguard_public_key" in kwargs
        assert "wireguard_peer_ips" in kwargs
        assert "vmess_id" not in kwargs

    def test_only_hysteria_allowed(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.hysteria}))
        assert "hysteria_auth" in kwargs
        assert "vmess_id" not in kwargs

    def test_wireguard_only_protocols_frozenset(self):
        """Simulates a WireGuard core node with only wireguard protocol."""
        wg_only = frozenset({ProxyProtocol.wireguard})
        kwargs = _call_serialize(FULL_USER_SETTINGS, wg_only)
        assert set(kwargs.keys()) == {"wireguard_public_key", "wireguard_peer_ips"}

    def test_xray_subset_vmess_vless_trojan(self):
        xray_protocols = frozenset({ProxyProtocol.vmess, ProxyProtocol.vless, ProxyProtocol.trojan})
        kwargs = _call_serialize(FULL_USER_SETTINGS, xray_protocols)
        assert "vmess_id" in kwargs
        assert "vless_id" in kwargs
        assert "trojan_password" in kwargs
        assert "shadowsocks_password" not in kwargs
        assert "wireguard_public_key" not in kwargs
        assert "hysteria_auth" not in kwargs

    def test_empty_allowed_protocols_passes_no_kwargs(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset())
        assert kwargs == {}


class TestSerializeUserForNodeValueMapping:
    """Verify that the correct values are extracted from user_settings."""

    def test_vmess_id_value(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.vmess}))
        assert kwargs["vmess_id"] == "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb"

    def test_vless_id_value(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.vless}))
        assert kwargs["vless_id"] == "11112222-3333-4444-5555-666677778888"

    def test_trojan_password_value(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.trojan}))
        assert kwargs["trojan_password"] == "trojan-pass"

    def test_shadowsocks_values(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.shadowsocks}))
        assert kwargs["shadowsocks_password"] == "ss-pass"
        assert kwargs["shadowsocks_method"] == "chacha20-ietf-poly1305"

    def test_wireguard_values(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.wireguard}))
        assert kwargs["wireguard_public_key"] == "wg-pub-key"
        assert kwargs["wireguard_peer_ips"] == ["10.0.0.2/32"]

    def test_hysteria_auth_value(self):
        kwargs = _call_serialize(FULL_USER_SETTINGS, frozenset({ProxyProtocol.hysteria}))
        assert kwargs["hysteria_auth"] == "hysteria-auth"

    def test_wireguard_peer_ips_defaults_to_empty_list_when_missing(self):
        settings = {"wireguard": {"public_key": "some-key"}}  # no peer_ips
        kwargs = _call_serialize(settings, frozenset({ProxyProtocol.wireguard}))
        assert kwargs["wireguard_peer_ips"] == []

    def test_missing_protocol_settings_returns_none(self):
        # Settings dict missing vmess key entirely
        settings = {}
        kwargs = _call_serialize(settings, frozenset({ProxyProtocol.vmess}))
        assert kwargs["vmess_id"] is None


class TestSerializeUserForNodeCreateUserCall:
    """Verify create_user is called with the expected arguments."""

    def test_create_user_called_once(self):
        _BRIDGE_MOCK.create_user.reset_mock()
        _BRIDGE_MOCK.create_proxy.reset_mock()
        _serialize_user_for_node(1, "bob", FULL_USER_SETTINGS, ["tag1"], None)
        assert _BRIDGE_MOCK.create_user.call_count == 1

    def test_create_user_receives_id_dot_username(self):
        _BRIDGE_MOCK.create_user.reset_mock()
        _serialize_user_for_node(42, "alice", FULL_USER_SETTINGS, ["tag1"], None)
        positional_args = _BRIDGE_MOCK.create_user.call_args.args
        assert positional_args[0] == "42.alice"

    def test_create_user_receives_inbounds(self):
        _BRIDGE_MOCK.create_user.reset_mock()
        _serialize_user_for_node(1, "bob", FULL_USER_SETTINGS, ["tag_a", "tag_b"], None)
        positional_args = _BRIDGE_MOCK.create_user.call_args.args
        assert positional_args[2] == ["tag_a", "tag_b"]

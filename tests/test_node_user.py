"""
Tests for app/node/user.py - _serialize_user_for_node refactored to use allowed_protocols.

Key change: the function now conditionally includes proxy kwargs based on the
allowed_protocols frozenset, instead of always including all protocol fields.
"""

import sys
import types
from unittest.mock import MagicMock, call, patch

import pytest

from app.models.protocol import ProxyProtocol


# ---------------------------------------------------------------------------
# Helpers to set up the PasarGuardNodeBridge mock before importing node.user
# ---------------------------------------------------------------------------


def _make_bridge_mock():
    """Return a (module_mock, create_proxy_mock, create_user_mock) triple."""
    bridge_module = types.ModuleType("PasarGuardNodeBridge")
    common_module = types.ModuleType("PasarGuardNodeBridge.common")
    service_module = types.ModuleType("PasarGuardNodeBridge.common.service_pb2")

    create_proxy_mock = MagicMock(name="create_proxy", return_value=MagicMock(name="proxy_obj"))
    create_user_mock = MagicMock(name="create_user", return_value=MagicMock(name="user_obj"))

    bridge_module.create_proxy = create_proxy_mock
    bridge_module.create_user = create_user_mock
    service_module.User = MagicMock(name="ProtoUser")

    common_module.service_pb2 = service_module
    bridge_module.common = common_module

    return bridge_module, create_proxy_mock, create_user_mock


@pytest.fixture(autouse=True)
def mock_bridge(monkeypatch):
    """Inject fake PasarGuardNodeBridge before any import of app.node.user."""
    bridge_module, create_proxy_mock, create_user_mock = _make_bridge_mock()

    monkeypatch.setitem(sys.modules, "PasarGuardNodeBridge", bridge_module)
    monkeypatch.setitem(sys.modules, "PasarGuardNodeBridge.common", bridge_module.common)
    monkeypatch.setitem(sys.modules, "PasarGuardNodeBridge.common.service_pb2", bridge_module.common.service_pb2)

    # Remove cached app.node.user so it re-imports with our mock
    monkeypatch.delitem(sys.modules, "app.node.user", raising=False)

    yield create_proxy_mock, create_user_mock


def _call_serialize(user_settings: dict, inbounds=None, allowed_protocols=None):
    """Import _serialize_user_for_node fresh and call it."""
    from app.node.user import _serialize_user_for_node

    return _serialize_user_for_node(
        id=42,
        username="testuser",
        user_settings=user_settings,
        inbounds=inbounds,
        allowed_protocols=allowed_protocols,
    )


FULL_USER_SETTINGS = {
    "vmess": {"id": "vmess-uuid-1234"},
    "vless": {"id": "vless-uuid-5678"},
    "trojan": {"password": "trojan-pass"},
    "shadowsocks": {"password": "ss-pass", "method": "chacha20-ietf-poly1305"},
    "wireguard": {"public_key": "wg-pub-key", "peer_ips": ["10.0.0.1/32"]},
    "hysteria": {"auth": "hysteria-auth"},
}


class TestSerializeUserForNodeAllProtocols:
    """When allowed_protocols is None, all protocols should be included."""

    def test_none_allowed_protocols_includes_vmess(self, mock_bridge):
        create_proxy, create_user = mock_bridge
        _call_serialize(FULL_USER_SETTINGS, inbounds=["tag1"], allowed_protocols=None)
        kwargs = create_proxy.call_args.kwargs
        assert "vmess_id" in kwargs
        assert kwargs["vmess_id"] == "vmess-uuid-1234"

    def test_none_allowed_protocols_includes_vless(self, mock_bridge):
        create_proxy, create_user = mock_bridge
        _call_serialize(FULL_USER_SETTINGS, inbounds=["tag1"], allowed_protocols=None)
        kwargs = create_proxy.call_args.kwargs
        assert "vless_id" in kwargs
        assert kwargs["vless_id"] == "vless-uuid-5678"

    def test_none_allowed_protocols_includes_trojan(self, mock_bridge):
        create_proxy, create_user = mock_bridge
        _call_serialize(FULL_USER_SETTINGS, inbounds=["tag1"], allowed_protocols=None)
        kwargs = create_proxy.call_args.kwargs
        assert "trojan_password" in kwargs
        assert kwargs["trojan_password"] == "trojan-pass"

    def test_none_allowed_protocols_includes_shadowsocks(self, mock_bridge):
        create_proxy, create_user = mock_bridge
        _call_serialize(FULL_USER_SETTINGS, inbounds=["tag1"], allowed_protocols=None)
        kwargs = create_proxy.call_args.kwargs
        assert "shadowsocks_password" in kwargs
        assert kwargs["shadowsocks_password"] == "ss-pass"
        assert "shadowsocks_method" in kwargs
        assert kwargs["shadowsocks_method"] == "chacha20-ietf-poly1305"

    def test_none_allowed_protocols_includes_wireguard(self, mock_bridge):
        create_proxy, create_user = mock_bridge
        _call_serialize(FULL_USER_SETTINGS, inbounds=["tag1"], allowed_protocols=None)
        kwargs = create_proxy.call_args.kwargs
        assert "wireguard_public_key" in kwargs
        assert kwargs["wireguard_public_key"] == "wg-pub-key"
        assert "wireguard_peer_ips" in kwargs
        assert kwargs["wireguard_peer_ips"] == ["10.0.0.1/32"]

    def test_none_allowed_protocols_includes_hysteria(self, mock_bridge):
        create_proxy, create_user = mock_bridge
        _call_serialize(FULL_USER_SETTINGS, inbounds=["tag1"], allowed_protocols=None)
        kwargs = create_proxy.call_args.kwargs
        assert "hysteria_auth" in kwargs
        assert kwargs["hysteria_auth"] == "hysteria-auth"

    def test_all_protocols_frozenset_same_as_none(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(FULL_USER_SETTINGS, inbounds=["tag1"], allowed_protocols=frozenset(ProxyProtocol))
        kwargs = create_proxy.call_args.kwargs
        assert "vmess_id" in kwargs
        assert "vless_id" in kwargs
        assert "trojan_password" in kwargs
        assert "shadowsocks_password" in kwargs
        assert "wireguard_public_key" in kwargs
        assert "hysteria_auth" in kwargs


class TestSerializeUserForNodeFilteredProtocols:
    """When allowed_protocols is provided, only those protocols should appear."""

    def test_vmess_only(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            FULL_USER_SETTINGS,
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.vmess}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert "vmess_id" in kwargs
        assert "vless_id" not in kwargs
        assert "trojan_password" not in kwargs
        assert "shadowsocks_password" not in kwargs
        assert "wireguard_public_key" not in kwargs
        assert "hysteria_auth" not in kwargs

    def test_vless_only(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            FULL_USER_SETTINGS,
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.vless}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert "vless_id" in kwargs
        assert "vmess_id" not in kwargs
        assert "trojan_password" not in kwargs

    def test_shadowsocks_only(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            FULL_USER_SETTINGS,
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.shadowsocks}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert "shadowsocks_password" in kwargs
        assert "shadowsocks_method" in kwargs
        assert "vmess_id" not in kwargs
        assert "vless_id" not in kwargs
        assert "trojan_password" not in kwargs
        assert "wireguard_public_key" not in kwargs
        assert "hysteria_auth" not in kwargs

    def test_wireguard_only(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            FULL_USER_SETTINGS,
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.wireguard}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert "wireguard_public_key" in kwargs
        assert "wireguard_peer_ips" in kwargs
        assert "vmess_id" not in kwargs
        assert "vless_id" not in kwargs

    def test_trojan_only(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            FULL_USER_SETTINGS,
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.trojan}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert "trojan_password" in kwargs
        assert "vmess_id" not in kwargs
        assert "shadowsocks_password" not in kwargs

    def test_hysteria_only(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            FULL_USER_SETTINGS,
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.hysteria}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert "hysteria_auth" in kwargs
        assert "vmess_id" not in kwargs
        assert "vless_id" not in kwargs

    def test_empty_allowed_protocols_no_proxy_kwargs(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            FULL_USER_SETTINGS,
            inbounds=["tag1"],
            allowed_protocols=frozenset(),
        )
        kwargs = create_proxy.call_args.kwargs
        assert len(kwargs) == 0

    def test_vmess_and_vless(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            FULL_USER_SETTINGS,
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.vmess, ProxyProtocol.vless}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert "vmess_id" in kwargs
        assert "vless_id" in kwargs
        assert "trojan_password" not in kwargs

    def test_xray_protocols(self, mock_bridge):
        """Test with typical XRay protocols (vmess, vless, trojan, shadowsocks)."""
        create_proxy, _ = mock_bridge
        xray_protocols = frozenset({
            ProxyProtocol.vmess,
            ProxyProtocol.vless,
            ProxyProtocol.trojan,
            ProxyProtocol.shadowsocks,
        })
        _call_serialize(FULL_USER_SETTINGS, inbounds=["tag1"], allowed_protocols=xray_protocols)
        kwargs = create_proxy.call_args.kwargs
        assert "vmess_id" in kwargs
        assert "vless_id" in kwargs
        assert "trojan_password" in kwargs
        assert "shadowsocks_password" in kwargs
        assert "wireguard_public_key" not in kwargs
        assert "hysteria_auth" not in kwargs


class TestSerializeUserForNodeMissingSettings:
    """Test behavior when user_settings dict is missing protocol keys."""

    def test_missing_vmess_settings(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            {},
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.vmess}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert "vmess_id" in kwargs
        assert kwargs["vmess_id"] is None

    def test_missing_shadowsocks_settings(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            {},
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.shadowsocks}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert kwargs["shadowsocks_password"] is None
        assert kwargs["shadowsocks_method"] is None

    def test_missing_wireguard_settings(self, mock_bridge):
        create_proxy, _ = mock_bridge
        _call_serialize(
            {},
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.wireguard}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert kwargs["wireguard_public_key"] is None
        assert kwargs["wireguard_peer_ips"] == []

    def test_wireguard_peer_ips_none_becomes_empty_list(self, mock_bridge):
        """wireguard_peer_ips=None should be coerced to []."""
        create_proxy, _ = mock_bridge
        settings = {"wireguard": {"public_key": "some-key", "peer_ips": None}}
        _call_serialize(
            settings,
            inbounds=["tag1"],
            allowed_protocols=frozenset({ProxyProtocol.wireguard}),
        )
        kwargs = create_proxy.call_args.kwargs
        assert kwargs["wireguard_peer_ips"] == []


class TestSerializeUserForNodeCreateUserCall:
    """Test that create_user is called with the correct arguments."""

    def test_create_user_called_with_correct_name(self, mock_bridge):
        create_proxy, create_user = mock_bridge
        _call_serialize({}, inbounds=["tag1"], allowed_protocols=None)
        args = create_user.call_args.args
        assert args[0] == "42.testuser"

    def test_create_user_called_with_inbounds(self, mock_bridge):
        create_proxy, create_user = mock_bridge
        inbounds = ["tag1", "tag2", "tag3"]
        _call_serialize({}, inbounds=inbounds, allowed_protocols=None)
        args = create_user.call_args.args
        assert args[2] == inbounds

    def test_create_user_called_with_none_inbounds(self, mock_bridge):
        create_proxy, create_user = mock_bridge
        _call_serialize({}, inbounds=None, allowed_protocols=None)
        args = create_user.call_args.args
        assert args[2] is None


class TestNoVlessFlowInSerialize:
    """
    The old code handled vless_flow; the new code does not set vless_flow at all.
    Regression test: ensure flow-related kwargs are not passed to create_proxy.
    """

    def test_vless_flow_not_in_proxy_kwargs(self, mock_bridge):
        create_proxy, _ = mock_bridge
        settings = {"vless": {"id": "some-uuid", "flow": "xtls-rprx-vision"}}
        _call_serialize(settings, inbounds=["tag1"], allowed_protocols=frozenset({ProxyProtocol.vless}))
        kwargs = create_proxy.call_args.kwargs
        assert "vless_flow" not in kwargs

    def test_vless_only_id_is_passed(self, mock_bridge):
        create_proxy, _ = mock_bridge
        settings = {"vless": {"id": "my-vless-uuid"}}
        _call_serialize(settings, inbounds=["tag1"], allowed_protocols=frozenset({ProxyProtocol.vless}))
        kwargs = create_proxy.call_args.kwargs
        assert kwargs["vless_id"] == "my-vless-uuid"
        assert "vless_flow" not in kwargs
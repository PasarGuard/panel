"""Tests for app/models/proxy.py — changes in this PR.

Specifically:
- XTLSFlows removed (flow no longer exists in VlessSettings)
- VlessSettings no longer has a `flow` field
- ProxyTable no longer carries flow information through VlessSettings
"""
import pytest
from pydantic import ValidationError

from app.models.proxy import (
    ProxyTable,
    ShadowsocksMethods,
    VlessSettings,
    VMessSettings,
)


class TestVlessSettingsNoFlow:
    """VlessSettings should no longer contain a flow field."""

    def test_vless_settings_has_no_flow_attribute(self):
        settings = VlessSettings()
        assert not hasattr(settings, "flow"), "flow field should not exist on VlessSettings"

    def test_vless_settings_only_has_id(self):
        settings = VlessSettings()
        fields = set(settings.model_fields_set | set(settings.model_dump().keys()))
        assert "id" in fields
        assert "flow" not in fields

    def test_vless_settings_ignores_flow_in_input(self):
        # Extra fields should be ignored (pydantic default) or raise; either way, no flow attr
        try:
            settings = VlessSettings(flow="xtls-rprx-vision")
        except ValidationError:
            # Pydantic strict mode raises – acceptable
            return
        assert not hasattr(settings, "flow")

    def test_vless_settings_id_is_uuid(self):
        import uuid
        settings = VlessSettings()
        assert isinstance(settings.id, uuid.UUID)

    def test_vless_settings_dict_has_no_flow(self):
        settings = VlessSettings()
        d = settings.model_dump()
        assert "flow" not in d


class TestProxyTableNoFlow:
    """ProxyTable.vless should not carry any flow field."""

    def test_proxy_table_vless_no_flow(self):
        table = ProxyTable()
        assert not hasattr(table.vless, "flow")

    def test_proxy_table_dict_no_flow(self):
        table = ProxyTable()
        d = table.dict()
        assert "flow" not in d.get("vless", {})

    def test_proxy_table_shadowsocks_default_method(self):
        table = ProxyTable()
        assert table.shadowsocks.method == ShadowsocksMethods.CHACHA20_POLY1305

    def test_proxy_table_all_protocols_present(self):
        table = ProxyTable()
        d = table.dict()
        for protocol in ("vmess", "vless", "trojan", "shadowsocks", "wireguard", "hysteria"):
            assert protocol in d, f"Protocol '{protocol}' missing from ProxyTable.dict()"


class TestXTLSFlowsRemoved:
    """XTLSFlows enum should no longer be importable from app.models.proxy."""

    def test_xtls_flows_not_in_proxy_module(self):
        import app.models.proxy as proxy_module
        assert not hasattr(proxy_module, "XTLSFlows"), (
            "XTLSFlows was removed from app.models.proxy in this PR and should not be importable"
        )


class TestShadowsocksMethodsIntact:
    """ShadowsocksMethods enum should still have all four methods."""

    def test_aes_128_gcm(self):
        assert ShadowsocksMethods.AES_128_GCM == "aes-128-gcm"

    def test_aes_256_gcm(self):
        assert ShadowsocksMethods.AES_256_GCM == "aes-256-gcm"

    def test_chacha20_poly1305(self):
        assert ShadowsocksMethods.CHACHA20_POLY1305 == "chacha20-ietf-poly1305"

    def test_xchacha20_poly1305(self):
        assert ShadowsocksMethods.XCHACHA20_POLY1305 == "xchacha20-poly1305"

    def test_member_count(self):
        assert len(ShadowsocksMethods) == 4
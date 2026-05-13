"""Tests for app/models/settings.py — General model no longer has default_flow.

The PR removed:
    default_flow: XTLSFlows = Field(default=XTLSFlows.NONE)
from the General model.
"""
import pytest

from app.models.settings import General
from app.models.proxy import ShadowsocksMethods


class TestGeneralModelNoDefaultFlow:
    """General should no longer have a default_flow field."""

    def test_general_has_no_default_flow_attribute(self):
        g = General()
        assert not hasattr(g, "default_flow"), (
            "General model must not have a default_flow field after this PR"
        )

    def test_general_fields_do_not_include_flow(self):
        g = General()
        fields = g.model_dump()
        assert "default_flow" not in fields

    def test_general_only_has_default_method(self):
        g = General()
        fields = g.model_dump()
        assert set(fields.keys()) == {"default_method"}

    def test_general_default_method_is_chacha20(self):
        g = General()
        assert g.default_method == ShadowsocksMethods.CHACHA20_POLY1305

    def test_general_default_method_can_be_set(self):
        g = General(default_method=ShadowsocksMethods.AES_256_GCM)
        assert g.default_method == ShadowsocksMethods.AES_256_GCM

    def test_general_accepts_all_shadowsocks_methods(self):
        for method in ShadowsocksMethods:
            g = General(default_method=method)
            assert g.default_method == method

    def test_xtls_flows_not_importable_from_settings(self):
        import app.models.settings as settings_module
        assert not hasattr(settings_module, "XTLSFlows"), (
            "XTLSFlows should not be importable from app.models.settings after this PR"
        )
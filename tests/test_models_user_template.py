"""Tests for app/models/user_template.py — ExtraSettings no longer has flow field.

The PR removed:
    flow: XTLSFlows | None = Field(XTLSFlows.NONE)
from ExtraSettings.
"""
import pytest
from pydantic import ValidationError

from app.models.user_template import ExtraSettings
from app.models.proxy import ShadowsocksMethods


class TestExtraSettingsNoFlow:
    """ExtraSettings should not have a flow field."""

    def test_no_flow_attribute(self):
        es = ExtraSettings()
        assert not hasattr(es, "flow"), "ExtraSettings must not have a flow field after this PR"

    def test_fields_do_not_include_flow(self):
        es = ExtraSettings()
        fields = es.model_dump()
        assert "flow" not in fields

    def test_only_method_field_exists(self):
        es = ExtraSettings()
        fields = set(es.model_dump().keys())
        assert fields == {"method"}

    def test_default_method_is_chacha20(self):
        es = ExtraSettings()
        assert es.method == ShadowsocksMethods.CHACHA20_POLY1305

    def test_method_can_be_none(self):
        es = ExtraSettings(method=None)
        assert es.method is None

    def test_all_shadowsocks_methods_accepted(self):
        for method in ShadowsocksMethods:
            es = ExtraSettings(method=method)
            assert es.method == method

    def test_xtls_flows_not_importable_from_user_template(self):
        import app.models.user_template as ut_module
        assert not hasattr(ut_module, "XTLSFlows"), (
            "XTLSFlows should not be importable from app.models.user_template after this PR"
        )


class TestExtraSettingsDict:
    """ExtraSettings.dict() should not include flow."""

    def test_dict_no_flow(self):
        es = ExtraSettings()
        d = es.dict()
        assert "flow" not in d

    def test_dict_contains_method(self):
        es = ExtraSettings(method=ShadowsocksMethods.AES_128_GCM)
        d = es.dict()
        assert d["method"] == "aes-128-gcm"

    def test_dict_method_none(self):
        es = ExtraSettings(method=None)
        d = es.dict()
        assert d["method"] is None
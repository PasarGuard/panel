"""Tests for app/models/user.py — BulkUsersProxy no longer has flow field.

The PR removed:
    flow: XTLSFlows | None = Field(default=None)
from BulkUsersProxy.
"""
import pytest
from pydantic import ValidationError

from app.models.user import BulkUsersProxy
from app.models.proxy import ShadowsocksMethods


class TestBulkUsersProxyNoFlow:
    """BulkUsersProxy should not have a flow field."""

    def test_no_flow_attribute(self):
        obj = BulkUsersProxy()
        assert not hasattr(obj, "flow"), "BulkUsersProxy must not have a flow field after this PR"

    def test_fields_do_not_include_flow(self):
        obj = BulkUsersProxy()
        fields = obj.model_dump()
        assert "flow" not in fields

    def test_method_field_exists_and_defaults_none(self):
        obj = BulkUsersProxy()
        assert obj.method is None

    def test_method_can_be_set(self):
        obj = BulkUsersProxy(method=ShadowsocksMethods.AES_256_GCM)
        assert obj.method == ShadowsocksMethods.AES_256_GCM

    def test_all_shadowsocks_methods_accepted(self):
        for method in ShadowsocksMethods:
            obj = BulkUsersProxy(method=method)
            assert obj.method == method

    def test_xtls_flows_not_importable_from_user_module(self):
        import app.models.user as user_module
        assert not hasattr(user_module, "XTLSFlows"), (
            "XTLSFlows should not be present in app.models.user after this PR"
        )

    def test_bulk_users_proxy_inherits_filter_fields(self):
        # BulkUsersProxy inherits from BulkUserFilter which has group_ids, admins, users, etc.
        obj = BulkUsersProxy(group_ids=[1, 2])
        assert obj.group_ids == [1, 2]


class TestBulkUsersProxyMethodSerialization:
    def test_method_serializes_correctly(self):
        obj = BulkUsersProxy(method=ShadowsocksMethods.CHACHA20_POLY1305)
        d = obj.model_dump()
        assert d["method"] == "chacha20-ietf-poly1305"

    def test_none_method_serializes_as_none(self):
        obj = BulkUsersProxy(method=None)
        d = obj.model_dump()
        assert d["method"] is None
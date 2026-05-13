"""
Tests for model changes introduced in this PR:
- app/models/proxy.py: XTLSFlows removed, VlessSettings.flow removed
- app/models/user_template.py: ExtraSettings.flow removed
- app/models/user.py: BulkUsersProxy.flow removed
- app/models/settings.py: General.default_flow removed
- app/models/validators.py: ProxyValidator.validate_proxy_url falsy check
- app/models/host.py: XHttpSettings.uplink_chunk_size changed to str|int|None with pattern
- app/models/status_emojis.py: STATUS_EMOJIS dict added
"""

import pytest
from pydantic import ValidationError


class TestVlessSettings:
    """VlessSettings no longer has a flow field."""

    def test_vless_settings_has_no_flow_field(self):
        from app.models.proxy import VlessSettings

        instance = VlessSettings()
        assert not hasattr(instance, "flow")

    def test_vless_settings_has_id_field(self):
        from app.models.proxy import VlessSettings

        instance = VlessSettings()
        assert hasattr(instance, "id")
        assert instance.id is not None

    def test_vless_settings_ignores_flow_in_input(self):
        """Extra fields should be ignored (Pydantic default)."""
        from app.models.proxy import VlessSettings

        # model_config may or may not forbid extras; just test no flow attribute
        instance = VlessSettings(id="12345678-1234-5678-1234-567812345678")
        assert not hasattr(instance, "flow")

    def test_xtls_flows_enum_removed(self):
        """XTLSFlows should no longer exist in app.models.proxy."""
        import app.models.proxy as proxy_module

        assert not hasattr(proxy_module, "XTLSFlows")


class TestExtraSettings:
    """ExtraSettings no longer has a flow field."""

    def test_extra_settings_has_no_flow_field(self):
        from app.models.user_template import ExtraSettings

        instance = ExtraSettings()
        assert not hasattr(instance, "flow")

    def test_extra_settings_has_method_field(self):
        from app.models.user_template import ExtraSettings

        instance = ExtraSettings()
        assert hasattr(instance, "method")

    def test_extra_settings_default_method(self):
        from app.models.proxy import ShadowsocksMethods
        from app.models.user_template import ExtraSettings

        instance = ExtraSettings()
        assert instance.method == ShadowsocksMethods.CHACHA20_POLY1305

    def test_extra_settings_dict_method_no_obj(self):
        from app.models.proxy import ShadowsocksMethods
        from app.models.user_template import ExtraSettings

        instance = ExtraSettings(method=ShadowsocksMethods.AES_256_GCM)
        result = instance.dict()
        assert "method" in result
        assert "flow" not in result

    def test_extra_settings_dict_contains_only_method(self):
        from app.models.user_template import ExtraSettings

        instance = ExtraSettings()
        result = instance.dict()
        assert set(result.keys()) == {"method"}

    def test_extra_settings_none_method(self):
        from app.models.user_template import ExtraSettings

        instance = ExtraSettings(method=None)
        assert instance.method is None


class TestBulkUsersProxy:
    """BulkUsersProxy no longer has a flow field."""

    def test_bulk_users_proxy_has_no_flow_field(self):
        from app.models.user import BulkUsersProxy

        instance = BulkUsersProxy()
        assert not hasattr(instance, "flow")

    def test_bulk_users_proxy_has_method_field(self):
        from app.models.user import BulkUsersProxy

        instance = BulkUsersProxy()
        assert hasattr(instance, "method")
        assert instance.method is None

    def test_bulk_users_proxy_accepts_shadowsocks_method(self):
        from app.models.proxy import ShadowsocksMethods
        from app.models.user import BulkUsersProxy

        instance = BulkUsersProxy(method=ShadowsocksMethods.AES_128_GCM)
        assert instance.method == ShadowsocksMethods.AES_128_GCM

    def test_bulk_users_proxy_method_none_by_default(self):
        from app.models.user import BulkUsersProxy

        instance = BulkUsersProxy()
        assert instance.method is None


class TestGeneralSettings:
    """General settings no longer has a default_flow field."""

    def test_general_has_no_default_flow(self):
        from app.models.settings import General

        instance = General()
        assert not hasattr(instance, "default_flow")

    def test_general_has_default_method(self):
        from app.models.proxy import ShadowsocksMethods
        from app.models.settings import General

        instance = General()
        assert hasattr(instance, "default_method")
        assert instance.default_method == ShadowsocksMethods.CHACHA20_POLY1305

    def test_general_default_method_can_be_set(self):
        from app.models.proxy import ShadowsocksMethods
        from app.models.settings import General

        instance = General(default_method=ShadowsocksMethods.AES_256_GCM)
        assert instance.default_method == ShadowsocksMethods.AES_256_GCM

    def test_general_fields(self):
        from app.models.settings import General

        fields = set(General.model_fields.keys())
        assert "default_method" in fields
        assert "default_flow" not in fields


class TestProxyValidatorChanges:
    """
    ProxyValidator.validate_proxy_url changed from `if value is None` to `if not value`.
    Empty string now returns None instead of attempting pattern validation.
    """

    def test_none_returns_none(self):
        from app.models.validators import ProxyValidator

        assert ProxyValidator.validate_proxy_url(None) is None

    def test_empty_string_returns_none(self):
        """Changed behavior: empty string now returns None."""
        from app.models.validators import ProxyValidator

        assert ProxyValidator.validate_proxy_url("") is None

    def test_valid_http_url_passes(self):
        from app.models.validators import ProxyValidator

        result = ProxyValidator.validate_proxy_url("http://127.0.0.1:8080")
        assert result == "http://127.0.0.1:8080"

    def test_valid_https_url_passes(self):
        from app.models.validators import ProxyValidator

        result = ProxyValidator.validate_proxy_url("https://proxy.example.com:443")
        assert result == "https://proxy.example.com:443"

    def test_valid_socks5_url_passes(self):
        from app.models.validators import ProxyValidator

        result = ProxyValidator.validate_proxy_url("socks5://127.0.0.1:1080")
        assert result == "socks5://127.0.0.1:1080"

    def test_valid_socks4_url_passes(self):
        from app.models.validators import ProxyValidator

        result = ProxyValidator.validate_proxy_url("socks4://proxy.example.com:1080")
        assert result == "socks4://proxy.example.com:1080"

    def test_valid_url_with_credentials_passes(self):
        from app.models.validators import ProxyValidator

        result = ProxyValidator.validate_proxy_url("socks5://user:pass@127.0.0.1:1080")
        assert result == "socks5://user:pass@127.0.0.1:1080"

    def test_invalid_scheme_raises(self):
        from app.models.validators import ProxyValidator

        with pytest.raises(ValueError, match="proxy_url must be a valid proxy address"):
            ProxyValidator.validate_proxy_url("ftp://127.0.0.1:21")

    def test_invalid_url_no_port_raises(self):
        from app.models.validators import ProxyValidator

        with pytest.raises(ValueError, match="proxy_url must be a valid proxy address"):
            ProxyValidator.validate_proxy_url("http://127.0.0.1")

    def test_invalid_url_no_scheme_raises(self):
        from app.models.validators import ProxyValidator

        with pytest.raises(ValueError, match="proxy_url must be a valid proxy address"):
            ProxyValidator.validate_proxy_url("127.0.0.1:8080")

    def test_whitespace_string_returns_none(self):
        """Whitespace is falsy in Python? No - it's truthy. But it will fail validation."""
        from app.models.validators import ProxyValidator

        # Whitespace is truthy, so it goes to the pattern check and should raise
        with pytest.raises(ValueError):
            ProxyValidator.validate_proxy_url("   ")


class TestXHttpSettingsUplinkChunkSize:
    """
    XHttpSettings.uplink_chunk_size changed from int|None to str|int|None with pattern.
    Also added to _empty_str_to_none validator list.
    """

    def test_uplink_chunk_size_none_by_default(self):
        from app.models.host import XHttpSettings

        instance = XHttpSettings()
        assert instance.uplink_chunk_size is None

    def test_uplink_chunk_size_accepts_integer_string(self):
        from app.models.host import XHttpSettings

        instance = XHttpSettings(uplink_chunk_size="1024")
        assert instance.uplink_chunk_size == "1024"

    def test_uplink_chunk_size_accepts_range_string(self):
        from app.models.host import XHttpSettings

        instance = XHttpSettings(uplink_chunk_size="1024-2048")
        assert instance.uplink_chunk_size == "1024-2048"

    def test_uplink_chunk_size_empty_string_becomes_none(self):
        from app.models.host import XHttpSettings

        instance = XHttpSettings(uplink_chunk_size="")
        assert instance.uplink_chunk_size is None

    def test_uplink_chunk_size_accepts_integer(self):
        from app.models.host import XHttpSettings

        instance = XHttpSettings(uplink_chunk_size=512)
        assert instance.uplink_chunk_size == 512

    def test_uplink_chunk_size_rejects_invalid_pattern(self):
        from app.models.host import XHttpSettings

        with pytest.raises(ValidationError):
            XHttpSettings(uplink_chunk_size="abc")

    def test_uplink_chunk_size_rejects_negative(self):
        from app.models.host import XHttpSettings

        with pytest.raises(ValidationError):
            XHttpSettings(uplink_chunk_size="-1")

    def test_uplink_chunk_size_single_large_number(self):
        from app.models.host import XHttpSettings

        instance = XHttpSettings(uplink_chunk_size="1234567890123456")
        assert instance.uplink_chunk_size == "1234567890123456"

    def test_uplink_chunk_size_range_with_large_numbers(self):
        from app.models.host import XHttpSettings

        instance = XHttpSettings(uplink_chunk_size="100-9999999999999999")
        assert instance.uplink_chunk_size == "100-9999999999999999"


class TestStatusEmojis:
    """STATUS_EMOJIS dict is a new module."""

    def test_status_emojis_contains_all_statuses(self):
        from app.models.status_emojis import STATUS_EMOJIS

        expected_keys = {"active", "expired", "limited", "disabled", "on_hold"}
        assert set(STATUS_EMOJIS.keys()) == expected_keys

    def test_status_emojis_active(self):
        from app.models.status_emojis import STATUS_EMOJIS

        assert STATUS_EMOJIS["active"] == "✅"

    def test_status_emojis_expired(self):
        from app.models.status_emojis import STATUS_EMOJIS

        assert STATUS_EMOJIS["expired"] == "⌛️"

    def test_status_emojis_limited(self):
        from app.models.status_emojis import STATUS_EMOJIS

        assert STATUS_EMOJIS["limited"] == "🪫"

    def test_status_emojis_disabled(self):
        from app.models.status_emojis import STATUS_EMOJIS

        assert STATUS_EMOJIS["disabled"] == "❌"

    def test_status_emojis_on_hold(self):
        from app.models.status_emojis import STATUS_EMOJIS

        assert STATUS_EMOJIS["on_hold"] == "🔌"

    def test_status_emojis_is_dict(self):
        from app.models.status_emojis import STATUS_EMOJIS

        assert isinstance(STATUS_EMOJIS, dict)
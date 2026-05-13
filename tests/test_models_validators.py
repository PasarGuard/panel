"""Tests for app/models/validators.py — ProxyValidator change.

The PR changed:
    if value is None:
        return value
to:
    if not value:
        return None

This means that empty strings now also produce None instead of being passed
through to the regex check, which previously would have raised a ValueError.
"""
import pytest

from app.models.validators import ProxyValidator


class TestProxyValidatorEmptyString:
    """Empty string should now return None (same as None input)."""

    def test_none_returns_none(self):
        assert ProxyValidator.validate_proxy_url(None) is None

    def test_empty_string_returns_none(self):
        # Key change: empty string must now return None instead of raising
        result = ProxyValidator.validate_proxy_url("")
        assert result is None

    def test_empty_string_does_not_raise(self):
        # Previously empty string would hit the regex and raise ValueError
        try:
            result = ProxyValidator.validate_proxy_url("")
        except ValueError:
            pytest.fail("validate_proxy_url('') should not raise ValueError after the PR change")


class TestProxyValidatorValidUrls:
    """Valid proxy URLs should pass through unchanged."""

    def test_http_host_port(self):
        url = "http://example.com:8080"
        assert ProxyValidator.validate_proxy_url(url) == url

    def test_https_host_port(self):
        url = "https://proxy.example.com:443"
        assert ProxyValidator.validate_proxy_url(url) == url

    def test_socks4_host_port(self):
        url = "socks4://10.0.0.1:1080"
        assert ProxyValidator.validate_proxy_url(url) == url

    def test_socks5_host_port(self):
        url = "socks5://10.0.0.1:1080"
        assert ProxyValidator.validate_proxy_url(url) == url

    def test_http_with_auth(self):
        url = "http://user:pass@host.example.com:3128"
        assert ProxyValidator.validate_proxy_url(url) == url

    def test_socks5_with_auth(self):
        url = "socks5://alice:secret@proxy.local:1080"
        assert ProxyValidator.validate_proxy_url(url) == url


class TestProxyValidatorInvalidUrls:
    """Invalid proxy URL strings should raise ValueError."""

    def test_missing_scheme_raises(self):
        with pytest.raises(ValueError, match="proxy_url must be a valid proxy address"):
            ProxyValidator.validate_proxy_url("host.example.com:8080")

    def test_unsupported_scheme_raises(self):
        with pytest.raises(ValueError, match="proxy_url must be a valid proxy address"):
            ProxyValidator.validate_proxy_url("ftp://host.example.com:21")

    def test_missing_port_raises(self):
        with pytest.raises(ValueError, match="proxy_url must be a valid proxy address"):
            ProxyValidator.validate_proxy_url("http://host.example.com")

    def test_whitespace_only_returns_none(self):
        # Falsy value check: whitespace string is truthy, but let's verify behaviour
        # A whitespace-only string is truthy in Python, so it should reach the regex
        # and raise ValueError (it won't match the scheme pattern)
        with pytest.raises(ValueError):
            ProxyValidator.validate_proxy_url("   ")

    def test_arbitrary_string_raises(self):
        with pytest.raises(ValueError, match="proxy_url must be a valid proxy address"):
            ProxyValidator.validate_proxy_url("not-a-proxy-url")
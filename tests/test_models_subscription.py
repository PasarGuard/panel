"""Tests for app/models/subscription.py — XHTTPTransportConfig.uplink_chunk_size change.

The PR changed uplink_chunk_size from:
    int | None
to:
    str | int | None  with pattern r"^\d{1,16}(?:-\d{1,16})?$"
"""
import pytest
from pydantic import ValidationError

from app.models.subscription import XHTTPTransportConfig


def _make_xhttp(**kwargs) -> XHTTPTransportConfig:
    return XHTTPTransportConfig(**kwargs)


class TestXHTTPTransportConfigUplinkChunkSizeNoneAndInt:
    def test_none_is_accepted(self):
        cfg = _make_xhttp(uplink_chunk_size=None)
        assert cfg.uplink_chunk_size is None

    def test_integer_is_accepted(self):
        cfg = _make_xhttp(uplink_chunk_size=2048)
        assert cfg.uplink_chunk_size == 2048

    def test_default_is_none(self):
        cfg = XHTTPTransportConfig()
        assert cfg.uplink_chunk_size is None


class TestXHTTPTransportConfigUplinkChunkSizeString:
    def test_numeric_string_accepted(self):
        cfg = _make_xhttp(uplink_chunk_size="1024")
        assert cfg.uplink_chunk_size == "1024"

    def test_range_string_accepted(self):
        cfg = _make_xhttp(uplink_chunk_size="512-2048")
        assert cfg.uplink_chunk_size == "512-2048"

    def test_single_digit_accepted(self):
        cfg = _make_xhttp(uplink_chunk_size="1")
        assert cfg.uplink_chunk_size == "1"

    def test_max_boundary_16_digits(self):
        cfg = _make_xhttp(uplink_chunk_size="9999999999999999")
        assert cfg.uplink_chunk_size == "9999999999999999"

    def test_range_max_boundary(self):
        cfg = _make_xhttp(uplink_chunk_size="1-9999999999999999")
        assert cfg.uplink_chunk_size == "1-9999999999999999"


class TestXHTTPTransportConfigUplinkChunkSizeInvalidStrings:
    def test_alphabetic_string_raises(self):
        with pytest.raises(ValidationError):
            _make_xhttp(uplink_chunk_size="big")

    def test_leading_dash_raises(self):
        with pytest.raises(ValidationError):
            _make_xhttp(uplink_chunk_size="-512")

    def test_double_dash_raises(self):
        with pytest.raises(ValidationError):
            _make_xhttp(uplink_chunk_size="512--1024")

    def test_too_many_digits_raises(self):
        with pytest.raises(ValidationError):
            _make_xhttp(uplink_chunk_size="12345678901234567")  # 17 digits

    def test_trailing_dash_raises(self):
        with pytest.raises(ValidationError):
            _make_xhttp(uplink_chunk_size="512-")


class TestXHTTPTransportConfigUplinkChunkSizeSerialization:
    """Verify serialization alias is applied correctly."""

    def test_serialized_alias_is_uplinkChunkSize(self):
        cfg = _make_xhttp(uplink_chunk_size="256")
        serialized = cfg.model_dump(by_alias=True, exclude_none=True)
        assert "uplinkChunkSize" in serialized
        assert serialized["uplinkChunkSize"] == "256"

    def test_none_excluded_from_serialization(self):
        cfg = _make_xhttp(uplink_chunk_size=None)
        serialized = cfg.model_dump(by_alias=True, exclude_none=True)
        assert "uplinkChunkSize" not in serialized
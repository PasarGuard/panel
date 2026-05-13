"""Tests for app/models/host.py — uplink_chunk_size type/pattern change.

The PR changed XHttpSettings.uplink_chunk_size from:
    int | None
to:
    str | int | None  with pattern r"^\d{1,16}(-\d{1,16})?$"

and added "uplink_chunk_size" to the _empty_str_to_none validator list,
so empty string is coerced to None before pattern validation.
"""
import pytest
from pydantic import ValidationError

from app.models.host import XHttpSettings


def _make_xhttp(**kwargs) -> XHttpSettings:
    """Helper: create XHttpSettings with only the given kwargs."""
    return XHttpSettings(**kwargs)


class TestXHttpSettingsUplinkChunkSizeTypes:
    """uplink_chunk_size now accepts str, int, or None."""

    def test_none_is_accepted(self):
        s = _make_xhttp(uplink_chunk_size=None)
        assert s.uplink_chunk_size is None

    def test_integer_is_accepted(self):
        s = _make_xhttp(uplink_chunk_size=1024)
        assert s.uplink_chunk_size == 1024

    def test_numeric_string_is_accepted(self):
        s = _make_xhttp(uplink_chunk_size="512")
        assert s.uplink_chunk_size == "512"

    def test_range_string_is_accepted(self):
        # Pattern: ^\d{1,16}(-\d{1,16})?$
        s = _make_xhttp(uplink_chunk_size="256-1024")
        assert s.uplink_chunk_size == "256-1024"


class TestXHttpSettingsUplinkChunkSizeEmptyString:
    """Empty string must be coerced to None (validator added in this PR)."""

    def test_empty_string_becomes_none(self):
        s = _make_xhttp(uplink_chunk_size="")
        assert s.uplink_chunk_size is None


class TestXHttpSettingsUplinkChunkSizePatternValidation:
    """Strings must match ^\d{1,16}(-\d{1,16})?$."""

    def test_single_number_string(self):
        s = _make_xhttp(uplink_chunk_size="100")
        assert s.uplink_chunk_size == "100"

    def test_range_string(self):
        s = _make_xhttp(uplink_chunk_size="100-200")
        assert s.uplink_chunk_size == "100-200"

    def test_large_number_at_boundary(self):
        # 16 digits is the max allowed
        s = _make_xhttp(uplink_chunk_size="1234567890123456")
        assert s.uplink_chunk_size == "1234567890123456"

    def test_invalid_string_with_letters_raises(self):
        with pytest.raises(ValidationError):
            _make_xhttp(uplink_chunk_size="abc")

    def test_invalid_string_double_dash_raises(self):
        with pytest.raises(ValidationError):
            _make_xhttp(uplink_chunk_size="100--200")

    def test_invalid_string_leading_dash_raises(self):
        with pytest.raises(ValidationError):
            _make_xhttp(uplink_chunk_size="-100")

    def test_too_many_digits_raises(self):
        # 17 digits should fail the 1-16 digit constraint
        with pytest.raises(ValidationError):
            _make_xhttp(uplink_chunk_size="12345678901234567")


class TestXHttpSettingsOtherFieldsUnchanged:
    """Smoke test: other fields on XHttpSettings are unaffected."""

    def test_default_construction(self):
        s = XHttpSettings()
        assert s.uplink_chunk_size is None

    def test_sc_max_each_post_bytes_still_accepts_range_string(self):
        s = _make_xhttp(sc_max_each_post_bytes="100-200")
        assert s.sc_max_each_post_bytes == "100-200"
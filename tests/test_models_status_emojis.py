"""Tests for app/models/status_emojis.py — new STATUS_EMOJIS constant."""
import pytest

from app.models.status_emojis import STATUS_EMOJIS


class TestStatusEmojis:
    """Verify STATUS_EMOJIS has the expected structure and values."""

    EXPECTED_KEYS = {"active", "expired", "limited", "disabled", "on_hold"}

    def test_is_dict(self):
        assert isinstance(STATUS_EMOJIS, dict)

    def test_contains_all_expected_keys(self):
        assert set(STATUS_EMOJIS.keys()) == self.EXPECTED_KEYS

    def test_active_emoji(self):
        assert STATUS_EMOJIS["active"] == "✅"

    def test_expired_emoji(self):
        assert STATUS_EMOJIS["expired"] == "⌛️"

    def test_limited_emoji(self):
        assert STATUS_EMOJIS["limited"] == "🪫"

    def test_disabled_emoji(self):
        assert STATUS_EMOJIS["disabled"] == "❌"

    def test_on_hold_emoji(self):
        assert STATUS_EMOJIS["on_hold"] == "🔌"

    def test_all_values_are_non_empty_strings(self):
        for key, value in STATUS_EMOJIS.items():
            assert isinstance(value, str), f"Value for '{key}' is not a string"
            assert value, f"Value for '{key}' is empty"

    def test_no_extra_keys(self):
        assert len(STATUS_EMOJIS) == len(self.EXPECTED_KEYS)

    def test_key_not_present_returns_keyerror(self):
        with pytest.raises(KeyError):
            _ = STATUS_EMOJIS["unknown_status"]
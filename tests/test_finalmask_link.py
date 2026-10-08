import json

from app.core.hosts import _normalize_finalmask_link


def test_finalmask_link_supports_stable_fragment_fields_without_mutating_input():
    settings = {"tcp": [{"type": "fragment", "settings": {"lengths": ["100-200"], "delays": ["10-20"]}}]}

    result = json.loads(_normalize_finalmask_link(settings))

    assert result["tcp"][0]["settings"] == {
        "lengths": ["100-200"],
        "delays": ["10-20"],
        "length": "100-200",
        "delay": "10-20",
    }
    assert "length" not in settings["tcp"][0]["settings"]


def test_finalmask_link_normalizes_string_payload():
    payload = '{"tcp":[{"type":"fragment","settings":{"lengths":["100-200"],"delays":["10-20"]}}]}'

    result = json.loads(_normalize_finalmask_link(payload))

    assert result["tcp"][0]["settings"]["length"] == "100-200"
    assert result["tcp"][0]["settings"]["delay"] == "10-20"

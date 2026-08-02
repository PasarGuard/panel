import pytest
from pydantic import ValidationError

from app.models.settings import Subscription
from app.subscription.share import _format_external_configs


def test_external_configs_are_trimmed_formatted_and_keep_order():
    configs = _format_external_configs(
        "  vless://legacy.example#{USERNAME}  \n\nss://legacy.example  ",
        "trojan://{USERNAME}@external.example\n  hysteria2://external.example  ",
        format_variables={"USERNAME": "alice"},
    )

    assert configs == [
        "vless://legacy.example#alice",
        "ss://legacy.example",
        "trojan://alice@external.example",
        "hysteria2://external.example",
    ]


def test_external_configs_leave_invalid_format_strings_unchanged():
    configs = _format_external_configs(
        "vless://external.example#{unclosed",
        format_variables={"USERNAME": "alice"},
    )

    assert configs == ["vless://external.example#{unclosed"]


def test_subscription_external_config_has_a_size_limit():
    with pytest.raises(ValidationError):
        Subscription(rules=[], external_config="x" * 65536)

import re

from app.models.subscription_defaults import build_default_subscription_rules


def _match(rules: list[dict[str, str]], user_agent: str) -> str | None:
    return next((rule["target"] for rule in rules if re.search(rule["pattern"], user_agent)), None)


def test_default_subscription_rules_match_builtin_clients():
    rules = build_default_subscription_rules()

    assert _match(rules, "InHive/1.0") == "xray"
    assert _match(rules, "v2rayN/7.15") == "links_base64"
    assert _match(rules, "unknown-client/1.0") == "links_base64"


def test_custom_json_flags_override_catch_all_rule():
    rules = build_default_subscription_rules(use_custom_json_for_v2rayn=True)

    assert _match(rules, "v2rayN/7.15") == "xray"
    assert _match(rules, "v2rayNG/1.10") == "links_base64"

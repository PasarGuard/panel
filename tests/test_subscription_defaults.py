from app.models.subscription_defaults import build_default_subscription_rules


def test_default_subscription_rules_keep_link_clients_on_base64():
    rules = build_default_subscription_rules()

    assert {"pattern": r"^[Ii]n[Hh]ive", "target": "xray"} in rules
    assert rules[-1] == {"pattern": r"^.*", "target": "links_base64"}
    assert not any("2rayN" in rule["pattern"] for rule in rules)


def test_default_subscription_rules_honor_custom_json_flags():
    rules = build_default_subscription_rules(use_custom_json_for_v2rayng=True, use_custom_json_for_happ=True)

    assert rules[-2] == {
        "pattern": r"^([Vv]2rayNG|[Hh]app)",
        "target": "xray",
    }


def test_custom_json_default_enables_all_supported_clients():
    rules = build_default_subscription_rules(use_custom_json_default=True)
    xray_rule = rules[-2]

    assert xray_rule["target"] == "xray"
    assert "[Vv]2rayNG" in xray_rule["pattern"]
    assert "[Vv]2rayN" in xray_rule["pattern"]
    assert "[Ss]treisand" in xray_rule["pattern"]
    assert "[Hh]app" in xray_rule["pattern"]
    assert r"[Kk]tor\-client" in xray_rule["pattern"]

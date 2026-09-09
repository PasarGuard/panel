from typing import TypedDict


class SubscriptionRuleDefault(TypedDict):
    pattern: str
    target: str


def build_default_subscription_rules(
    *,
    use_custom_json_default: bool = False,
    use_custom_json_for_v2rayn: bool = False,
    use_custom_json_for_v2rayng: bool = False,
    use_custom_json_for_streisand: bool = False,
    use_custom_json_for_happ: bool = False,
    use_custom_json_for_npvtunnel: bool = False,
) -> list[SubscriptionRuleDefault]:
    """Build the environment-aware subscription rules used for new installs and resets."""
    rules: list[SubscriptionRuleDefault] = [
        {
            "pattern": (
                r"^(?:FlClashX?|Flowvy|[Cc]lash(?:-(?:[Vv]erge|nyanpasu)|X [Mm]eta|-?[Mm]eta)|"
                r"[Kk]oala-[Cc]lash|[Mm](?:urge|ihomo)|prizrak-box|clash\.meta)"
            ),
            "target": "clash_meta",
        },
        {"pattern": r"^([Cc]lash|[Ss]tash)", "target": "clash"},
        {
            "pattern": r"^(SFA|SFI|SFM|SFT|[Kk]aring|[Hh]iddify[Nn]ext)|.*[Ss]ing[\-b]?ox.*",
            "target": "sing_box",
        },
        {"pattern": r"^(SS|SSR|SSD|SSS|Outline|Shadowsocks|SSconf)", "target": "outline"},
        {"pattern": r"^[Ii]n[Hh]ive", "target": "xray"},
        {"pattern": r"^.*", "target": "links_base64"},
    ]

    custom_json_patterns: list[str] = []
    candidates = (
        (use_custom_json_for_v2rayng, "[Vv]2rayNG"),
        (use_custom_json_for_v2rayn, "[Vv]2rayN"),
        (use_custom_json_for_streisand, "[Ss]treisand"),
        (use_custom_json_for_happ, "[Hh]app"),
        (use_custom_json_for_npvtunnel, r"[Kk]tor\-client"),
    )
    for enabled, pattern in candidates:
        if use_custom_json_default or enabled:
            custom_json_patterns.append(pattern)

    if custom_json_patterns:
        rules.insert(-1, {"pattern": rf"^({'|'.join(custom_json_patterns)})", "target": "xray"})

    return rules

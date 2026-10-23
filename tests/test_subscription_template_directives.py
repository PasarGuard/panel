import json

import pytest
import yaml
from pydantic import ValidationError

from app.models.subscription import SubscriptionInboundData, TLSConfig, WebSocketTransportConfig
from app.subscription.clash import ClashMetaConfiguration
from app.subscription.singbox import SingBoxConfiguration
from app.subscription.template_directives import (
    HostCandidate,
    HostSelector,
    validate_clash_template_directives,
    validate_singbox_template_directives,
    validate_xray_template_directive,
)
from app.subscription.xray import XrayConfiguration

USER_ID = "11111111-1111-1111-1111-111111111111"
SETTINGS = {"id": USER_ID}

# (host id, remark, inbound tag, address)
HOSTS = [
    (1, "DE-1 \U0001f1e9\U0001f1ea", "de-in", "de1.example.com"),
    (2, "DE-2", "de-in", "de2.example.com"),
    (3, "NL-1", "nl-in", "nl1.example.com"),
    (4, "US-1", "us-ws", "us1.example.com"),
]

# HOSTS with fragment settings, so every xray host also gets a freedom "dialer" helper outbound
FRAGMENT_HOSTS = [
    (*host, {"fragment_settings": {"xray": {"packets": "tlshello", "length": "100-200", "interval": "10-20"}}})
    for host in HOSTS
]

XRAY_TEMPLATE = {
    "inbounds": [{"tag": "socks", "protocol": "socks", "port": 10808}],
    "outbounds": [
        {"tag": "direct", "protocol": "freedom"},
        {"tag": "block", "protocol": "blackhole"},
    ],
    "routing": {"rules": [{"type": "field", "network": "tcp,udp", "outboundTag": "proxy"}]},
}

SINGBOX_TEMPLATE = {
    "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen_port": 2080}],
    "outbounds": [
        {"type": "selector", "tag": "select", "outbounds": ["auto"]},
        {"type": "urltest", "tag": "auto", "outbounds": []},
        {"type": "direct", "tag": "direct"},
    ],
}

CLASH_TEMPLATE = """mode: rule
{{ conf | except("proxy-groups", "mode", "rules") | yaml }}
proxy-groups:
- name: 'PROXY'
  type: 'select'
  proxies:
  - 'Fastest'
  {{ proxy_remarks | yaml | indent(2) }}
- name: 'Fastest'
  type: 'url-test'
  proxies:
  {{ proxy_remarks | yaml | indent(2) }}
rules:
  - MATCH,PROXY
"""

# Output of the generators before directives existed (upstream v5.5.0) for HOSTS and the templates above.
XRAY_GOLDEN = (
    '[{"inbounds":[{"tag":"socks","protocol":"socks","port":10808}],"outbounds":[{"protocol":"vless","tag'
    '":"proxy","settings":{"vnext":[{"address":"de1.example.com","port":443,"users":[{"id":"11111111-1111'
    '-1111-1111-111111111111","encryption":"none"}]}]},"streamSettings":{"network":"ws","security":"tls",'
    '"tlsSettings":{"serverName":"sni.example.com","fingerprint":"chrome"},"wsSettings":{"path":"/ws","ho'
    'st":"cdn.example.com"}}},{"tag":"direct","protocol":"freedom"},{"tag":"block","protocol":"blackhole"'
    '}],"routing":{"rules":[{"type":"field","network":"tcp,udp","outboundTag":"proxy"}]},"remarks":"DE-1 '
    '🇩🇪"},{"inbounds":[{"tag":"socks","protocol":"socks","port":10808}],"outbounds":[{"protocol":"vless",'
    '"tag":"proxy","settings":{"vnext":[{"address":"de2.example.com","port":443,"users":[{"id":"11111111-'
    '1111-1111-1111-111111111111","encryption":"none"}]}]},"streamSettings":{"network":"ws","security":"t'
    'ls","tlsSettings":{"serverName":"sni.example.com","fingerprint":"chrome"},"wsSettings":{"path":"/ws"'
    ',"host":"cdn.example.com"}}},{"tag":"direct","protocol":"freedom"},{"tag":"block","protocol":"blackh'
    'ole"}],"routing":{"rules":[{"type":"field","network":"tcp,udp","outboundTag":"proxy"}]},"remarks":"D'
    'E-2"},{"inbounds":[{"tag":"socks","protocol":"socks","port":10808}],"outbounds":[{"protocol":"vless"'
    ',"tag":"proxy","settings":{"vnext":[{"address":"nl1.example.com","port":443,"users":[{"id":"11111111'
    '-1111-1111-1111-111111111111","encryption":"none"}]}]},"streamSettings":{"network":"ws","security":"'
    'tls","tlsSettings":{"serverName":"sni.example.com","fingerprint":"chrome"},"wsSettings":{"path":"/ws'
    '","host":"cdn.example.com"}}},{"tag":"direct","protocol":"freedom"},{"tag":"block","protocol":"black'
    'hole"}],"routing":{"rules":[{"type":"field","network":"tcp,udp","outboundTag":"proxy"}]},"remarks":"'
    'NL-1"},{"inbounds":[{"tag":"socks","protocol":"socks","port":10808}],"outbounds":[{"protocol":"vless'
    '","tag":"proxy","settings":{"vnext":[{"address":"us1.example.com","port":443,"users":[{"id":"1111111'
    '1-1111-1111-1111-111111111111","encryption":"none"}]}]},"streamSettings":{"network":"ws","security":'
    '"tls","tlsSettings":{"serverName":"sni.example.com","fingerprint":"chrome"},"wsSettings":{"path":"/w'
    's","host":"cdn.example.com"}}},{"tag":"direct","protocol":"freedom"},{"tag":"block","protocol":"blac'
    'khole"}],"routing":{"rules":[{"type":"field","network":"tcp,udp","outboundTag":"proxy"}]},"remarks":'
    '"US-1"}]'
)


def _host(remark: str, inbound_tag: str, address: str, **extra) -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark=remark,
        inbound_tag=inbound_tag,
        protocol="vless",
        address=address,
        port=443,
        network="ws",
        tls_config=TLSConfig(tls="tls", sni="sni.example.com", fingerprint="chrome"),
        transport_config=WebSocketTransportConfig(path="/ws", host="cdn.example.com"),
        priority=0,
        **extra,
    )


def _fill(conf, hosts=HOSTS, **add_kwargs):
    for host_id, remark, inbound_tag, address, *extra in hosts:
        inbound = _host(remark, inbound_tag, address, **(extra[0] if extra else {}))
        conf.add(remark, address, inbound, SETTINGS, host_id=host_id, **add_kwargs)
    return conf


def _xray(template: dict, **kwargs) -> list[dict]:
    return json.loads(_fill(XrayConfiguration(xray_template_content=json.dumps(template), **kwargs)).render())


def _singbox(template: dict) -> dict:
    return json.loads(_fill(SingBoxConfiguration(singbox_template_content=json.dumps(template))).render())


def _assert_user_outbound(outbound: dict, address: str) -> None:
    vnext = outbound["settings"]["vnext"][0]
    assert outbound["protocol"] == "vless"
    assert vnext["address"] == address
    assert vnext["users"][0]["id"] == USER_ID
    assert outbound["streamSettings"]["wsSettings"]["path"] == "/ws"


# ---------- selector ----------


def _selected(selector: dict) -> list[int]:
    model = HostSelector.model_validate(selector)
    return [
        host_id
        for host_id, remark, inbound_tag, _ in HOSTS
        if model.matches(HostCandidate(host_id=host_id, inbound_tag=inbound_tag, remark=remark))
    ]


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        ({}, [1, 2, 3, 4]),
        ({"inbound_tags": ["de-in", "us-ws"]}, [1, 2, 4]),
        ({"inbound_tag_regex": "-in$"}, [1, 2, 3]),
        ({"remark_regex": "^DE"}, [1, 2]),
        ({"remark_regex": "\U0001f1e9\U0001f1ea"}, [1]),
        ({"host_ids": [2, 4]}, [2, 4]),
        ({"inbound_tags": ["de-in"], "host_ids": [2, 3]}, [2]),
        ({"inbound_tag_regex": "in", "remark_regex": "1", "host_ids": [1, 3, 4]}, [1, 3]),
        ({"inbound_tags": []}, []),
    ],
)
def test_selector_variants(selector, expected):
    assert _selected(selector) == expected


@pytest.mark.parametrize(
    "selector",
    [{"remark_regex": "("}, {"inbound_tag_regex": "[a-"}, {"tags": ["premium"]}, {"unknown": 1}],
)
def test_selector_rejects_invalid(selector):
    with pytest.raises(ValidationError):
        HostSelector.model_validate(selector)


# ---------- xray ----------


def test_xray_without_directive_is_unchanged():
    assert _fill(XrayConfiguration(xray_template_content=json.dumps(XRAY_TEMPLATE))).render() == XRAY_GOLDEN


def test_xray_directive_without_inject_is_stripped_and_output_unchanged():
    template = {**XRAY_TEMPLATE, "pasarguard": {"mode": "per_host"}}
    rendered = _fill(XrayConfiguration(xray_template_content=json.dumps(template))).render()
    assert rendered == XRAY_GOLDEN


def test_xray_per_host_inject_adds_other_selected_hosts_with_unique_tags():
    template = {
        **XRAY_TEMPLATE,
        "pasarguard": {"inject": [{"select": {"inbound_tags": ["de-in"]}, "tag_prefix": "de"}]},
    }
    configs = _xray(template)

    assert len(configs) == 4
    assert all("pasarguard" not in config for config in configs)

    de1, _, nl1, _ = configs
    assert de1["remarks"] == HOSTS[0][1]
    assert [o["tag"] for o in de1["outbounds"]] == ["proxy", "de-1", "direct", "block"]
    _assert_user_outbound(de1["outbounds"][0], "de1.example.com")
    _assert_user_outbound(de1["outbounds"][1], "de2.example.com")

    assert nl1["remarks"] == "NL-1"
    assert [o["tag"] for o in nl1["outbounds"]] == ["proxy", "de-1", "de-2", "direct", "block"]
    _assert_user_outbound(nl1["outbounds"][0], "nl1.example.com")
    _assert_user_outbound(nl1["outbounds"][1], "de1.example.com")
    _assert_user_outbound(nl1["outbounds"][2], "de2.example.com")
    assert nl1["routing"] == XRAY_TEMPLATE["routing"]


def test_xray_inject_tags_from_remark_are_sanitized_and_deduplicated():
    hosts = [(1, "Same name", "a", "a.example.com"), (2, "Same name", "b", "b.example.com")] + HOSTS[:1]
    template = {**XRAY_TEMPLATE, "pasarguard": {"mode": "single", "inject": [{"tag_from": "remark"}]}}
    conf = _fill(XrayConfiguration(xray_template_content=json.dumps(template)), hosts=hosts)
    (config,) = json.loads(conf.render())

    assert [o["tag"] for o in config["outbounds"]] == ["Same-name", "Same-name-2", "DE-1", "direct", "block"]


def test_xray_inject_tag_does_not_clash_with_template_outbounds():
    template = {
        **XRAY_TEMPLATE,
        "outbounds": [{"tag": "eu-1", "protocol": "freedom"}],
        "pasarguard": {"mode": "single", "inject": [{"select": {"host_ids": [1, 2]}, "tag_prefix": "eu"}]},
    }
    (config,) = _xray(template)
    assert [o["tag"] for o in config["outbounds"]] == ["eu-1-2", "eu-2", "eu-1"]


def test_xray_single_mode_produces_one_config_with_all_injected_hosts():
    template = {
        **XRAY_TEMPLATE,
        "remarks": "Template title",
        "routing": {
            "balancers": [{"tag": "all", "selector": ["proxy-"], "strategy": {"type": "leastPing"}}],
            "rules": [{"type": "field", "network": "tcp,udp", "balancerTag": "all"}],
        },
        "burstObservatory": {"subjectSelector": ["proxy-"]},
        "pasarguard": {"mode": "single", "inject": [{}]},
    }
    configs = _xray(template, single_remarks="My subscription")

    assert len(configs) == 1
    (config,) = configs
    assert "pasarguard" not in config
    assert config["remarks"] == "My subscription"
    assert [o["tag"] for o in config["outbounds"]] == ["proxy-1", "proxy-2", "proxy-3", "proxy-4", "direct", "block"]
    for outbound, (_, _, _, address) in zip(config["outbounds"], HOSTS):
        _assert_user_outbound(outbound, address)
    assert config["routing"] == template["routing"]
    assert config["burstObservatory"] == template["burstObservatory"]


def test_xray_single_mode_remarks_fallbacks():
    template = {**XRAY_TEMPLATE, "remarks": "Template title", "pasarguard": {"mode": "single", "inject": [{}]}}
    assert _xray(template)[0]["remarks"] == "Template title"

    template.pop("remarks")
    assert _xray(template)[0]["remarks"] == "PasarGuard"


def test_xray_single_mode_with_no_hosts_renders_empty_list():
    template = {**XRAY_TEMPLATE, "pasarguard": {"mode": "single", "inject": [{}]}}
    assert XrayConfiguration(xray_template_content=json.dumps(template)).render() == "[]"


def test_xray_inject_renames_fragment_dialer_helpers():
    template = {**XRAY_TEMPLATE, "pasarguard": {"mode": "single", "inject": [{}]}}
    conf = XrayConfiguration(xray_template_content=json.dumps(template))
    fragment = {"xray": {"packets": "tlshello", "length": "100-200", "interval": "10-20"}}
    for host_id, remark, inbound_tag, address in HOSTS[:2]:
        conf.add(
            remark, address, _host(remark, inbound_tag, address, fragment_settings=fragment), SETTINGS, host_id=host_id
        )
    (config,) = json.loads(conf.render())

    tags = [o["tag"] for o in config["outbounds"]]
    assert tags == ["proxy-1", "dialer-proxy-1", "proxy-2", "dialer-proxy-2", "direct", "block"]
    assert config["outbounds"][0]["streamSettings"]["sockopt"]["dialerProxy"] == "dialer-proxy-1"
    assert config["outbounds"][2]["streamSettings"]["sockopt"]["dialerProxy"] == "dialer-proxy-2"
    assert config["outbounds"][1]["settings"]["fragment"]["packets"] == "tlshello"


@pytest.mark.parametrize(
    "directive",
    [
        {"mode": "single", "inject": [{}]},
        {"mode": "single", "inject": [{"tag_prefix": "dialer"}]},
        {"mode": "single", "inject": [{"tag_prefix": "d"}, {"tag_prefix": "_", "tag_from": "remark"}]},
        {"mode": "single", "inject": [{"tag_from": "remark"}]},
        {"inject": [{}]},
        {"inject": [{"tag_prefix": "di"}]},
        {"inject": [{"select": {"remark_regex": "^DE"}, "tag_prefix": "de"}, {"tag_prefix": "fallback"}]},
    ],
)
def test_xray_helper_outbounds_never_match_injected_tag_prefixes(directive):
    """Balancers/observatories select by tag prefix: a direct freedom dialer must never fall under one."""
    template = {**XRAY_TEMPLATE, "pasarguard": directive}
    configs = json.loads(_fill(XrayConfiguration(xray_template_content=json.dumps(template)), FRAGMENT_HOSTS).render())
    assert configs

    injects = directive["inject"]
    prefixes = {inject.get("tag_prefix") or "proxy" for inject in injects if inject.get("tag_from") != "remark"}
    prefixes |= {inject["tag_prefix"] for inject in injects if inject.get("tag_prefix")}
    for config in configs:
        outbounds = config["outbounds"][: -len(XRAY_TEMPLATE["outbounds"])]
        tags = [outbound["tag"] for outbound in outbounds]
        assert len(tags) == len(set(tags))
        mains = [outbound for outbound in outbounds if outbound["protocol"] == "vless"]
        helpers = [outbound for outbound in outbounds if outbound["protocol"] == "freedom"]
        assert helpers and len(helpers) == len(mains)
        injected_main_tags = {outbound["tag"] for outbound in mains} - {"proxy"}
        for helper in helpers:
            assert not any(helper["tag"].startswith(prefix) for prefix in prefixes | injected_main_tags), helper["tag"]
        # every main points at its own, existing helper
        dialers = [outbound["streamSettings"]["sockopt"]["dialerProxy"] for outbound in mains]
        assert sorted(dialers) == sorted(helper["tag"] for helper in helpers)


def test_xray_per_host_own_helper_keeps_upstream_tag_when_it_does_not_collide():
    template = {**XRAY_TEMPLATE, "pasarguard": {"inject": [{"tag_prefix": "pool"}]}}
    configs = json.loads(_fill(XrayConfiguration(xray_template_content=json.dumps(template)), FRAGMENT_HOSTS).render())
    own_main, own_helper = configs[0]["outbounds"][:2]
    assert (own_main["tag"], own_helper["tag"]) == ("proxy", "dialer")
    assert own_main["streamSettings"]["sockopt"]["dialerProxy"] == "dialer"


def test_xray_without_directive_keeps_upstream_helper_tags():
    conf = XrayConfiguration(xray_template_content=json.dumps(XRAY_TEMPLATE))
    configs = json.loads(_fill(conf, FRAGMENT_HOSTS).render())
    assert all([o["tag"] for o in config["outbounds"]] == ["proxy", "dialer", "direct", "block"] for config in configs)


def test_xray_host_level_template_directive_uses_host_ids():
    host_template = {
        **XRAY_TEMPLATE,
        "pasarguard": {"inject": [{"select": {"host_ids": [4]}, "tag_prefix": "backup"}]},
    }
    conf = XrayConfiguration(xray_template_content=json.dumps(XRAY_TEMPLATE))
    for host_id, remark, inbound_tag, address in HOSTS:
        content = json.dumps(host_template) if host_id == 3 else None
        conf.add(
            remark, address, _host(remark, inbound_tag, address), SETTINGS, template_content=content, host_id=host_id
        )
    configs = json.loads(conf.render())

    assert [o["tag"] for o in configs[0]["outbounds"]] == ["proxy", "direct", "block"]
    assert [o["tag"] for o in configs[2]["outbounds"]] == ["proxy", "backup-1", "direct", "block"]
    _assert_user_outbound(configs[2]["outbounds"][1], "us1.example.com")


def test_xray_invalid_directive_at_render_is_ignored():
    template = {**XRAY_TEMPLATE, "pasarguard": {"mode": "bogus"}}
    assert _fill(XrayConfiguration(xray_template_content=json.dumps(template))).render() == XRAY_GOLDEN


@pytest.mark.parametrize(
    "directive",
    [
        {"mode": "bogus"},
        {"mode": "single"},
        {"inject": [{"select": {"remark_regex": "("}}]},
        {"inject": [{"tag_from": "name"}]},
        {"extra": True},
    ],
)
def test_xray_template_validation_rejects_bad_directive(directive):
    with pytest.raises(ValueError):
        validate_xray_template_directive({**XRAY_TEMPLATE, "pasarguard": directive})


# ---------- sing-box ----------


def test_singbox_without_directive_keeps_filling_every_group():
    config = _singbox(SINGBOX_TEMPLATE)
    remarks = [remark for _, remark, _, _ in HOSTS]
    assert config["outbounds"][0]["outbounds"] == ["auto", *remarks]
    assert config["outbounds"][1]["outbounds"] == remarks


def test_singbox_group_directive_selects_proxies_and_keeps_author_entries():
    template = json.loads(json.dumps(SINGBOX_TEMPLATE))
    template["outbounds"][0]["outbounds"] = ["auto", "direct", "NL-1"]
    template["outbounds"][0]["pasarguard"] = {"select": {"remark_regex": "^(NL|US)"}}
    template["outbounds"][1]["pasarguard"] = {"include_proxies": True, "select": {"inbound_tags": ["de-in"]}}
    template["outbounds"].append({"type": "urltest", "tag": "rest", "outbounds": []})
    config = _singbox(template)

    select, auto, _, rest = config["outbounds"][:4]
    assert select["outbounds"] == ["auto", "direct", "NL-1", "US-1"]
    assert auto["outbounds"] == [HOSTS[0][1], "DE-2"]
    # A group without the directive still gets every proxy
    assert rest["outbounds"] == [remark for _, remark, _, _ in HOSTS]
    assert all("pasarguard" not in outbound for outbound in config["outbounds"])


def test_singbox_include_proxies_false_leaves_group_as_written():
    template = json.loads(json.dumps(SINGBOX_TEMPLATE))
    template["outbounds"][0]["outbounds"] = ["auto", "direct"]
    template["outbounds"][0]["pasarguard"] = {"include_proxies": False}
    config = _singbox(template)

    assert config["outbounds"][0] == {"type": "selector", "tag": "select", "outbounds": ["auto", "direct"]}


@pytest.mark.parametrize("include_proxies", [True, False])
def test_singbox_empty_directive_group_falls_back_to_all_servers(include_proxies):
    template = json.loads(json.dumps(SINGBOX_TEMPLATE))
    template["outbounds"][0]["outbounds"] = []
    template["outbounds"][0]["pasarguard"] = {"include_proxies": include_proxies, "select": {"host_ids": [999]}}
    template["outbounds"][1]["pasarguard"] = {
        "include_proxies": include_proxies,
        "select": {"remark_regex": "^nothing-matches"},
    }
    config = _singbox(template)
    remarks = [remark for _, remark, _, _ in HOSTS]

    assert config["outbounds"][0]["outbounds"] == ["auto", *remarks]
    assert config["outbounds"][1]["outbounds"] == remarks
    assert [o["tag"] for o in config["outbounds"] if o["type"] == "direct"] == ["direct"]


def test_singbox_empty_directive_group_without_any_servers():
    template = json.loads(json.dumps(SINGBOX_TEMPLATE))
    template["outbounds"][1]["pasarguard"] = {"select": {"host_ids": [999]}}
    config = json.loads(SingBoxConfiguration(singbox_template_content=json.dumps(template)).render())
    # Never fall back to a direct outbound: an empty group keeps the config from silently bypassing the VPN
    assert config["outbounds"][1]["outbounds"] == []

    template["outbounds"] = template["outbounds"][:2]
    config = json.loads(SingBoxConfiguration(singbox_template_content=json.dumps(template)).render())
    assert config["outbounds"][1]["outbounds"] == []
    assert [o["type"] for o in config["outbounds"]] == ["selector", "urltest"]


def test_singbox_non_empty_directive_group_gets_no_fallback():
    template = json.loads(json.dumps(SINGBOX_TEMPLATE))
    template["outbounds"][1]["pasarguard"] = {"select": {"host_ids": [3]}}
    config = _singbox(template)

    assert config["outbounds"][1]["outbounds"] == ["NL-1"]
    assert [o["tag"] for o in config["outbounds"] if o["type"] == "direct"] == ["direct"]


def test_singbox_template_validation():
    good = json.loads(json.dumps(SINGBOX_TEMPLATE))
    good["outbounds"][1]["pasarguard"] = {"select": {"inbound_tag_regex": "^de"}}
    validate_singbox_template_directives(good)

    bad_regex = json.loads(json.dumps(SINGBOX_TEMPLATE))
    bad_regex["outbounds"][1]["pasarguard"] = {"select": {"remark_regex": "(["}}
    with pytest.raises(ValueError):
        validate_singbox_template_directives(bad_regex)

    wrong_place = json.loads(json.dumps(SINGBOX_TEMPLATE))
    wrong_place["outbounds"][2]["pasarguard"] = {}
    with pytest.raises(ValueError):
        validate_singbox_template_directives(wrong_place)


# ---------- clash ----------


def _clash(template: str) -> str:
    return _fill(ClashMetaConfiguration(clash_template_content=template)).render()


def test_clash_without_directive_returns_rendered_template_untouched():
    conf = _fill(ClashMetaConfiguration(clash_template_content=CLASH_TEMPLATE))
    from app.templates import render_template_string

    expected = render_template_string(CLASH_TEMPLATE, {"conf": conf.data, "proxy_remarks": conf.proxy_remarks})
    assert conf.render() == expected


def test_clash_group_directive_appends_matching_proxies_without_duplicates():
    template = CLASH_TEMPLATE.replace(
        "rules:\n",
        "- name: 'Germany'\n"
        "  type: 'url-test'\n"
        "  proxies:\n"
        "  - 'Fastest'\n"
        "  - 'DE-2'\n"
        "  pasarguard:\n"
        "    include-proxies: true\n"
        "    select:\n"
        "      remark_regex: '^DE'\n"
        "- name: 'Manual'\n"
        "  type: 'select'\n"
        "  proxies: ['PROXY']\n"
        "  pasarguard: {include_proxies: false}\n"
        "rules:\n",
    )
    data = yaml.safe_load(_clash(template))
    groups = {group["name"]: group for group in data["proxy-groups"]}

    assert groups["Germany"]["proxies"] == ["Fastest", "DE-2", HOSTS[0][1]]
    assert groups["Manual"]["proxies"] == ["PROXY"]
    assert groups["Fastest"]["proxies"] == [remark for _, remark, _, _ in HOSTS]
    assert all("pasarguard" not in group for group in data["proxy-groups"])
    assert len(data["proxies"]) == 4


def test_clash_invalid_regex_at_render_matches_nothing():
    template = CLASH_TEMPLATE.replace(
        "rules:\n",
        "- name: 'Broken'\n  type: 'select'\n  proxies: ['PROXY']\n  pasarguard: {select: {remark_regex: '('}}\nrules:\n",
    )
    data = yaml.safe_load(_clash(template))
    broken = next(group for group in data["proxy-groups"] if group["name"] == "Broken")
    assert broken == {"name": "Broken", "type": "select", "proxies": ["PROXY"]}


def test_clash_template_validation():
    validate_clash_template_directives({"proxy-groups": [{"name": "a", "pasarguard": {"include-proxies": True}}]})
    with pytest.raises(ValueError):
        validate_clash_template_directives({"proxy-groups": [{"name": "a", "pasarguard": {"select": {"bad": 1}}}]})


def test_clash_empty_directive_group_falls_back_to_all_servers():
    template = CLASH_TEMPLATE.replace(
        "rules:\n",
        "- name: 'Nothing'\n  type: 'url-test'\n  proxies: []\n  pasarguard: {select: {host_ids: [999]}}\n"
        "- name: 'Written'\n  type: 'select'\n  pasarguard: {include-proxies: false}\n"
        "- name: 'Provider'\n  type: 'select'\n  use: ['remote']\n  pasarguard: {select: {host_ids: [999]}}\n"
        "- name: 'Picked'\n  type: 'select'\n  proxies: []\n  pasarguard: {select: {host_ids: [3]}}\n"
        "rules:\n",
    )
    groups = {group["name"]: group for group in yaml.safe_load(_clash(template))["proxy-groups"]}
    remarks = [remark for _, remark, _, _ in HOSTS]

    assert groups["Nothing"]["proxies"] == remarks
    assert groups["Written"]["proxies"] == remarks
    assert groups["Provider"]["proxies"] == []
    assert groups["Picked"]["proxies"] == ["NL-1"]


def test_clash_empty_directive_group_without_any_servers_rejects():
    template = "proxies: []\nproxy-groups:\n- name: 'Nothing'\n  type: 'select'\n  pasarguard: {}\nrules: []\n"
    data = yaml.safe_load(ClashMetaConfiguration(clash_template_content=template).render())
    assert data["proxy-groups"] == [{"name": "Nothing", "type": "select", "proxies": ["REJECT"]}]

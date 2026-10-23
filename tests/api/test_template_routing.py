import json

import pytest
from fastapi import status

from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_client_template,
    create_core,
    create_group,
    create_hosts_for_inbounds,
    create_user,
    delete_client_template,
    delete_core,
    delete_group,
    delete_user,
    unique_name,
)

XRAY_CONTENT = {
    "inbounds": [{"tag": "socks", "protocol": "socks", "port": 10808}],
    "outbounds": [{"tag": "direct", "protocol": "freedom", "settings": {}}],
}
SINGBOX_CONTENT = {
    "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen_port": 2080}],
    "outbounds": [{"type": "urltest", "tag": "auto", "outbounds": []}, {"type": "direct", "tag": "direct"}],
}


def _xray_template(access_token: str, marker: str, **directive) -> dict:
    content = {**XRAY_CONTENT, "outbounds": [{"tag": marker, "protocol": "freedom", "settings": {}}]}
    if directive:
        content["pasarguard"] = directive
    return create_client_template(
        access_token,
        name=unique_name("rule_xray"),
        template_type="xray_subscription",
        content=json.dumps(content),
    )


def _get_subscription_settings(access_token: str) -> dict:
    response = client.get("/api/settings", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    return response.json()["subscription"]


def _put_rules(access_token: str, original: dict, rules: list[dict]):
    return client.put(
        "/api/settings",
        headers=auth_headers(access_token),
        json={"subscription": {**original, "rules": [*rules, *original["rules"]]}},
    )


def _restore(access_token: str, original: dict) -> None:
    response = client.put("/api/settings", headers=auth_headers(access_token), json={"subscription": original})
    assert response.status_code == status.HTTP_200_OK


def test_settings_reject_unknown_and_mismatched_rule_templates(access_token):
    original = _get_subscription_settings(access_token)
    singbox_template = create_client_template(
        access_token,
        name=unique_name("rule_singbox"),
        template_type="singbox_subscription",
        content=json.dumps(SINGBOX_CONTENT),
    )
    try:
        unknown = _put_rules(
            access_token, original, [{"pattern": "^RuleTpl", "target": "xray", "template_id": 999_999_999}]
        )
        assert unknown.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not exist" in unknown.json()["detail"]

        mismatch = _put_rules(
            access_token, original, [{"pattern": "^RuleTpl", "target": "xray", "template_id": singbox_template["id"]}]
        )
        assert mismatch.status_code == status.HTTP_400_BAD_REQUEST
        assert "xray_subscription" in mismatch.json()["detail"]

        not_templated = _put_rules(
            access_token, original, [{"pattern": "^RuleTpl", "target": "links", "template_id": singbox_template["id"]}]
        )
        assert not_templated.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        accepted = _put_rules(
            access_token,
            original,
            [{"pattern": "^RuleTpl", "target": "sing_box", "template_id": singbox_template["id"]}],
        )
        assert accepted.status_code == status.HTTP_200_OK
        assert accepted.json()["subscription"]["rules"][0]["template_id"] == singbox_template["id"]
        # Rules without template_id keep working and read back as null
        assert accepted.json()["subscription"]["rules"][1]["template_id"] is None
    finally:
        _restore(access_token, original)
        delete_client_template(access_token, singbox_template["id"])


def test_deleting_template_used_by_rule_is_refused(access_token):
    original = _get_subscription_settings(access_token)
    template = _xray_template(access_token, "delete-guard-marker")
    try:
        assert (
            _put_rules(
                access_token, original, [{"pattern": "^DeleteGuard", "target": "xray", "template_id": template["id"]}]
            ).status_code
            == status.HTTP_200_OK
        )

        response = client.delete(f"/api/client_template/{template['id']}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "^DeleteGuard" in response.json()["detail"]

        bulk = client.post(
            "/api/client_templates/bulk/delete",
            headers=auth_headers(access_token),
            json={"ids": [template["id"]]},
        )
        assert bulk.status_code == status.HTTP_409_CONFLICT

        _restore(access_token, original)
        response = client.delete(f"/api/client_template/{template['id']}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        template = None
    finally:
        _restore(access_token, original)
        if template:
            delete_client_template(access_token, template["id"])


def test_subscription_uses_rule_template_only_for_matching_client(access_token, mock_settings):
    original = _get_subscription_settings(access_token)
    original_mock_rules = mock_settings["subscription"]["rules"]
    rule_template = _xray_template(access_token, "rule-template-marker")
    single_template = _xray_template(
        access_token, "single-template-marker", mode="single", inject=[{"tag_prefix": "pool"}]
    )
    core = create_core(access_token)
    group = create_group(access_token, name=unique_name("rule_tpl_group"))
    hosts = create_hosts_for_inbounds(access_token)
    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("rule_tpl_user")})
    rules = [
        {"pattern": "^RuleTemplateClient$", "target": "xray", "template_id": rule_template["id"]},
        {"pattern": "^SingleTemplateClient$", "target": "xray", "template_id": single_template["id"]},
        {"pattern": "^DefaultTemplateClient$", "target": "xray"},
    ]
    try:
        response = _put_rules(access_token, original, rules)
        assert response.status_code == status.HTTP_200_OK
        # tests/api serve subscriptions from a static settings snapshot (conftest.mock_settings); mirror the PUT there.
        mock_settings["subscription"]["rules"] = [*rules, *original_mock_rules]

        with_rule = client.get(user["subscription_url"], headers={"User-Agent": "RuleTemplateClient"})
        assert with_rule.status_code == status.HTTP_200_OK
        rule_configs = with_rule.json()
        assert rule_configs
        assert all(config["outbounds"][-1]["tag"] == "rule-template-marker" for config in rule_configs)

        # Same user, another client right after: must not get the cached output of the first one
        default = client.get(user["subscription_url"], headers={"User-Agent": "DefaultTemplateClient"})
        assert default.status_code == status.HTTP_200_OK
        assert "rule-template-marker" not in default.text
        assert len(default.json()) == len(rule_configs)

        single = client.get(user["subscription_url"], headers={"User-Agent": "SingleTemplateClient"})
        assert single.status_code == status.HTTP_200_OK
        (config,) = single.json()
        assert "pasarguard" not in config
        tags = [outbound["tag"] for outbound in config["outbounds"]]
        assert tags[-1] == "single-template-marker"
        assert len([tag for tag in tags if tag.startswith("pool-")]) == len(rule_configs)
    finally:
        mock_settings["subscription"]["rules"] = original_mock_rules
        _restore(access_token, original)
        delete_user(access_token, user["username"])
        for host in hosts:
            client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])
        delete_client_template(access_token, rule_template["id"])
        delete_client_template(access_token, single_template["id"])


@pytest.mark.parametrize(
    ("template_type", "content"),
    [
        ("xray_subscription", {**XRAY_CONTENT, "pasarguard": {"mode": "bogus"}}),
        ("xray_subscription", {**XRAY_CONTENT, "pasarguard": {"mode": "single"}}),
        ("xray_subscription", {**XRAY_CONTENT, "pasarguard": {"inject": [{"select": {"remark_regex": "(["}}]}}),
        (
            "singbox_subscription",
            {
                **SINGBOX_CONTENT,
                "outbounds": [
                    {"type": "urltest", "tag": "auto", "outbounds": [], "pasarguard": {"select": {"remark_regex": "("}}}
                ],
            },
        ),
        (
            "singbox_subscription",
            {**SINGBOX_CONTENT, "outbounds": [{"type": "direct", "tag": "direct", "pasarguard": {}}]},
        ),
        (
            "clash_subscription",
            (
                "proxies: []\nproxy-groups:\n- name: a\n  type: select\n  proxies: []\n"
                "  pasarguard: {select: {inbound_tag_regex: '('}}\nrules: []\n"
            ),
        ),
    ],
)
def test_client_template_rejects_invalid_directive(access_token, template_type, content):
    payload = {
        "name": unique_name("bad_directive"),
        "template_type": template_type,
        "content": content if isinstance(content, str) else json.dumps(content),
    }
    response = client.post("/api/client_template", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid template content" in response.json()["detail"]


def test_client_template_modify_rejects_invalid_directive(access_token):
    template = _xray_template(access_token, "modify-marker", inject=[{"select": {"inbound_tags": ["a"]}}])
    try:
        response = client.put(
            f"/api/client_template/{template['id']}",
            headers=auth_headers(access_token),
            json={"content": json.dumps({**XRAY_CONTENT, "pasarguard": {"inject": [{"tag_from": "nope"}]}})},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    finally:
        delete_client_template(access_token, template["id"])

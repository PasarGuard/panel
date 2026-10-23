"""Subscriptions of users attached to a client profile."""

import asyncio
import base64
import json

import pytest
from fastapi import status

from app.settings import refresh_caches
from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_client_template,
    create_core,
    create_group,
    create_user,
    delete_client_template,
    delete_core,
    delete_group,
    delete_user,
    unique_name,
)


def _xray_template(access_token: str, marker: str) -> dict:
    return create_client_template(
        access_token,
        name=unique_name(marker),
        template_type="xray_subscription",
        content=json.dumps(
            {
                "inbounds": [{"tag": "placeholder", "protocol": "vmess", "settings": {"clients": []}}],
                "outbounds": [{"tag": marker, "protocol": "freedom", "settings": {}}],
            }
        ),
    )


def _singbox_template(access_token: str, marker: str) -> dict:
    return create_client_template(
        access_token,
        name=unique_name(marker),
        template_type="singbox_subscription",
        content=json.dumps(
            {
                "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 2080}],
                "outbounds": [{"type": "direct", "tag": marker}],
            }
        ),
    )


def _clash_template(access_token: str, marker: str) -> dict:
    return create_client_template(
        access_token,
        name=unique_name(marker),
        template_type="clash_subscription",
        content=(
            "mode: rule\n"
            f"profile-marker: {marker}\n"
            '{{ conf | except("proxy-groups", "port", "mode", "rules") | yaml }}\n'
            "proxy-groups: []\n"
            "rules:\n"
            "- MATCH,DIRECT\n"
        ),
    )


def _decode_title(value: str) -> str:
    assert value.startswith("base64:")
    return base64.b64decode(value.removeprefix("base64:")).decode()


class Env:
    def __init__(self, access_token: str):
        self.token = access_token
        self.headers = auth_headers(access_token)
        self.inbound = unique_name("profile_inbound")
        self.core = create_core(
            access_token,
            config={
                "log": {"loglevel": "info"},
                "inbounds": [
                    {
                        "tag": self.inbound,
                        "listen": "0.0.0.0",
                        "port": 2087,
                        "protocol": "vmess",
                        "settings": {"clients": []},
                        "streamSettings": {"network": "ws", "wsSettings": {"path": "/p"}, "security": "none"},
                    }
                ],
                "outbounds": [{"protocol": "freedom", "tag": "DIRECT"}],
            },
            fallbacks=[],
        )
        self.group = create_group(access_token, inbound_tags=[self.inbound])
        self.host_ids: list[int] = []
        self.template_ids: list[int] = []
        self.profile_ids: list[int] = []
        self.usernames: list[str] = []

    def add_host(self, remark: str = "Host {USERNAME}", **extra) -> dict:
        response = client.post(
            "/api/host",
            headers=self.headers,
            json={
                "remark": remark,
                "address": ["198.51.100.70"],
                "port": 443,
                "sni": ["profile.example.com"],
                "inbound_tag": self.inbound,
                "priority": len(self.host_ids) + 1,
                **extra,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text
        self.host_ids.append(response.json()["id"])
        return response.json()

    def template(self, factory, marker: str) -> dict:
        template = factory(self.token, marker)
        self.template_ids.append(template["id"])
        return template

    def profile(self, **payload) -> dict:
        payload.setdefault("name", unique_name("sub_profile"))
        response = client.post("/api/client_profile", headers=self.headers, json=payload)
        assert response.status_code == status.HTTP_201_CREATED, response.text
        self.profile_ids.append(response.json()["id"])
        return response.json()

    def user(self, profile: dict | None = None) -> dict:
        payload = {"client_profile_id": profile["id"]} if profile else {}
        user = create_user(self.token, group_ids=[self.group["id"]], payload=payload)
        self.usernames.append(user["username"])
        return user

    def cleanup(self) -> None:
        for username in self.usernames:
            delete_user(self.token, username)
        for host_id in self.host_ids:
            client.delete(f"/api/host/{host_id}", headers=self.headers)
        for profile_id in self.profile_ids:
            client.delete(f"/api/client_profile/{profile_id}", headers=self.headers)
        for template_id in self.template_ids:
            delete_client_template(self.token, template_id)
        delete_group(self.token, self.group["id"])
        delete_core(self.token, self.core["id"])


@pytest.fixture
def env(access_token):
    environment = Env(access_token)
    yield environment
    environment.cleanup()


def _xray_tags(response) -> set[str]:
    assert response.status_code == status.HTTP_200_OK, response.text
    return {outbound["tag"] for config in response.json() for outbound in config["outbounds"]}


def test_profile_templates_reach_each_format(env):
    env.add_host()
    xray = env.template(_xray_template, "profile-xray-marker")
    singbox = env.template(_singbox_template, "profile-singbox-marker")
    clash = env.template(_clash_template, "profile-clash-marker")
    profile = env.profile(
        templates={
            "xray_subscription": xray["id"],
            "singbox_subscription": singbox["id"],
            "clash_subscription": clash["id"],
        }
    )
    with_profile = env.user(profile)
    without_profile = env.user()

    assert "profile-xray-marker" in _xray_tags(client.get(f"{with_profile['subscription_url']}/xray"))
    assert "profile-singbox-marker" in client.get(f"{with_profile['subscription_url']}/sing_box").text
    for clash_format in ("clash", "clash_meta"):
        assert "profile-clash-marker" in client.get(f"{with_profile['subscription_url']}/{clash_format}").text

    # A user without a profile keeps the global default templates
    assert "profile-xray-marker" not in _xray_tags(client.get(f"{without_profile['subscription_url']}/xray"))
    assert "profile-singbox-marker" not in client.get(f"{without_profile['subscription_url']}/sing_box").text
    assert "profile-clash-marker" not in client.get(f"{without_profile['subscription_url']}/clash").text


def test_host_xray_template_beats_profile_template(env):
    host_template = env.template(_xray_template, "host-xray-marker")
    profile_template = env.template(_xray_template, "profile-xray-marker")
    env.add_host(subscription_templates={"xray": host_template["id"]})
    user = env.user(env.profile(templates={"xray_subscription": profile_template["id"]}))

    tags = _xray_tags(client.get(f"{user['subscription_url']}/xray"))
    assert "host-xray-marker" in tags
    assert "profile-xray-marker" not in tags


def test_profile_settings_override_headers(env):
    env.add_host(remark="{BRAND}-host")
    profile = env.profile(
        settings={
            "profile_title": "{BRAND} for {USERNAME}",
            "support_url": "https://support.example.com",
            "announce": "Hello from {BRAND}",
            "update_interval": 6,
            "response_headers": {"X-Profile": "{BRAND}"},
            "remove_response_headers": ["Announce-URL", "subscription-USERINFO"],
            "custom_variables": [{"key": "BRAND", "value": "Acme"}],
        }
    )
    user = env.user(profile)
    plain = env.user()

    response = client.get(f"{user['subscription_url']}/links")
    assert response.status_code == status.HTTP_200_OK
    assert _decode_title(response.headers["profile-title"]) == f"Acme for {user['username']}"
    assert response.headers["support-url"] == "https://support.example.com"
    assert _decode_title(response.headers["announce"]) == "Hello from Acme"
    assert response.headers["profile-update-interval"] == "6"
    assert response.headers["x-profile"] == "Acme"
    assert "announce-url" not in response.headers
    assert "subscription-userinfo" not in response.headers
    # The profile variable is available to host remarks
    xray_configs = client.get(f"{user['subscription_url']}/xray").json()
    assert [config["remarks"] for config in xray_configs] == ["Acme-host"]

    # Same headers on the user-agent based endpoint
    response = client.get(user["subscription_url"], headers={"User-Agent": "v2rayNG/1.8"})
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["profile-update-interval"] == "6"
    assert response.headers["x-profile"] == "Acme"
    assert "subscription-userinfo" not in response.headers

    response = client.get(f"{plain['subscription_url']}/links")
    assert _decode_title(response.headers["profile-title"]) == "Subscription"
    assert response.headers["support-url"] == "https://t.me/"
    assert response.headers["profile-update-interval"] == "12"
    assert "x-profile" not in response.headers
    assert "subscription-userinfo" in response.headers


def test_profile_change_applies_to_next_subscription(env):
    env.add_host()
    first = env.template(_xray_template, "first-xray-marker")
    second = env.template(_xray_template, "second-xray-marker")
    profile = env.profile(templates={"xray_subscription": first["id"]}, settings={"update_interval": 6})
    user = env.user(profile)

    response = client.get(f"{user['subscription_url']}/xray")
    assert "first-xray-marker" in _xray_tags(response)
    assert response.headers["profile-update-interval"] == "6"

    response = client.put(
        f"/api/client_profile/{profile['id']}",
        headers=env.headers,
        json={"templates": {"xray_subscription": second["id"]}, "settings": {"update_interval": 3}},
    )
    assert response.status_code == status.HTTP_200_OK

    # No restart and no manual cache clear: the profile change invalidates cached configs
    response = client.get(f"{user['subscription_url']}/xray")
    tags = _xray_tags(response)
    assert "second-xray-marker" in tags
    assert "first-xray-marker" not in tags
    assert response.headers["profile-update-interval"] == "3"

    # Moving the user off the profile also changes the next response
    client.put(f"/api/user/{user['username']}", headers=env.headers, json={"client_profile_id": None})
    response = client.get(f"{user['subscription_url']}/xray")
    assert "second-xray-marker" not in _xray_tags(response)
    assert response.headers["profile-update-interval"] == "12"


def test_client_template_content_change_applies_to_next_subscription(env):
    env.add_host()
    template = env.template(_xray_template, "before-edit-marker")
    user = env.user(env.profile(templates={"xray_subscription": template["id"]}))
    assert "before-edit-marker" in _xray_tags(client.get(f"{user['subscription_url']}/xray"))

    content = json.dumps(
        {
            "inbounds": [{"tag": "placeholder", "protocol": "vmess", "settings": {"clients": []}}],
            "outbounds": [{"tag": "after-edit-marker", "protocol": "freedom", "settings": {}}],
        }
    )
    response = client.put(f"/api/client_template/{template['id']}", headers=env.headers, json={"content": content})
    assert response.status_code == status.HTTP_200_OK, response.text

    # The profile only stores the template id: editing the template is picked up by its users
    tags = _xray_tags(client.get(f"{user['subscription_url']}/xray"))
    assert "after-edit-marker" in tags
    assert "before-edit-marker" not in tags


def test_rule_response_headers_beat_profile_removed_headers(env, mock_settings):
    rule = {
        "pattern": r"^ProfileRuleHeaderClient$",
        "target": "links",
        "response_headers": {"x-rule": "rule-{USERNAME}", "support-url": "https://rule.example.com"},
    }
    rules = mock_settings["subscription"]["rules"]
    rules.insert(0, rule)
    # Subscription settings are cached; drop what earlier tests loaded
    asyncio.run(refresh_caches())
    try:
        env.add_host()
        profile = env.profile(
            settings={
                "support_url": "https://profile.example.com",
                "response_headers": {"X-Rule": "profile"},
                "remove_response_headers": ["X-Rule", "Support-URL"],
            }
        )
        user = env.user(profile)

        # Rule headers are applied last, after the profile's add/remove
        response = client.get(user["subscription_url"], headers={"User-Agent": "ProfileRuleHeaderClient"})
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["x-rule"] == f"rule-{user['username']}"
        assert response.headers["support-url"] == "https://rule.example.com"

        # A client that matches no header rule still gets the profile's removals
        response = client.get(user["subscription_url"], headers={"User-Agent": "v2rayNG/1.8"})
        assert response.status_code == status.HTTP_200_OK
        assert "x-rule" not in response.headers
        assert "support-url" not in response.headers
    finally:
        rules.remove(rule)
        asyncio.run(refresh_caches())


def test_subscription_info_hides_client_profile_id(env):
    env.add_host()
    user = env.user(env.profile())
    response = client.get(f"{user['subscription_url']}/info")
    assert response.status_code == status.HTTP_200_OK
    assert "client_profile_id" not in response.json()
    assert "client_profile" not in response.json()

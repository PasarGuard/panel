import asyncio
import json
from base64 import b64decode

import pytest
from fastapi import status

from app.db.models import ClientTemplate
from app.settings import refresh_caches
from app.subscription.client_templates import refresh_client_templates_cache
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_client_template,
    create_core,
    create_group,
    create_hosts_for_inbounds,
    create_user,
    delete_core,
    delete_group,
    delete_user,
    unique_name,
)

ROUTING_PREFIX = "happ://routing/onadd/"


def happ_profile(**overrides) -> dict:
    profile = {
        "Name": "PasarGuard",
        "GlobalProxy": "true",
        "RemoteDNSType": "DoH",
        "RemoteDNSDomain": "https://cloudflare-dns.com/dns-query",
        "RemoteDNSIP": "1.1.1.1",
        "DomesticDNSType": "DoU",
        "DomesticDNSDomain": "",
        "DomesticDNSIP": "8.8.8.8",
        "DnsHosts": {"cloudflare-dns.com": "1.1.1.1"},
        "DirectSites": ["geosite:private"],
        "DirectIp": ["10.0.0.0/8", "192.168.0.0/16"],
        "ProxySites": [],
        "ProxyIp": [],
        "BlockSites": [],
        "BlockIp": [],
        "DomainStrategy": "IPIfNonMatch",
        "FakeDNS": "false",
    }
    profile.update(overrides)
    return profile


def create_happ_template(access_token: str, profile: dict | None = None) -> dict:
    return create_client_template(
        access_token,
        name=unique_name("happ_routing"),
        template_type="happ_routing",
        content=json.dumps(profile or happ_profile(), ensure_ascii=False),
    )


def post_happ_template(access_token: str, content: str, **extra):
    return client.post(
        "/api/client_template",
        headers=auth_headers(access_token),
        json={"name": unique_name("happ_bad"), "template_type": "happ_routing", "content": content, **extra},
    )


def delete_template(access_token: str, template_id: int):
    return client.delete(f"/api/client_template/{template_id}", headers=auth_headers(access_token))


def get_subscription_settings(access_token: str) -> dict:
    response = client.get("/api/settings", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    return response.json()["subscription"]


def put_subscription_settings(access_token: str, subscription: dict):
    return client.put("/api/settings", headers=auth_headers(access_token), json={"subscription": subscription})


def refresh_runtime_caches() -> None:
    """Runtime reads the mocked settings snapshot and template cache; drop cached copies after editing them."""

    async def _refresh():
        await refresh_caches()
        await refresh_client_templates_cache()

    asyncio.run(_refresh())


def decode_routing_link(link: str) -> dict:
    assert link.startswith(ROUTING_PREFIX)
    return json.loads(b64decode(link.removeprefix(ROUTING_PREFIX)).decode("utf-8"))


# --- template validation ---


def test_happ_routing_template_valid_content_is_stored_and_not_default(access_token):
    profile = happ_profile(Name="Тест", FutureHappField={"kept": True})
    created = create_happ_template(access_token, profile)

    assert created["template_type"] == "happ_routing"
    assert created["is_default"] is False
    assert created["is_system"] is False
    # unknown keys are kept as-is
    assert json.loads(created["content"])["FutureHappField"] == {"kept": True}

    assert delete_template(access_token, created["id"]).status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not json", "valid JSON"),
        ("[]", "JSON object"),
        (json.dumps({k: v for k, v in happ_profile().items() if k != "Name"}), "Name"),
        (json.dumps(happ_profile(Name="  ")), "Name"),
        (json.dumps(happ_profile(GlobalProxy=True)), "GlobalProxy"),
        (json.dumps(happ_profile(FakeDNS="yes")), "FakeDNS"),
        (json.dumps(happ_profile(RemoteDNSIP=1)), "RemoteDNSIP"),
        (json.dumps(happ_profile(DomainStrategy="Fast")), "DomainStrategy"),
        (json.dumps(happ_profile(DirectSites="geosite:ru")), "DirectSites"),
        (json.dumps(happ_profile(BlockIp=[1, 2])), "BlockIp"),
        (json.dumps(happ_profile(DnsHosts=["1.1.1.1"])), "DnsHosts"),
        (json.dumps(happ_profile(DnsHosts={"a": 1})), "DnsHosts"),
    ],
    ids=lambda value: value if len(value) < 20 else None,
)
def test_happ_routing_template_rejects_invalid_content(access_token, content, message):
    response = post_happ_template(access_token, content)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert message in response.json()["detail"]


def test_happ_routing_template_update_validates_and_rejects_default(access_token):
    created = create_happ_template(access_token)
    try:
        response = client.put(
            f"/api/client_template/{created['id']}",
            headers=auth_headers(access_token),
            json={"content": json.dumps(happ_profile(ProxyIp="geoip:ru"))},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "ProxyIp" in response.json()["detail"]

        response = client.put(
            f"/api/client_template/{created['id']}",
            headers=auth_headers(access_token),
            json={"is_default": True},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.put(
            f"/api/client_template/{created['id']}",
            headers=auth_headers(access_token),
            json={"content": json.dumps(happ_profile(Name="Updated"))},
        )
        assert response.status_code == status.HTTP_200_OK
        assert json.loads(response.json()["content"])["Name"] == "Updated"
    finally:
        delete_template(access_token, created["id"])


def test_happ_routing_template_create_rejects_default(access_token):
    response = post_happ_template(access_token, json.dumps(happ_profile()), is_default=True)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# --- settings ---


def test_settings_rule_happ_routing_template_validation(access_token):
    original_subscription = get_subscription_settings(access_token)
    happ_template = create_happ_template(access_token)
    other_template = create_client_template(
        access_token, name=unique_name("tmpl_ua"), template_type="user_agent", content='{"list": ["ua"]}'
    )

    def with_rule(**rule_fields) -> dict:
        rule = {"pattern": "^Happ/", "target": "links_base64", **rule_fields}
        return {**original_subscription, "rules": [rule, *original_subscription["rules"]]}

    try:
        response = put_subscription_settings(access_token, with_rule(happ_routing_template_id=happ_template["id"]))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["subscription"]["rules"][0]["happ_routing_template_id"] == happ_template["id"]

        response = put_subscription_settings(access_token, with_rule(happ_routing_template_id=other_template["id"]))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not a Happ routing template" in response.json()["detail"]

        response = put_subscription_settings(access_token, with_rule(happ_routing_template_id=99_999_999))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not found" in response.json()["detail"]

        response = put_subscription_settings(
            access_token,
            with_rule(happ_routing_template_id=happ_template["id"], response_headers={"Routing": "happ://x"}),
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "routing" in response.text

        # a manual routing header alone is still allowed
        response = put_subscription_settings(access_token, with_rule(response_headers={"routing": "happ://x"}))
        assert response.status_code == status.HTTP_200_OK
    finally:
        assert put_subscription_settings(access_token, original_subscription).status_code == status.HTTP_200_OK
        delete_template(access_token, happ_template["id"])
        delete_template(access_token, other_template["id"])


# --- deletion ---


def test_delete_referenced_happ_routing_template_conflicts(access_token):
    original_subscription = get_subscription_settings(access_token)
    referenced = create_happ_template(access_token)
    unused = create_happ_template(access_token)
    subscription = {
        **original_subscription,
        "rules": [
            {"pattern": "^Happ/", "target": "links_base64", "happ_routing_template_id": referenced["id"]},
            *original_subscription["rules"],
        ],
    }
    assert put_subscription_settings(access_token, subscription).status_code == status.HTTP_200_OK

    try:
        response = delete_template(access_token, referenced["id"])
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["detail"] == (
            f'Client template "{referenced["name"]}" is used by subscription rules: ^Happ/. '
            "Remove it from those rules first."
        )

        response = client.post(
            "/api/client_templates/bulk/delete",
            headers=auth_headers(access_token),
            json={"ids": [referenced["id"], unused["id"]]},
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "^Happ/" in response.json()["detail"]
        # nothing was deleted
        assert (
            client.get(f"/api/client_template/{unused['id']}", headers=auth_headers(access_token)).status_code
            == status.HTTP_200_OK
        )
    finally:
        assert put_subscription_settings(access_token, original_subscription).status_code == status.HTTP_200_OK

    # once no rule references them, they can be deleted (including the last one of the type)
    response = client.post(
        "/api/client_templates/bulk/delete",
        headers=auth_headers(access_token),
        json={"ids": [referenced["id"], unused["id"]]},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["count"] == 2


# --- delivery ---


@pytest.fixture
def happ_subscription(access_token, mock_settings):
    """A user, a happ_routing template and a ^Happ rule (the runtime settings snapshot is mocked)."""
    core = create_core(access_token)
    group = create_group(access_token, name=unique_name("happ_group"))
    hosts = create_hosts_for_inbounds(access_token)
    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("happ_routing_user")})
    profile = happ_profile(Name="PasarGuard Ру")
    template = create_happ_template(access_token, profile)

    sub = mock_settings["subscription"]
    original_rules = sub["rules"]
    original_placement = sub.get("header_placement", "header")
    sub["rules"] = [
        {"pattern": "^Happ/", "target": "links_base64", "happ_routing_template_id": template["id"]},
        {"pattern": "^HappPlain/", "target": "links", "happ_routing_template_id": template["id"]},
        {"pattern": "^HappClash/", "target": "clash_meta", "happ_routing_template_id": template["id"]},
        *original_rules,
    ]
    refresh_runtime_caches()

    yield {"user": user, "template": template, "profile": profile, "settings": sub}

    sub["rules"] = original_rules
    sub["header_placement"] = original_placement
    refresh_runtime_caches()
    delete_template(access_token, template["id"])
    delete_user(access_token, user["username"])
    for host in hosts:
        client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
    delete_group(access_token, group["id"])
    delete_core(access_token, core["id"])


def test_happ_rule_sends_routing_header(happ_subscription):
    url = happ_subscription["user"]["subscription_url"]
    response = client.get(url, headers={"User-Agent": "Happ/3.0"})
    assert response.status_code == status.HTTP_200_OK
    assert decode_routing_link(response.headers["routing"]) == happ_subscription["profile"]
    assert ROUTING_PREFIX not in b64decode(response.text).decode()

    # HEAD returns the same header
    head = client.head(url, headers={"User-Agent": "Happ/3.0"})
    assert head.status_code == status.HTTP_200_OK
    assert head.headers["routing"] == response.headers["routing"]

    # clash keeps the header even with body placement: a bare link is not valid YAML
    happ_subscription["settings"]["header_placement"] = "body_start"
    refresh_runtime_caches()
    response = client.get(url, headers={"User-Agent": "HappClash/1.0"})
    assert response.status_code == status.HTTP_200_OK
    assert decode_routing_link(response.headers["routing"]) == happ_subscription["profile"]
    assert ROUTING_PREFIX not in response.text


def test_other_rule_gets_no_routing(happ_subscription):
    response = client.get(happ_subscription["user"]["subscription_url"], headers={"User-Agent": "v2rayNG/1.8"})
    assert response.status_code == status.HTTP_200_OK
    assert "routing" not in response.headers
    assert ROUTING_PREFIX not in b64decode(response.text).decode()


@pytest.mark.parametrize("placement", ["body_start", "body_end"])
def test_happ_rule_body_placement_puts_link_first(happ_subscription, placement):
    happ_subscription["settings"]["header_placement"] = placement
    refresh_runtime_caches()
    url = happ_subscription["user"]["subscription_url"]

    # links_base64: the link goes inside the encoded list
    response = client.get(url, headers={"User-Agent": "Happ/3.0"})
    assert response.status_code == status.HTTP_200_OK
    assert "routing" not in response.headers
    lines = b64decode(response.text).decode().splitlines()
    assert decode_routing_link(lines[0]) == happ_subscription["profile"]
    assert not any(line.startswith("#routing") for line in lines)

    # plain links
    response = client.get(url, headers={"User-Agent": "HappPlain/3.0"})
    assert response.status_code == status.HTTP_200_OK
    assert "routing" not in response.headers
    lines = response.text.splitlines()
    assert decode_routing_link(lines[0]) == happ_subscription["profile"]
    assert sum(line.startswith(ROUTING_PREFIX) for line in lines) == 1


def test_deleted_or_broken_template_sends_subscription_without_routing(access_token, happ_subscription):
    url = happ_subscription["user"]["subscription_url"]
    template = happ_subscription["template"]

    # broken content written behind the API's back
    async def set_content(content: str):
        async with TestSession() as session:
            db_template = await session.get(ClientTemplate, template["id"])
            db_template.content = content
            await session.commit()

    asyncio.run(set_content('{"Name": ""}'))
    refresh_runtime_caches()
    response = client.get(url, headers={"User-Agent": "Happ/3.0"})
    assert response.status_code == status.HTTP_200_OK
    assert "routing" not in response.headers

    # the rule points to a template that no longer exists
    happ_subscription["settings"]["rules"][0]["happ_routing_template_id"] = 99_999_999
    refresh_runtime_caches()
    response = client.get(url, headers={"User-Agent": "Happ/3.0"})
    assert response.status_code == status.HTTP_200_OK
    assert "routing" not in response.headers
    assert b64decode(response.text).decode().strip()

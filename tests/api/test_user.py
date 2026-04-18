import io
import json
import zipfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlsplit

from fastapi import status

from app.models.settings import ConfigFormat, SubRule
from app.operation.subscription import SubscriptionOperation
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_client_template,
    create_core,
    create_group,
    create_hosts_for_inbounds,
    create_user,
    create_user_template,
    delete_client_template,
    delete_core,
    delete_group,
    delete_user,
    delete_user_template,
    unique_name,
)


def setup_groups(access_token: str, count: int = 1):
    core = create_core(access_token)
    groups = [create_group(access_token, name=unique_name(f"user_group_{idx}")) for idx in range(count)]
    return core, groups


def cleanup_groups(access_token: str, core: dict, groups: list[dict]):
    for group in groups:
        delete_group(access_token, group["id"])
    delete_core(access_token, core["id"])


def extract_wireguard_config_bodies(response) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        config_files = [name for name in zip_file.namelist() if name.endswith(".conf")]
        return [zip_file.read(name).decode("utf-8") for name in config_files]


def test_user_create_active(access_token):
    """Test that the user create active route is accessible."""
    core, groups = setup_groups(access_token, 2)
    group_ids = [group["id"] for group in groups]
    expire = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    user = create_user(
        access_token,
        group_ids=group_ids,
        payload={
            "username": unique_name("test_user_active"),
            "proxy_settings": {},
            "expire": expire.isoformat(),
            "data_limit": (1024 * 1024 * 1024 * 10),
            "data_limit_reset_strategy": "no_reset",
            "status": "active",
        },
    )
    try:
        assert user["data_limit"] == (1024 * 1024 * 1024 * 10)
        assert user["data_limit_reset_strategy"] == "no_reset"
        assert user["status"] == "active"
        assert user["proxy_settings"]["wireguard"]["private_key"]
        assert user["proxy_settings"]["wireguard"]["public_key"]
        assert set(user["group_ids"]) == set(group_ids)
        response_datetime = datetime.fromisoformat(user["expire"])
        expected_formatted = expire.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
        response_formatted = response_datetime.strftime("%Y-%m-%dT%H:%M:%S")
        assert response_formatted == expected_formatted
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_create_expire_timezone_offset_normalized_to_utc(access_token):
    """Expire with non-UTC offset should be persisted as the same UTC instant."""
    core, groups = setup_groups(access_token, 1)
    tehran_tz = timezone(timedelta(hours=3, minutes=30))
    expire_utc = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    expire_tehran = expire_utc.astimezone(tehran_tz)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={
            "username": unique_name("test_user_tz_expire"),
            "proxy_settings": {},
            "expire": expire_tehran.isoformat(),
            "status": "active",
        },
    )
    try:
        response_expire = datetime.fromisoformat(user["expire"])
        assert response_expire.astimezone(timezone.utc).replace(microsecond=0) == expire_utc
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_create_on_hold(access_token):
    """Test that the user create on hold route is accessible."""
    core, groups = setup_groups(access_token, 2)
    group_ids = [group["id"] for group in groups]
    expire = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    user = create_user(
        access_token,
        group_ids=group_ids,
        payload={
            "username": unique_name("test_user_on_hold"),
            "proxy_settings": {},
            "data_limit": (1024 * 1024 * 1024 * 10),
            "data_limit_reset_strategy": "no_reset",
            "status": "on_hold",
            "on_hold_timeout": expire.isoformat(),
            "on_hold_expire_duration": (86400 * 30),
        },
    )
    try:
        assert user["status"] == "on_hold"
        assert user["on_hold_expire_duration"] == (86400 * 30)
        assert set(user["group_ids"]) == set(group_ids)
        response_datetime = datetime.fromisoformat(user["on_hold_timeout"])
        expected_formatted = expire.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
        response_formatted = response_datetime.strftime("%Y-%m-%dT%H:%M:%S")
        assert response_formatted == expected_formatted
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_users_get(access_token):
    """Test that the users get route is accessible."""
    core, groups = setup_groups(access_token, 1)
    usernames = []
    try:
        for _ in range(2):
            user = create_user(
                access_token,
                group_ids=[groups[0]["id"]],
                payload={"username": unique_name("test_user_list")},
            )
            usernames.append(user["username"])

        response = client.get(
            "/api/users?load_sub=true",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        listed_usernames = {user["username"] for user in response.json()["users"]}
        for username in usernames:
            assert username in listed_usernames
    finally:
        for username in usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_user_subscriptions(access_token):
    """Test that the user subscriptions route is accessible."""
    user_subscription_formats = [
        "",
        "info",
        "usage",
        "apps",
        "sing_box",
        "clash_meta",
        "clash",
        "outline",
        "links",
        "links_base64",
        "wireguard",
        "xray",
    ]

    core, groups = setup_groups(access_token, 1)
    hosts = create_hosts_for_inbounds(access_token)
    user = create_user(
        access_token,
        group_ids=[group["id"] for group in groups],
        payload={"username": unique_name("test_user_subscriptions")},
    )
    try:
        for usf in user_subscription_formats:
            url = f"{user['subscription_url']}/{usf}"
            response = client.get(url, headers={"Accept": "text/html"} if usf == "" else None)
            assert response.status_code == status.HTTP_200_OK
    finally:
        delete_user(access_token, user["username"])
        for host in hosts:
            client.delete(f"/api/host/{host['id']}", headers={"Authorization": f"Bearer {access_token}"})
        cleanup_groups(access_token, core, groups)


def test_user_sub_update_user_agent(access_token):
    """Test that the user sub_update user_agent is accessible."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_agent")},
    )
    try:
        url = user["subscription_url"]
        user_agent = "v2rayNG/1.9.46 This is PasarGuard Test"
        client.get(url, headers={"User-Agent": user_agent})
        response = client.get(
            f"/api/user/{user['username']}/sub_update",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["updates"][0]["user_agent"] == user_agent
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_sub_update_user_agent_truncates_long_values(access_token):
    """Ensure overly long User-Agent strings are stored without failing."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_agent_truncate")},
    )
    try:
        url = user["subscription_url"]
        long_user_agent = "A" * 1000
        client.get(url, headers={"User-Agent": long_user_agent})
        response = client.get(
            f"/api/user/{user['username']}/sub_update",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["updates"][0]["user_agent"] == long_user_agent[:512]
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_subscription_applies_rule_response_headers(access_token):
    """Custom rule response headers should persist and keep subscription requests healthy."""
    settings_response = client.get("/api/settings", headers=auth_headers(access_token))
    assert settings_response.status_code == status.HTTP_200_OK
    original_subscription = settings_response.json()["subscription"]

    updated_subscription = {
        **original_subscription,
        "rules": [
            {
                "pattern": r"^PasarGuardRuleHeaderClient$",
                "target": "links",
                "response_headers": {
                    "x-subheader": "Hello {USERNAME}",
                    "profile-title": "Rule Profile {USERNAME}",
                },
            },
            *original_subscription["rules"],
        ],
    }

    update_response = client.put(
        "/api/settings",
        headers=auth_headers(access_token),
        json={"subscription": updated_subscription},
    )
    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.json()["subscription"]["rules"][0]["response_headers"]["x-subheader"] == "Hello {USERNAME}"

    core, groups = setup_groups(access_token, 1)
    hosts = create_hosts_for_inbounds(access_token)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_rule_response_headers")},
    )

    try:
        response = client.get(
            user["subscription_url"],
            headers={"User-Agent": "PasarGuardRuleHeaderClient"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.text
    finally:
        restore_response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"subscription": original_subscription},
        )
        assert restore_response.status_code == status.HTTP_200_OK
        delete_user(access_token, user["username"])
        for host in hosts:
            client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        cleanup_groups(access_token, core, groups)


def test_wireguard_subscription_outputs_are_consistent(access_token):
    interface_private_key, _ = generate_wireguard_keypair()
    interface_public_key = get_wireguard_public_key(interface_private_key)
    interface_name = unique_name("wg_subscription")
    host_remark = "WG {USERNAME}"
    endpoint = "198.51.100.10"

    core = create_core(
        access_token,
        name=unique_name("wireguard_subscription_core"),
        config={
            "interface_name": interface_name,
            "private_key": interface_private_key,
            "listen_port": 51820,
            "address": ["10.30.0.1/24"],
        },
        type="wg",
        fallbacks=[],
    )

    host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": host_remark,
            "address": [endpoint],
            "port": 51820,
            "inbound_tag": interface_name,
            "priority": 1,
        },
    )
    assert host_response.status_code == status.HTTP_201_CREATED
    host_id = host_response.json()["id"]

    group = create_group(access_token, name=unique_name("wg_subscription_group"), inbound_tags=[interface_name])
    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("wg_user")})
    expected_remark = f"WG {user['username']}"

    try:
        links_response = client.get(f"{user['subscription_url']}/links")
        wireguard_response = client.get(f"{user['subscription_url']}/wireguard")

        assert links_response.status_code == status.HTTP_200_OK
        assert wireguard_response.status_code == status.HTTP_200_OK

        link = links_response.text.strip()
        assert link.startswith("wireguard://")

        parsed = urlsplit(link)
        query = parse_qs(parsed.query)
        assert unquote(parsed.username or "") == user["proxy_settings"]["wireguard"]["private_key"]
        assert parsed.hostname == endpoint
        assert parsed.port == 51820
        assert query["publickey"] == [interface_public_key]
        assert "address" in query
        dynamic_address = query["address"][0]
        assert dynamic_address == user["proxy_settings"]["wireguard"]["peer_ips"][0]
        assert dynamic_address.endswith("/32")
        assert query["allowedips"] == ["0.0.0.0/0,::/0"]
        assert unquote(parsed.fragment) == expected_remark

        config_bodies = extract_wireguard_config_bodies(wireguard_response)
        assert len(config_bodies) == 1

        body = config_bodies[0]
        assert f"PrivateKey = {user['proxy_settings']['wireguard']['private_key']}" in body
        assert f"Address = {dynamic_address}" in body
        assert f"PublicKey = {interface_public_key}" in body
        assert "AllowedIPs = 0.0.0.0/0, ::/0" in body
        assert f"Endpoint = {endpoint}:51820" in body
    finally:
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_xray_subscription_includes_wireguard_outbound(access_token):
    interface_private_key, _ = generate_wireguard_keypair()
    interface_public_key = get_wireguard_public_key(interface_private_key)
    interface_name = unique_name("wg_xray_subscription")
    endpoint = "198.51.100.11"

    core = create_core(
        access_token,
        name=unique_name("wireguard_xray_core"),
        config={
            "interface_name": interface_name,
            "private_key": interface_private_key,
            "listen_port": 51820,
            "address": ["10.30.0.1/24"],
        },
        type="wg",
        fallbacks=[],
    )

    host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "WG Xray {USERNAME}",
            "address": [endpoint],
            "port": 51820,
            "inbound_tag": interface_name,
            "priority": 1,
            "wireguard_overrides": {
                "keepalive_seconds": 25,
            },
        },
    )
    assert host_response.status_code == status.HTTP_201_CREATED
    host_id = host_response.json()["id"]

    group = create_group(access_token, name=unique_name("wg_xray_group"), inbound_tags=[interface_name])
    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("wg_xray_user")})

    try:
        response = client.get(f"{user['subscription_url']}/xray")
        assert response.status_code == status.HTTP_200_OK

        configs = response.json()
        assert isinstance(configs, list)
        assert configs

        wireguard_outbounds = []
        for config in configs:
            for outbound in config.get("outbounds", []):
                if outbound.get("protocol") == "wireguard":
                    wireguard_outbounds.append(outbound)

        assert len(wireguard_outbounds) == 1

        outbound = wireguard_outbounds[0]
        assert outbound["tag"] == "proxy"
        settings = outbound["settings"]
        assert settings["secretKey"] == user["proxy_settings"]["wireguard"]["private_key"]
        assert settings["address"]
        assert settings["address"][0] == user["proxy_settings"]["wireguard"]["peer_ips"][0]
        assert settings["address"][0].startswith("10.")
        assert settings["address"][0].endswith("/32")
        assert settings["domainStrategy"] == "ForceIP"
        assert "mtu" not in settings
        peers = settings["peers"]
        assert len(peers) == 1
        peer = peers[0]
        assert peer["endpoint"] == f"{endpoint}:51820"
        assert peer["publicKey"] == interface_public_key
        assert peer["allowedIPs"] == ["0.0.0.0/0", "::/0"]
        assert peer["keepAlive"] == 25
    finally:
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_xray_subscription_uses_host_specific_template_override(access_token):
    # Use a unique inbound tag so other tests' hosts can't affect config count.
    unique_inbound = unique_name("xray_override_inbound")
    core = create_core(
        access_token,
        config={
            "log": {"loglevel": "info"},
            "inbounds": [
                {
                    "tag": unique_inbound,
                    "listen": "0.0.0.0",
                    "port": 2087,
                    "protocol": "vmess",
                    "settings": {"clients": []},
                    "streamSettings": {"network": "ws", "wsSettings": {"path": "/yourpath"}, "security": "none"},
                }
            ],
            "outbounds": [{"protocol": "freedom", "tag": "DIRECT"}, {"protocol": "blackhole", "tag": "BLOCK"}],
        },
        fallbacks=[],
    )
    inbound = unique_inbound
    override_template = create_client_template(
        access_token,
        name=unique_name("xray_host_override_template"),
        template_type="xray_subscription",
        content=json.dumps(
            {
                "log": {"loglevel": "warning"},
                "inbounds": [{"tag": "placeholder", "protocol": "vmess", "settings": {"clients": []}}],
                "outbounds": [{"tag": "template-marker", "protocol": "freedom", "settings": {}}],
            }
        ),
    )

    host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "Override Host {USERNAME}",
            "address": ["198.51.100.50"],
            "port": 443,
            "sni": ["override-template.example.com"],
            "inbound_tag": inbound,
            "priority": 1,
            "subscription_templates": {"xray": override_template["id"]},
        },
    )
    assert host_response.status_code == status.HTTP_201_CREATED
    host_id = host_response.json()["id"]

    group = create_group(access_token, name=unique_name("xray_override_group"), inbound_tags=[inbound])
    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("xray_override_user")})

    try:
        response = client.get(f"{user['subscription_url']}/xray")
        assert response.status_code == status.HTTP_200_OK

        configs = response.json()
        assert isinstance(configs, list)
        assert len(configs) == 1

        outbounds = configs[0]["outbounds"]
        assert any(outbound["tag"] == "template-marker" for outbound in outbounds)
    finally:
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_client_template(access_token, override_template["id"])
        delete_core(access_token, core["id"])


def test_xray_subscription_template_override_isolated_per_host(access_token):
    # Use a unique inbound tag so other tests' hosts can't affect config count.
    unique_inbound = unique_name("xray_isolated_inbound")
    core = create_core(
        access_token,
        config={
            "log": {"loglevel": "info"},
            "inbounds": [
                {
                    "tag": unique_inbound,
                    "listen": "0.0.0.0",
                    "port": 2087,
                    "protocol": "vmess",
                    "settings": {"clients": []},
                    "streamSettings": {"network": "ws", "wsSettings": {"path": "/yourpath"}, "security": "none"},
                }
            ],
            "outbounds": [{"protocol": "freedom", "tag": "DIRECT"}, {"protocol": "blackhole", "tag": "BLOCK"}],
        },
        fallbacks=[],
    )
    inbound = unique_inbound
    override_template = create_client_template(
        access_token,
        name=unique_name("xray_host_isolated_template"),
        template_type="xray_subscription",
        content=json.dumps(
            {
                "log": {"loglevel": "warning"},
                "inbounds": [{"tag": "placeholder", "protocol": "vmess", "settings": {"clients": []}}],
                "outbounds": [{"tag": "template-marker", "protocol": "freedom", "settings": {}}],
            }
        ),
    )

    first_host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "Host With Template {USERNAME}",
            "address": ["198.51.100.60"],
            "port": 443,
            "sni": ["host-template.example.com"],
            "inbound_tag": inbound,
            "priority": 1,
            "subscription_templates": {"xray": override_template["id"]},
        },
    )
    assert first_host_response.status_code == status.HTTP_201_CREATED
    first_host_id = first_host_response.json()["id"]

    second_host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "Host Without Template {USERNAME}",
            "address": ["198.51.100.61"],
            "port": 443,
            "sni": ["host-default.example.com"],
            "inbound_tag": inbound,
            "priority": 2,
        },
    )
    assert second_host_response.status_code == status.HTTP_201_CREATED
    second_host_id = second_host_response.json()["id"]

    group = create_group(access_token, name=unique_name("xray_isolated_group"), inbound_tags=[inbound])
    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("xray_isolated_user")})

    try:
        response = client.get(f"{user['subscription_url']}/xray")
        assert response.status_code == status.HTTP_200_OK

        configs = response.json()
        assert isinstance(configs, list)
        assert len(configs) == 2

        marker_count = 0
        for config in configs:
            outbounds = config.get("outbounds", [])
            if any(outbound.get("tag") == "template-marker" for outbound in outbounds):
                marker_count += 1

        assert marker_count == 1
    finally:
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        client.delete(f"/api/host/{first_host_id}", headers=auth_headers(access_token))
        client.delete(f"/api/host/{second_host_id}", headers=auth_headers(access_token))
        delete_client_template(access_token, override_template["id"])
        delete_core(access_token, core["id"])


def test_singbox_subscription_includes_wireguard_endpoint(access_token):
    interface_private_key, interface_public_key = generate_wireguard_keypair()
    pre_shared_key, _ = generate_wireguard_keypair()
    interface_name = unique_name("wg_singbox_subscription")
    endpoint = "198.51.100.12"

    core = create_core(
        access_token,
        name=unique_name("wireguard_singbox_core"),
        config={
            "interface_name": interface_name,
            "private_key": interface_private_key,
            "pre_shared_key": pre_shared_key,
            "listen_port": 51820,
            "address": ["10.30.0.1/24"],
        },
        type="wg",
        fallbacks=[],
    )

    host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "WG Singbox {USERNAME}",
            "address": [endpoint],
            "port": 10001,
            "inbound_tag": interface_name,
            "priority": 1,
            "wireguard_overrides": {
                "mtu": 1408,
                "reserved": "0,0,0",
                "keepalive_seconds": 30,
            },
        },
    )
    assert host_response.status_code == status.HTTP_201_CREATED
    host_id = host_response.json()["id"]

    group = create_group(access_token, name=unique_name("wg_singbox_group"), inbound_tags=[interface_name])
    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("wg_singbox_user")})
    expected_tag = f"WG Singbox {user['username']}"

    try:
        response = client.get(f"{user['subscription_url']}/sing_box")
        assert response.status_code == status.HTTP_200_OK

        config = response.json()
        wireguard_ep = next(
            (ep for ep in config.get("endpoints", []) if ep.get("type") == "wireguard"),
            None,
        )
        assert wireguard_ep is not None
        assert wireguard_ep["tag"] == expected_tag
        assert wireguard_ep["system"] is True
        assert wireguard_ep["name"] == "wg0"
        assert wireguard_ep["mtu"] == 1408
        assert wireguard_ep["address"]
        assert wireguard_ep["address"][0] == user["proxy_settings"]["wireguard"]["peer_ips"][0]
        assert wireguard_ep["address"][0].startswith("10.")
        assert wireguard_ep["address"][0].endswith("/32")
        assert wireguard_ep["private_key"] == user["proxy_settings"]["wireguard"]["private_key"]

        peers = wireguard_ep["peers"]
        assert len(peers) == 1
        peer = peers[0]
        assert peer["address"] == endpoint
        assert peer["port"] == 10001
        assert peer["public_key"] == interface_public_key
        assert peer["pre_shared_key"] == pre_shared_key
        assert peer["allowed_ips"] == ["0.0.0.0/0", "::/0"]
        assert peer["persistent_keepalive_interval"] == 30
        assert peer["reserved"] == [0, 0, 0]

        selector = next((outbound for outbound in config.get("outbounds", []) if outbound.get("tag") == "proxy"), None)
        if selector is not None:
            assert expected_tag in selector.get("outbounds", [])

        urltest = next(
            (outbound for outbound in config.get("outbounds", []) if outbound.get("type") == "urltest"), None
        )
        if urltest is not None:
            assert expected_tag in urltest.get("outbounds", [])
    finally:
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_user_can_be_assigned_to_multiple_wireguard_interfaces(access_token):
    first_private_key, _ = generate_wireguard_keypair()
    second_private_key, _ = generate_wireguard_keypair()
    first_interface = unique_name("wg_multi_a")
    second_interface = unique_name("wg_multi_b")
    first_endpoint = "198.51.100.21"
    second_endpoint = "198.51.100.22"

    first_core = create_core(
        access_token,
        name=unique_name("wireguard_multi_core_a"),
        config={
            "interface_name": first_interface,
            "private_key": first_private_key,
            "listen_port": 51820,
            "address": ["10.30.10.1/24"],
        },
        type="wg",
        fallbacks=[],
    )
    second_core = create_core(
        access_token,
        name=unique_name("wireguard_multi_core_b"),
        config={
            "interface_name": second_interface,
            "private_key": second_private_key,
            "listen_port": 51821,
            "address": ["10.40.10.1/24"],
        },
        type="wg",
        fallbacks=[],
    )

    first_host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "WG Multi A {USERNAME}",
            "address": [first_endpoint],
            "port": 51820,
            "inbound_tag": first_interface,
            "priority": 1,
        },
    )
    assert first_host_response.status_code == status.HTTP_201_CREATED
    first_host_id = first_host_response.json()["id"]

    second_host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "WG Multi B {USERNAME}",
            "address": [second_endpoint],
            "port": 51821,
            "inbound_tag": second_interface,
            "priority": 2,
        },
    )
    assert second_host_response.status_code == status.HTTP_201_CREATED
    second_host_id = second_host_response.json()["id"]

    group = create_group(
        access_token,
        name=unique_name("wg_multi_group"),
        inbound_tags=[first_interface, second_interface],
    )
    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("wg_multi_user")})

    try:
        # Single global-pool allocation; same peer address on every WG inbound
        peer_ips = user["proxy_settings"]["wireguard"]["peer_ips"]

        assert isinstance(peer_ips, list)
        assert len(peer_ips) == 1
        assert peer_ips[0].startswith("10.")
        assert peer_ips[0].endswith("/32")

        links_response = client.get(f"{user['subscription_url']}/links")
        assert links_response.status_code == status.HTTP_200_OK

        links_by_endpoint: dict[str, dict[str, list[str]]] = {}
        for line in links_response.text.splitlines():
            if not line.startswith("wireguard://"):
                continue
            parsed = urlsplit(line.strip())
            links_by_endpoint[f"{parsed.hostname}:{parsed.port}"] = parse_qs(parsed.query)

        expected_addr = ",".join(peer_ips)
        assert links_by_endpoint[f"{first_endpoint}:51820"]["address"] == [expected_addr]
        assert links_by_endpoint[f"{second_endpoint}:51821"]["address"] == [expected_addr]

        wireguard_response = client.get(f"{user['subscription_url']}/wireguard")
        assert wireguard_response.status_code == status.HTTP_200_OK
        config_bodies = extract_wireguard_config_bodies(wireguard_response)
        assert len(config_bodies) == 2

        addr_line = f"Address = {', '.join(peer_ips)}"
        expected_endpoints = {f"Endpoint = {first_endpoint}:51820", f"Endpoint = {second_endpoint}:51821"}
        actual_endpoints = set()
        for body in config_bodies:
            assert addr_line in body
            for endpoint in expected_endpoints:
                if endpoint in body:
                    actual_endpoints.add(endpoint)
        assert actual_endpoints == expected_endpoints

        # Test no-op update preserves allocated peer_ips
        update_response = client.put(
            f"/api/user/{user['username']}",
            headers=auth_headers(access_token),
            json={"note": "keep existing wireguard allocations"},
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["proxy_settings"]["wireguard"]["peer_ips"] == peer_ips
    finally:
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        client.delete(f"/api/host/{first_host_id}", headers=auth_headers(access_token))
        client.delete(f"/api/host/{second_host_id}", headers=auth_headers(access_token))
        delete_core(access_token, first_core["id"])
        delete_core(access_token, second_core["id"])


def test_shared_wireguard_peer_ips_can_be_applied_to_multiple_interfaces(access_token):
    first_private_key, _ = generate_wireguard_keypair()
    second_private_key, _ = generate_wireguard_keypair()
    first_interface = unique_name("wg_multi_explicit_a")
    second_interface = unique_name("wg_multi_explicit_b")
    first_endpoint = "198.51.100.23"
    second_endpoint = "198.51.100.24"
    shared_peer_ips = ["10.30.20.9/32"]
    updated_shared_peer_ips = ["10.30.20.10/32"]

    first_core = create_core(
        access_token,
        name=unique_name("wireguard_multi_explicit_core_a"),
        config={
            "interface_name": first_interface,
            "private_key": first_private_key,
            "listen_port": 51820,
            "address": ["10.30.20.1/24"],
        },
        type="wg",
        fallbacks=[],
    )
    second_core = create_core(
        access_token,
        name=unique_name("wireguard_multi_explicit_core_b"),
        config={
            "interface_name": second_interface,
            "private_key": second_private_key,
            "listen_port": 51821,
            "address": ["10.40.20.1/24"],
        },
        type="wg",
        fallbacks=[],
    )

    first_host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "WG Multi Shared A {USERNAME}",
            "address": [first_endpoint],
            "port": 51820,
            "inbound_tag": first_interface,
            "priority": 1,
        },
    )
    assert first_host_response.status_code == status.HTTP_201_CREATED
    first_host_id = first_host_response.json()["id"]

    second_host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "WG Multi Shared B {USERNAME}",
            "address": [second_endpoint],
            "port": 51821,
            "inbound_tag": second_interface,
            "priority": 2,
        },
    )
    assert second_host_response.status_code == status.HTTP_201_CREATED
    second_host_id = second_host_response.json()["id"]

    group = create_group(
        access_token,
        name=unique_name("wg_multi_explicit_group"),
        inbound_tags=[first_interface, second_interface],
    )
    user = None

    try:
        user = create_user(
            access_token,
            group_ids=[group["id"]],
            payload={
                "username": unique_name("wg_multi_shared_user"),
                "proxy_settings": {
                    "wireguard": {
                        "peer_ips": shared_peer_ips,
                    }
                },
            },
        )

        # With simplified model, peer_ips are stored directly
        wireguard_settings = user["proxy_settings"]["wireguard"]
        assert wireguard_settings["peer_ips"] == shared_peer_ips

        # Verify WireGuard links use the shared peer IPs
        links_response = client.get(f"{user['subscription_url']}/links")
        assert links_response.status_code == status.HTTP_200_OK

        links_by_endpoint: dict[str, dict[str, list[str]]] = {}
        for line in links_response.text.splitlines():
            if not line.startswith("wireguard://"):
                continue
            parsed = urlsplit(line.strip())
            links_by_endpoint[f"{parsed.hostname}:{parsed.port}"] = parse_qs(parsed.query)

        # Both endpoints should have the same peer IPs
        expected_address = ",".join(shared_peer_ips)
        assert links_by_endpoint[f"{first_endpoint}:51820"]["address"] == [expected_address]
        assert links_by_endpoint[f"{second_endpoint}:51821"]["address"] == [expected_address]

        # Verify WireGuard subscription contains the shared peer IPs
        wireguard_response = client.get(f"{user['subscription_url']}/wireguard")
        assert wireguard_response.status_code == status.HTTP_200_OK
        config_bodies = extract_wireguard_config_bodies(wireguard_response)
        assert len(config_bodies) == 2

        expected_address = f"Address = {', '.join(shared_peer_ips)}"
        expected_endpoints = {f"Endpoint = {first_endpoint}:51820", f"Endpoint = {second_endpoint}:51821"}
        actual_endpoints = set()

        for body in config_bodies:
            assert expected_address in body
            for endpoint in expected_endpoints:
                if endpoint in body:
                    actual_endpoints.add(endpoint)

        assert actual_endpoints == expected_endpoints

        # Test updating with new peer_ips
        updated_proxy_settings = deepcopy(user["proxy_settings"])
        updated_proxy_settings["wireguard"]["peer_ips"] = updated_shared_peer_ips
        update_response = client.put(
            f"/api/user/{user['username']}",
            headers=auth_headers(access_token),
            json={"proxy_settings": updated_proxy_settings},
        )
        assert update_response.status_code == status.HTTP_200_OK

        updated_wireguard = update_response.json()["proxy_settings"]["wireguard"]
        assert updated_wireguard["peer_ips"] == updated_shared_peer_ips

        # Verify the updated peer IPs are used in subscription links
        links_response = client.get(f"{user['subscription_url']}/links")
        assert links_response.status_code == status.HTTP_200_OK

        links_by_endpoint = {}
        for line in links_response.text.splitlines():
            if not line.startswith("wireguard://"):
                continue
            parsed = urlsplit(line.strip())
            links_by_endpoint[f"{parsed.hostname}:{parsed.port}"] = parse_qs(parsed.query)

        expected_updated_address = ",".join(updated_shared_peer_ips)
        assert links_by_endpoint[f"{first_endpoint}:51820"]["address"] == [expected_updated_address]
        assert links_by_endpoint[f"{second_endpoint}:51821"]["address"] == [expected_updated_address]
    finally:
        if user:
            delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        client.delete(f"/api/host/{first_host_id}", headers=auth_headers(access_token))
        client.delete(f"/api/host/{second_host_id}", headers=auth_headers(access_token))
        delete_core(access_token, first_core["id"])
        delete_core(access_token, second_core["id"])


def test_format_rule_response_headers_supports_strings_and_json():
    rule = SubRule(
        pattern=r"^TestClient$",
        target=ConfigFormat.links,
        response_headers={
            "x-subheader": "Hello {USERNAME}",
            "x-json": {"enabled": True, "count": 2},
        },
    )

    headers = SubscriptionOperation._format_rule_response_headers(rule, {"USERNAME": "alice"})

    assert headers["x-subheader"] == "Hello alice"
    assert headers["x-json"] == '{"enabled":true,"count":2}'


def test_detect_client_rule_matches_user_agent():
    rule = SubRule(
        pattern=r"^PasarGuardRuleHeaderClient$",
        target=ConfigFormat.links,
        response_headers={"x-subheader": "Hello {USERNAME}"},
    )

    matched_rule = SubscriptionOperation.detect_client_rule("PasarGuardRuleHeaderClient", [rule])

    assert matched_rule is not None
    assert matched_rule.target == ConfigFormat.links
    assert matched_rule.response_headers["x-subheader"] == "Hello {USERNAME}"


def test_user_get(access_token):
    """Test that the user get by id route is accessible."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_get")},
    )
    try:
        response = client.get(
            f"/api/users?username={user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["users"]) == 1
        assert response.json()["users"][0]["username"] == user["username"]
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_reset_user_usage(access_token):
    """Test that the user usage can be reset."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_reset")},
    )
    try:
        response = client.post(
            f"/api/user/{user['username']}/reset",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_update(access_token):
    """Test that the user update route is accessible."""
    core, groups = setup_groups(access_token, 2)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_update")},
    )
    try:
        response = client.put(
            f"/api/user/{user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "group_ids": [groups[1]["id"]],
                "data_limit": (1024 * 1024 * 1024 * 10),
                "next_plan": {"data_limit": 10000, "expire": 10000, "add_remaining_traffic": False},
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["group_ids"] == [groups[1]["id"]]
        assert response.json()["data_limit"] == (1024 * 1024 * 1024 * 10)
        assert response.json()["next_plan"]["data_limit"] == 10000
        assert response.json()["next_plan"]["expire"] == 10000
        assert response.json()["next_plan"]["add_remaining_traffic"] is False
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_reset_by_next_user_usage(access_token):
    """Test that the user next plan is available."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_next_plan")},
    )
    try:
        update = client.put(
            f"/api/user/{user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"next_plan": {"data_limit": 100, "expire": 100, "add_remaining_traffic": True}},
        )
        assert update.status_code == status.HTTP_200_OK
        response = client.post(
            f"/api/user/{user['username']}/active_next",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_revoke_user_subscription(access_token):
    """Test revoke user subscription info."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_revoke")},
    )
    try:
        response = client.post(
            f"/api/user/{user['username']}/revoke_sub",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_delete(access_token):
    """Test that the user delete route is accessible."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_delete")},
    )
    try:
        response = client.delete(
            f"/api/user/{user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
    finally:
        cleanup_groups(access_token, core, groups)


def test_create_user_with_template(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    username = unique_name("test_user_template")
    try:
        response = client.post(
            "/api/user/from_template",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"username": username, "user_template_id": template["id"]},
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["username"] == username
        assert response.json()["data_limit"] == template["data_limit"]
        assert response.json()["status"] == template["status"]
    finally:
        delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_modify_user_with_template(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    username = unique_name("test_user_template_modify")
    client.post(
        "/api/user/from_template",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"username": username, "user_template_id": template["id"]},
    )
    try:
        response = client.put(
            f"/api/user/from_template/{username}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"user_template_id": template["id"]},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data_limit"] == template["data_limit"]
        assert response.json()["status"] == template["status"]
    finally:
        delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_bulk_create_users_from_template_sequence(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    base_username = unique_name("bulk_template_seq")
    count = 2
    start_number = 3
    expected_usernames: list[str] = []

    try:
        response = client.post(
            "/api/users/bulk/from_template",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "user_template_id": template["id"],
                "strategy": "sequence",
                "username": base_username,
                "count": count,
                "start_number": start_number,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["created"] == count
        assert len(response.json()["subscription_urls"]) == count

        expected_usernames = [f"{base_username}{start_number + idx}" for idx in range(count)]

        for username in expected_usernames:
            user_response = client.get(f"/api/user/{username}", headers={"Authorization": f"Bearer {access_token}"})
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["data_limit"] == template["data_limit"]
            assert user_response.json()["status"] == template["status"]
    finally:
        for username in expected_usernames:
            delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_bulk_create_users_from_template_sequence_with_template_affixes(access_token):
    core, groups = setup_groups(access_token, 1)
    prefix = "pre_"
    suffix = "_suf"
    template = create_user_template(
        access_token,
        group_ids=[groups[0]["id"]],
        username_prefix=prefix,
        username_suffix=suffix,
    )
    base_username = unique_name("bulk_template_affix_seq")
    count = 2
    start_number = 7
    expected_usernames: list[str] = []

    try:
        response = client.post(
            "/api/users/bulk/from_template",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "user_template_id": template["id"],
                "strategy": "sequence",
                "username": base_username,
                "count": count,
                "start_number": start_number,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["created"] == count
        assert len(response.json()["subscription_urls"]) == count

        expected_usernames = [f"{prefix}{base_username}{suffix}{start_number + idx}" for idx in range(count)]

        for username in expected_usernames:
            user_response = client.get(f"/api/user/{username}", headers={"Authorization": f"Bearer {access_token}"})
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["data_limit"] == template["data_limit"]
            assert user_response.json()["status"] == template["status"]
    finally:
        for username in expected_usernames:
            delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_bulk_create_users_from_template_random(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    count = 2
    created_usernames: list[str] = []

    try:
        response = client.post(
            "/api/users/bulk/from_template",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "user_template_id": template["id"],
                "count": count,
                "strategy": "random",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["created"] == count
        assert len(response.json()["subscription_urls"]) == count

        users_response = client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"group": groups[0]["id"]},
        )
        assert users_response.status_code == status.HTTP_200_OK
        users = users_response.json()["users"]
        created_usernames = [user["username"] for user in users]
        assert len(created_usernames) == count
        for user in users:
            assert user["data_limit"] == template["data_limit"]
            assert user["status"] == template["status"]
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_bulk_create_users_from_template_random_with_username_rejected(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])

    try:
        response = client.post(
            "/api/users/bulk/from_template",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "user_template_id": template["id"],
                "count": 1,
                "strategy": "random",
                "username": "should_fail",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "username must be null when strategy is 'random'" in response.text
    finally:
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_bulk_apply_template_to_users(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])

    user1 = create_user(access_token, username=unique_name("bulk_apply_tmpl_u1"))
    user2 = create_user(access_token, username=unique_name("bulk_apply_tmpl_u2"))

    try:
        response = client.post(
            "/api/users/bulk/apply_template",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "ids": [user1["id"], user2["id"]],
                "user_template_id": template["id"],
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 2

        for username in (user1["username"], user2["username"]):
            user_response = client.get(f"/api/user/{username}", headers={"Authorization": f"Bearer {access_token}"})
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["data_limit"] == template["data_limit"]
            assert user_response.json()["status"] == template["status"]
    finally:
        delete_user(access_token, user1["username"])
        delete_user(access_token, user2["username"])
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


# Tests for /api/users/simple endpoint


def test_get_users_simple_basic(access_token):
    """Test that users/simple returns correct minimal data structure."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 3 users
        for i in range(3):
            user = create_user(access_token, username=unique_name(f"user_{i}"))
            created_usernames.append(user["username"])

        # Execute
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "users" in data
        assert "total" in data

        # Check that each user has only id and username
        for user in data["users"]:
            assert set(user.keys()) == {"id", "username"}

        # Check all created usernames are present
        response_usernames = [u["username"] for u in data["users"]]
        for username in created_usernames:
            assert username in response_usernames
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_search(access_token):
    """Test case-insensitive search by username."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 3 users with specific names
        user1 = create_user(access_token, username="test_search_alice")
        user2 = create_user(access_token, username="test_search_bob")
        user3 = create_user(access_token, username="test_search_CHARLIE")
        created_usernames = [user1["username"], user2["username"], user3["username"]]

        # Execute search for "alice"
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "alice"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["users"]) >= 1
        assert any(u["username"] == "test_search_alice" for u in data["users"])
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_sort_ascending(access_token):
    """Test ascending sort by username."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 3 users with specific names for ordering
        user1 = create_user(access_token, username="user_c_sort")
        user2 = create_user(access_token, username="user_a_sort")
        user3 = create_user(access_token, username="user_b_sort")
        created_usernames = [user1["username"], user2["username"], user3["username"]]

        # Execute with ascending sort
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "username"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Find our created users in the response
        our_users = [u for u in data["users"] if u["username"] in created_usernames]
        our_usernames = [u["username"] for u in our_users]
        assert our_usernames == sorted(created_usernames)
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_sort_descending(access_token):
    """Test descending sort by username."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 3 users with specific names for ordering
        user1 = create_user(access_token, username="user_a_desc")
        user2 = create_user(access_token, username="user_b_desc")
        user3 = create_user(access_token, username="user_c_desc")
        created_usernames = [user1["username"], user2["username"], user3["username"]]

        # Execute with descending sort
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "-username"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Find our created users in the response
        our_users = [u for u in data["users"] if u["username"] in created_usernames]
        our_usernames = [u["username"] for u in our_users]
        assert our_usernames == sorted(created_usernames, reverse=True)
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_pagination(access_token):
    """Test pagination with offset and limit."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 5 users
        for i in range(5):
            user = create_user(access_token, username=unique_name(f"user_pag_{i}"))
            created_usernames.append(user["username"])

        # Execute first request
        response1 = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 0, "limit": 2},
        )

        # Execute second request
        response2 = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 2, "limit": 2},
        )

        # Assert
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
        data1 = response1.json()
        data2 = response2.json()

        assert len(data1["users"]) == 2
        assert len(data2["users"]) == 2

        # Check no overlap
        usernames1 = {u["username"] for u in data1["users"]}
        usernames2 = {u["username"] for u in data2["users"]}
        assert len(usernames1 & usernames2) == 0
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_skip_pagination(access_token):
    """Test all=true parameter returns all records."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 10 users
        for i in range(10):
            user = create_user(access_token, username=unique_name(f"user_all_{i}"))
            created_usernames.append(user["username"])

        # Execute with all=true
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"all": "true"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] >= 10
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_empty_search(access_token):
    """Test search with no matching results."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 2 users
        user1 = create_user(access_token, username="known_user_1")
        user2 = create_user(access_token, username="known_user_2")
        created_usernames = [user1["username"], user2["username"]]

        # Execute search for non-existent user
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "nonexistent_xyz_12345"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert len(data["users"]) == 0
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_invalid_sort(access_token):
    """Test error handling for invalid sort parameter."""
    # Execute with invalid sort
    response = client.get(
        "/api/users/simple",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"sort": "invalid_field_xyz"},
    )

    # Assert
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_users_simple_search_and_sort(access_token):
    """Test combining search and sort parameters."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 4 users
        user1 = create_user(access_token, username="apple_user_combo")
        user2 = create_user(access_token, username="banana_user_combo")
        user3 = create_user(access_token, username="cherry_user_combo")
        user4 = create_user(access_token, username="other_name_combo")
        created_usernames = [
            user1["username"],
            user2["username"],
            user3["username"],
            user4["username"],
        ]

        # Execute with search and sort
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "_user_combo", "sort": "-username"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should return 3 users (those with _user_combo)
        matching_users = [u for u in data["users"] if "_user_combo" in u["username"]]
        assert len(matching_users) >= 3

        # Check they're sorted descending
        matching_usernames = [u["username"] for u in matching_users]
        assert matching_usernames == sorted(matching_usernames, reverse=True)
    finally:
        for username in created_usernames:
            delete_user(access_token, username)


def test_wireguard_peer_ip_global_pool_and_validation(access_token):
    """Test that peer IPs are allocated from global pool and server IP is rejected."""
    interface_private_key, _ = generate_wireguard_keypair()
    interface_name = unique_name("wg_global_pool")
    endpoint = "198.51.100.30"

    core = create_core(
        access_token,
        name=unique_name("wireguard_global_pool_core"),
        config={
            "interface_name": interface_name,
            "private_key": interface_private_key,
            "listen_port": 51820,
            "address": [],
        },
        type="wg",
        fallbacks=[],
    )

    host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "WG Global Pool {USERNAME}",
            "address": [endpoint],
            "port": 51820,
            "inbound_tag": interface_name,
            "priority": 1,
        },
    )
    assert host_response.status_code == status.HTTP_201_CREATED
    host_id = host_response.json()["id"]

    group = create_group(access_token, name=unique_name("wg_global_pool_group"), inbound_tags=[interface_name])

    user1 = None
    user2 = None
    duplicate_user = None

    try:
        # Test 1: Try to create user with server IP (10.0.0.1) - should fail
        response = client.post(
            "/api/user",
            headers=auth_headers(access_token),
            json={
                "username": unique_name("wg_server_ip_user"),
                "proxy_settings": {
                    "wireguard": {
                        "peer_ips": ["10.0.0.1/32"],
                    }
                },
                "group_ids": [group["id"]],
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "reserved" in response.json()["detail"]

        # Test 2: Create user without specifying peer IPs - should get persisted auto-allocation
        user1 = create_user(
            access_token,
            group_ids=[group["id"]],
            payload={"username": unique_name("wg_auto_ip_user1")},
        )
        peer_ips1 = user1["proxy_settings"]["wireguard"]["peer_ips"]
        assert isinstance(peer_ips1, list)
        assert len(peer_ips1) == 1
        assert peer_ips1[0].startswith("10.")
        assert peer_ips1[0].endswith("/32")
        assert peer_ips1[0] != "10.0.0.1/32"  # Should not be the reserved server IP

        # Subscription should use persisted allocation
        links_response = client.get(f"{user1['subscription_url']}/links")
        assert links_response.status_code == status.HTTP_200_OK

        # Should have a wireguard link with the persisted IP
        link = links_response.text.strip()
        assert link.startswith("wireguard://")
        parsed = urlsplit(link)
        query = parse_qs(parsed.query)
        peer_ip1 = query.get("address", [""])[0]
        assert peer_ip1 == peer_ips1[0]

        # Test 3: Manual peer_ip is validated against stored peer_ips, including auto-allocated ones.
        response = client.post(
            "/api/user",
            headers=auth_headers(access_token),
            json={
                "username": unique_name("wg_duplicate_ip_user"),
                "proxy_settings": {
                    "wireguard": {
                        "peer_ips": [peer_ip1],
                    }
                },
                "group_ids": [group["id"]],
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already in use" in response.json()["detail"]

        # Test 4: Create another user without specifying peer IPs - should get different persisted IP
        user2 = create_user(
            access_token,
            group_ids=[group["id"]],
            payload={"username": unique_name("wg_auto_ip_user2")},
        )
        peer_ips2 = user2["proxy_settings"]["wireguard"]["peer_ips"]
        assert isinstance(peer_ips2, list)
        assert len(peer_ips2) == 1

        # Get allocated IP from subscription
        links_response2 = client.get(f"{user2['subscription_url']}/links")
        assert links_response2.status_code == status.HTTP_200_OK
        link2 = links_response2.text.strip()
        assert link2.startswith("wireguard://")
        parsed2 = urlsplit(link2)
        query2 = parse_qs(parsed2.query)
        peer_ip2 = query2.get("address", [""])[0]
        assert peer_ip2 == peer_ips2[0]
        # Different users should get different IPs
        assert peer_ip2 != peer_ip1

    finally:
        if user1:
            delete_user(access_token, user1["username"])
        if user2:
            delete_user(access_token, user2["username"])
        if duplicate_user:
            delete_user(access_token, duplicate_user["username"])
        delete_group(access_token, group["id"])
        client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_wireguard_rejects_manual_peer_ip_outside_global_pool(access_token):
    """Manual peer IPv4 must fall within WIREGUARD_GLOBAL_POOL."""
    interface_private_key, _ = generate_wireguard_keypair()
    interface_name = unique_name("wg_subnet_val")
    endpoint = "198.51.100.40"

    core = create_core(
        access_token,
        name=unique_name("wireguard_subnet_core"),
        config={
            "interface_name": interface_name,
            "private_key": interface_private_key,
            "listen_port": 51820,
            "address": ["10.88.0.1/24"],
        },
        type="wg",
        fallbacks=[],
    )

    host_response = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": "WG Subnet Val {USERNAME}",
            "address": [endpoint],
            "port": 51820,
            "inbound_tag": interface_name,
            "priority": 1,
        },
    )
    assert host_response.status_code == status.HTTP_201_CREATED
    host_id = host_response.json()["id"]

    group = create_group(access_token, name=unique_name("wg_subnet_val_group"), inbound_tags=[interface_name])

    try:
        response = client.post(
            "/api/user",
            headers=auth_headers(access_token),
            json={
                "username": unique_name("wg_bad_subnet_user"),
                "proxy_settings": {
                    "wireguard": {
                        "peer_ips": ["172.16.0.50/32"],
                    }
                },
                "group_ids": [group["id"]],
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "outside WIREGUARD_GLOBAL_POOL" in response.json()["detail"]
    finally:
        delete_group(access_token, group["id"])
        client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlsplit

from fastapi import status

from app.models.settings import ConfigFormat, SubRule
from app.operation.subscription import SubscriptionOperation
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_core,
    create_group,
    create_hosts_for_inbounds,
    create_user,
    create_user_template,
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
            "peer_keepalive_seconds": 25,
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
        assert query["address"] == [",".join(user["proxy_settings"]["wireguard"]["peer_ips"])]
        assert query["allowedips"] == ["0.0.0.0/0,::/0"]
        assert query["keepalive"] == ["25"]
        assert unquote(parsed.fragment) == expected_remark

        body = wireguard_response.text
        assert f"# Name = {expected_remark}" in body
        assert f"PrivateKey = {user['proxy_settings']['wireguard']['private_key']}" in body
        assert f"Address = {', '.join(user['proxy_settings']['wireguard']['peer_ips'])}" in body
        assert f"PublicKey = {interface_public_key}" in body
        assert "AllowedIPs = 0.0.0.0/0, ::/0" in body
        assert f"Endpoint = {endpoint}:51820" in body
        assert "PersistentKeepalive = 25" in body
        assert f"# URI: {link}" in body
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
            "peer_keepalive_seconds": 25,
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
        assert settings["address"] == user["proxy_settings"]["wireguard"]["peer_ips"]
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


def test_singbox_subscription_includes_wireguard_outbound(access_token):
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
            "peer_keepalive_seconds": 30,
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
        wireguard_outbound = next(
            (outbound for outbound in config.get("outbounds", []) if outbound.get("type") == "wireguard"), None
        )
        assert wireguard_outbound is not None
        assert wireguard_outbound["tag"] == expected_tag
        assert wireguard_outbound["system_interface"] is True
        assert wireguard_outbound["interface_name"] == "wg0"
        assert wireguard_outbound["mtu"] == 1408
        assert wireguard_outbound["local_address"] == user["proxy_settings"]["wireguard"]["peer_ips"]
        assert wireguard_outbound["private_key"] == user["proxy_settings"]["wireguard"]["private_key"]
        assert wireguard_outbound["server"] == endpoint
        assert wireguard_outbound["server_port"] == 10001
        assert wireguard_outbound["peer_public_key"] == interface_public_key
        assert wireguard_outbound["pre_shared_key"] == pre_shared_key
        assert wireguard_outbound["reserved"] == [0, 0, 0]

        peers = wireguard_outbound["peers"]
        assert len(peers) == 1
        peer = peers[0]
        assert peer["server"] == endpoint
        assert peer["server_port"] == 10001
        assert peer["public_key"] == interface_public_key
        assert peer["pre_shared_key"] == pre_shared_key
        assert peer["allowed_ips"] == ["0.0.0.0/0", "::/0"]
        assert peer["persistent_keepalive_interval"] == 30
        assert peer["reserved"] == [0, 0, 0]

        selector = next((outbound for outbound in config.get("outbounds", []) if outbound.get("tag") == "proxy"), None)
        if selector is not None:
            assert expected_tag in selector.get("outbounds", [])

        urltest = next((outbound for outbound in config.get("outbounds", []) if outbound.get("type") == "urltest"), None)
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
            "peer_keepalive_seconds": 25,
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
            "peer_keepalive_seconds": 30,
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
        peer_ips_by_inbound = user["proxy_settings"]["wireguard"]["peer_ips_by_inbound"]
        first_peer_ips = peer_ips_by_inbound[first_interface]
        second_peer_ips = peer_ips_by_inbound[second_interface]

        assert user["proxy_settings"]["wireguard"]["peer_ips"] == []
        assert first_peer_ips and second_peer_ips
        assert first_peer_ips != second_peer_ips
        assert all(peer_ip.startswith("10.30.10.") for peer_ip in first_peer_ips)
        assert all(peer_ip.startswith("10.40.10.") for peer_ip in second_peer_ips)

        links_response = client.get(f"{user['subscription_url']}/links")
        assert links_response.status_code == status.HTTP_200_OK

        links_by_endpoint: dict[str, dict[str, list[str]]] = {}
        for line in links_response.text.splitlines():
            if not line.startswith("wireguard://"):
                continue
            parsed = urlsplit(line.strip())
            links_by_endpoint[f"{parsed.hostname}:{parsed.port}"] = parse_qs(parsed.query)

        assert links_by_endpoint[f"{first_endpoint}:51820"]["address"] == [",".join(first_peer_ips)]
        assert links_by_endpoint[f"{second_endpoint}:51821"]["address"] == [",".join(second_peer_ips)]

        wireguard_response = client.get(f"{user['subscription_url']}/wireguard")
        assert wireguard_response.status_code == status.HTTP_200_OK
        body = wireguard_response.text
        assert f"Address = {', '.join(first_peer_ips)}" in body
        assert f"Endpoint = {first_endpoint}:51820" in body
        assert f"Address = {', '.join(second_peer_ips)}" in body
        assert f"Endpoint = {second_endpoint}:51821" in body

        update_response = client.put(
            f"/api/user/{user['username']}",
            headers=auth_headers(access_token),
            json={"note": "keep existing wireguard allocations"},
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert (
            update_response.json()["proxy_settings"]["wireguard"]["peer_ips_by_inbound"] == peer_ips_by_inbound
        )
    finally:
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
        cleanup_groups(access_token, core, groups)

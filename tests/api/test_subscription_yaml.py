import random

import pytest
import yaml

from app.subscription import config_cache
from app.templates import filters
from app.utils.crypto import generate_wireguard_keypair
from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_core,
    create_group,
    create_user,
    delete_core,
    delete_group,
    delete_user,
    get_inbound_details,
    unique_name,
)


@pytest.mark.skipif(not yaml.__with_libyaml__, reason="libyaml is not available")
def test_clash_subscriptions_match_pure_yaml_dumper(access_token, monkeypatch):
    headers = auth_headers(access_token)
    core = create_core(access_token)
    details = get_inbound_details(access_token)
    group = create_group(access_token, inbound_tags=[detail["tag"] for detail in details])
    user = create_user(access_token, group_ids=[group["id"]])
    host_ids = []
    fast_dumper = filters._FastDumper

    try:
        for index, detail in enumerate(details):
            payload = {
                "remark": f"🇩🇪 {{USERNAME}} {detail['tag']} ✅ {{DATA_LEFT}} 🚀",
                "address": [f"198.51.100.{index + 1}"],
                "port": 443,
                "inbound_tag": detail["tag"],
                "priority": index,
            }
            if detail["protocol"] != "wireguard":
                payload["sni"] = [f"s{index}.example.com"]
            response = client.post("/api/host", headers=headers, json=payload)
            assert response.status_code == 201, response.text
            host_ids.append(response.json()["id"])

        for client_type in ("clash", "clash_meta"):
            bodies = []
            for dumper in (fast_dumper, None):
                monkeypatch.setattr(filters, "_FastDumper", dumper)
                config_cache.clear_sub_config_cache()
                # Reality short ids are picked at random per render
                random.seed(1052)
                response = client.get(f"{user['subscription_url']}/{client_type}")
                assert response.status_code == 200
                bodies.append(response.content)

            assert "🇩🇪".encode() in bodies[0]
            assert bodies[0] == bodies[1]
    finally:
        monkeypatch.setattr(filters, "_FastDumper", fast_dumper)
        for host_id in host_ids:
            client.delete(f"/api/host/{host_id}", headers=headers)
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


@pytest.mark.parametrize("profile", ["wireguard", "amnezia-empty", "amnezia"])
def test_wireguard_profiles_in_mihomo_subscription(access_token, profile):
    headers = auth_headers(access_token)
    tag = unique_name("wg_mihomo")
    server_key, server_public = generate_wireguard_keypair()
    header_key, _ = generate_wireguard_keypair()
    config = {
        "interface_name": tag,
        "private_key": server_key,
        "listen_port": 51820,
        "address": ["10.23.5.1/24"],
    }
    expected_options = None
    if profile == "amnezia-empty":
        config["amnezia"] = {}
        expected_options = {"version": 3}
    elif profile == "amnezia":
        config["amnezia"] = {
            "jc": 0,
            "jmin": 30,
            "jmax": 60,
            "s1": 24,
            "s2": 24,
            "s3": 24,
            "s4": 24,
            "h1": "101-106",
            "h2": 201,
            "h3": "301-306",
            "h4": "401-406",
            "i1": "<r 16>",
            "header_protection_key": header_key,
            "content_padding_addition": "5-12",
            "rekey_after_time": "115-125",
            "rekey_timeout": 5,
            "reject_after_time": 180,
            "keepalive_timeout": 10,
            "max_handshake_attempts": 18,
            "random_trailers": True,
            "disable_cookies": False,
        }
        expected_options = {
            "version": 3,
            "jc": 0,
            "jmin": 30,
            "jmax": 60,
            "s1": 24,
            "s2": 24,
            "s3": 24,
            "s4": 24,
            "h1": "101-106",
            "h2": "201",
            "h3": "301-306",
            "h4": "401-406",
            "i1": "<r 16>",
            "header-protection-key": header_key,
            "content-padding-addition": "5-12",
            "rekey-after-time": "115-125",
            "rekey-timeout": "5",
            "reject-after-time": "180",
            "keepalive-timeout": "10",
            "max-handshake-attempts": "18",
            "random-trailers": True,
            "disable-cookies": False,
        }

    core = create_core(access_token, type="wg", config=config)
    group = create_group(access_token, inbound_tags=[tag])
    user = create_user(access_token, group_ids=[group["id"]])
    host_response = client.post(
        "/api/host",
        headers=headers,
        json={"remark": tag, "address": ["198.51.100.10"], "inbound_tag": tag, "priority": 1},
    )
    assert host_response.status_code == 201, host_response.text
    host_id = host_response.json()["id"]
    url = user["subscription_url"]

    try:
        for response in (
            client.get(url, headers={"User-Agent": "mihomo/1.19.34"}),
            client.get(f"{url}/clash_meta"),
        ):
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/yaml")
            assert server_key not in response.text
            data = yaml.safe_load(response.content)
            proxy = next(node for node in data["proxies"] if node["name"] == tag)
            credentials = user["proxy_settings"]["wireguard"]
            assert proxy["type"] == "wireguard"
            assert proxy["private-key"] == credentials["private_key"]
            assert proxy["public-key"] == server_public
            assert proxy["server"] == "198.51.100.10"
            assert proxy["port"] == 51820
            assert proxy["ip"] == credentials["peer_ips"][0].split("/")[0]
            if expected_options is None:
                assert "amnezia-wg-option" not in proxy
            else:
                assert proxy["amnezia-wg-option"] == expected_options

        response = client.get(f"{url}/clash")
        assert response.status_code == 200
        classic_names = [node["name"] for node in yaml.safe_load(response.content)["proxies"] or []]
        assert (tag in classic_names) is (expected_options is None)
    finally:
        client.delete(f"/api/host/{host_id}", headers=headers)
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])

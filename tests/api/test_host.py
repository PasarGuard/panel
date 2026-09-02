from fastapi import status

from app.utils.crypto import generate_wireguard_keypair
from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_client_template,
    create_core,
    delete_client_template,
    delete_core,
    get_inbounds,
    unique_name,
)


def test_host_create(access_token):
    """Test that the host create route is accessible."""

    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds, "No inbounds available for host creation"
    created_hosts = []

    try:
        for idx, inbound in enumerate(inbounds[:3]):
            payload = {
                "remark": unique_name(f"test_host_{idx}"),
                "address": ["127.0.0.1"],
                "port": 443,
                "sni": [f"test_sni_{idx}.com"],
                "inbound_tag": inbound,
                "priority": idx + 1,
                "vless_route": "6967" if idx == 0 else None,  # Only test vless_route on the first host
            }
            response = client.post(
                "/api/host",
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload,
            )
            assert response.status_code == status.HTTP_201_CREATED
            created_hosts.append(response.json()["id"])
            assert response.json()["remark"] == payload["remark"]
            assert response.json()["address"] == payload["address"]
            assert response.json()["port"] == payload["port"]
            assert response.json()["sni"] == payload["sni"]
            assert response.json()["inbound_tag"] == inbound
    finally:
        for host_id in created_hosts:
            client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_host_get(access_token):
    """Test that the host get route is accessible."""

    core = create_core(access_token)
    inbound_list = get_inbounds(access_token)
    assert inbound_list, "No inbounds available for host reads"
    inbound = inbound_list[0]
    payload = {
        "remark": unique_name("test_host_get"),
        "address": ["127.0.0.1"],
        "port": 443,
        "sni": ["test_sni_get.com"],
        "inbound_tag": inbound,
        "priority": 1,
    }
    create_response = client.post("/api/host", headers={"Authorization": f"Bearer {access_token}"}, json=payload)
    host_id = create_response.json()["id"]
    response = client.get(
        "/api/hosts",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert any(host["remark"] == payload["remark"] for host in response.json())
    client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
    delete_core(access_token, core["id"])


def test_host_update(access_token):
    """Test that the host update route is accessible."""

    core = create_core(access_token)
    inbound_list = get_inbounds(access_token)
    assert inbound_list, "No inbounds available for host updates"
    inbound = inbound_list[0]
    create_response = client.post(
        "/api/host",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "remark": unique_name("test_host_update"),
            "address": ["127.0.0.1"],
            "port": 443,
            "sni": ["test_sni.com"],
            "inbound_tag": inbound,
            "priority": 1,
        },
    )
    host_id = create_response.json()["id"]
    response = client.put(
        f"/api/host/{host_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "remark": "test_host_updated",
            "priority": 666,
            "address": ["127.0.0.2"],
            "port": 443,
            "sni": ["test_sni_updated.com"],
            "inbound_tag": "Trojan Websocket TLS",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["remark"] == "test_host_updated"
    assert response.json()["address"] == ["127.0.0.2"]
    assert response.json()["port"] == 443
    assert response.json()["sni"] == ["test_sni_updated.com"]
    assert response.json()["priority"] == 666
    assert response.json()["inbound_tag"] == "Trojan Websocket TLS"
    client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
    delete_core(access_token, core["id"])


def test_host_delete(access_token):
    """Test that the host delete route is accessible."""

    core = create_core(access_token)
    inbound_list = get_inbounds(access_token)
    assert inbound_list, "No inbounds available for host deletion"
    inbound = inbound_list[0]
    create_response = client.post(
        "/api/host",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "remark": unique_name("test_host_delete"),
            "address": ["127.0.0.1"],
            "port": 443,
            "sni": ["test_sni_delete.com"],
            "inbound_tag": inbound,
            "priority": 1,
        },
    )
    host_id = create_response.json()["id"]
    response = client.delete(
        f"/api/host/{host_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    delete_core(access_token, core["id"])


def test_wireguard_host_create(access_token):
    private_key, _ = generate_wireguard_keypair()
    interface_name = unique_name("wg_host")
    core = create_core(
        access_token,
        name=unique_name("wireguard_host_core"),
        config={
            "interface_name": interface_name,
            "private_key": private_key,
            "listen_port": 51820,
            "address": ["10.10.0.1/24"],
        },
        type="wg",
        fallbacks=[],
    )

    try:
        response = client.post(
            "/api/host",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "remark": unique_name("test_wireguard_host"),
                "address": ["198.51.100.10"],
                "port": 51820,
                "inbound_tag": interface_name,
                "priority": 1,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["inbound_tag"] == interface_name
        assert response.json()["address"] == ["198.51.100.10"]
        assert response.json()["port"] == 51820
    finally:
        hosts_response = client.get("/api/hosts", headers={"Authorization": f"Bearer {access_token}"})
        if hosts_response.status_code == status.HTTP_200_OK:
            for host in hosts_response.json():
                if host["inbound_tag"] == interface_name:
                    client.delete(f"/api/host/{host['id']}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_host_subscription_templates_create_and_update(access_token):
    core = create_core(access_token)
    inbound_list = get_inbounds(access_token)
    assert inbound_list, "No inbounds available for host template override test"
    inbound = inbound_list[0]
    first_template = create_client_template(
        access_token,
        name=unique_name("host_xray_template_first"),
        template_type="xray_subscription",
        content='{"inbounds":[{"tag":"placeholder","protocol":"vmess","settings":{"clients":[]}}],"outbounds":[{"tag":"first-template-marker","protocol":"freedom","settings":{}}]}',
    )
    second_template = create_client_template(
        access_token,
        name=unique_name("host_xray_template_second"),
        template_type="xray_subscription",
        content='{"inbounds":[{"tag":"placeholder","protocol":"vmess","settings":{"clients":[]}}],"outbounds":[{"tag":"second-template-marker","protocol":"freedom","settings":{}}]}',
    )

    host_id = None
    try:
        create_response = client.post(
            "/api/host",
            headers=auth_headers(access_token),
            json={
                "remark": unique_name("test_host_subscription_template"),
                "address": ["127.0.0.1"],
                "port": 443,
                "sni": ["test_template_host.example.com"],
                "inbound_tag": inbound,
                "priority": 1,
                "subscription_templates": {"xray": first_template["id"]},
            },
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        host_id = create_response.json()["id"]
        assert create_response.json()["subscription_templates"] == {"xray": first_template["id"]}

        update_response = client.put(
            f"/api/host/{host_id}",
            headers=auth_headers(access_token),
            json={
                "remark": unique_name("test_host_subscription_template_updated"),
                "address": ["127.0.0.2"],
                "port": 443,
                "sni": ["test_template_host_updated.example.com"],
                "inbound_tag": inbound,
                "priority": 2,
                "subscription_templates": {"xray": second_template["id"]},
            },
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["subscription_templates"] == {"xray": second_template["id"]}
    finally:
        if host_id is not None:
            client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_client_template(access_token, second_template["id"])
        delete_client_template(access_token, first_template["id"])
        delete_core(access_token, core["id"])


# Tests for /api/hosts/simple endpoint


def create_simple_host(access_token: str, inbound_tag: str, *, remark: str, priority: int) -> int:
    payload = {
        "remark": remark,
        "address": ["127.0.0.1"],
        "port": 443,
        "sni": [f"{remark}.example.com"],
        "inbound_tag": inbound_tag,
        "priority": priority,
    }
    response = client.post(
        "/api/host",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload,
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()["id"]


def test_host_finalmask_new_types(access_token):
    """Test host creation and serialization with new Xray-core FinalMask settings."""
    core = create_core(access_token)
    inbound_list = get_inbounds(access_token)
    assert inbound_list
    inbound = inbound_list[0]

    finalmask_payload = {
        "tcp": [
            {
                "type": "fragment",
                "settings": {
                    "packets": "tlshello",
                    "lengths": ["3-5", "6-8", "10-20"],
                    "delays": ["10-20"],
                    "maxSplit": "3-6",
                },
            },
            {
                "type": "xmc",
                "settings": {
                    "hostname": "mc.example.com",
                    "password": "secretpassword",
                    "profiles": [
                        {
                            "username": "User1",
                            "uuid": "00112233-4455-6677-8899-aabbccddeeff",
                            "texturesValue": "val1",
                            "texturesSignature": "sig1",
                        }
                    ],
                },
            },
        ],
        "udp": [
            {
                "type": "realm",
                "settings": {
                    "url": "realm://token@example.com:443/id123",
                    "stunServers": ["stun.l.google.com:19302"],
                },
            },
            {
                "type": "mkcp-legacy",
                "settings": {
                    "header": "wechat",
                    "value": "pass123",
                },
            },
            {
                "type": "xdns",
                "settings": {
                    "domains": ["dns1.com", "dns2.com"],
                    "resolvers": ["+udp://1.1.1.1:53"],
                },
            },
            {
                "type": "xicmp",
                "settings": {
                    "dgram": True,
                    "ips": ["1.1.1.1", "8.8.8.8"],
                },
            },
            {
                "type": "salamander",
                "settings": {
                    "password": "salamanderpass",
                    "packetSize": "100-200",
                },
            },
            {
                "type": "noise",
                "settings": {
                    "reset": "30-60",
                    "noise": [{"type": "rand", "rand": "1-8192", "delay": "10-20"}],
                },
            },
        ],
        "quicParams": {
            "congestion": "bbr",
            "bbrProfile": "standard",
            "debug": True,
            "brutalUp": 100,
            "brutalDown": 100,
            "udpHop": {"ports": "50000-60000", "interval": "10s"},
        },
    }

    create_response = client.post(
        "/api/host",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "remark": unique_name("test_host_finalmask_new"),
            "address": ["127.0.0.1"],
            "port": 443,
            "sni": ["test_fm_new.example.com"],
            "inbound_tag": inbound,
            "priority": 1,
            "final_mask_settings": finalmask_payload,
        },
    )
    assert create_response.status_code == status.HTTP_201_CREATED, create_response.text
    host_data = create_response.json()
    host_id = host_data["id"]

    try:
        get_res = client.get(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        assert get_res.status_code == status.HTTP_200_OK
        data = get_res.json()
        fm = data.get("final_mask_settings") or {}
        assert fm.get("quicParams", {}).get("bbrProfile") == "standard"
        assert len(fm.get("tcp", [])) == 2
        assert fm["tcp"][0]["type"] == "fragment"
        assert fm["tcp"][0]["settings"].get("lengths") == ["3-5", "6-8", "10-20"]
        assert fm["tcp"][0]["settings"].get("delays") == ["10-20"]
        assert len(fm.get("udp", [])) == 6
        assert fm["udp"][0]["type"] == "realm"
        assert fm["udp"][1]["type"] == "mkcp-legacy"
        assert fm["udp"][5]["settings"].get("reset") == "30-60"
        assert "apply_to" not in (fm["udp"][5]["settings"].get("noise") or [{}])[0]
    finally:
        client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_host_fragment_interval_roundtrip(access_token):
    """Freedom fragment interval must persist as interval (not serialize away as delay)."""
    core = create_core(access_token)
    inbound_list = get_inbounds(access_token)
    assert inbound_list
    inbound = inbound_list[0]

    create_response = client.post(
        "/api/host",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "remark": unique_name("fragment_interval"),
            "address": ["127.0.0.1"],
            "port": 443,
            "inbound_tag": inbound,
            "priority": 1,
            "fragment_settings": {
                "xray": {
                    "packets": "tlshello",
                    "length": "10-20",
                    "interval": "5-10",
                }
            },
        },
    )
    assert create_response.status_code == status.HTTP_201_CREATED, create_response.text
    host_id = create_response.json()["id"]

    try:
        get_res = client.get(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        assert get_res.status_code == status.HTTP_200_OK
        xray = (get_res.json().get("fragment_settings") or {}).get("xray") or {}
        assert xray.get("interval") == "5-10"
        assert xray.get("length") == "10-20"
        assert "delay" not in xray
    finally:
        client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_host_ech_settings_roundtrip(access_token):
    """All client-specific ECH values must round-trip through one JSON field."""
    core = create_core(access_token)
    host_id = None

    try:
        inbound_list = get_inbounds(access_token)
        assert inbound_list
        inbound = inbound_list[0]
        ech = {
            "xray": {"config_list": "xray-base64-config", "query_strategy": "full"},
            "mihomo": {
                "config": "mihomo-base64-config",
                "query_server_name": "mihomo-ech.example.com",
            },
            "sing_box": {
                "config": "sing-box-base64-config",
                "query_server_name": "sing-box-ech.example.com",
            },
        }

        create_response = client.post(
            "/api/host",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "remark": unique_name("format_specific_ech"),
                "address": ["127.0.0.1"],
                "port": 443,
                "inbound_tag": inbound,
                "priority": 1,
                "ech": ech,
            },
        )
        assert create_response.status_code == status.HTTP_201_CREATED, create_response.text
        host_id = create_response.json()["id"]

        get_response = client.get(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["ech"] == ech
    finally:
        if host_id is not None:
            client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_host_finalmask_legacy_interval_to_delays(access_token):
    """Legacy FinalMask fragment interval/length should normalize to delays/lengths."""
    core = create_core(access_token)
    inbound_list = get_inbounds(access_token)
    assert inbound_list
    inbound = inbound_list[0]

    create_response = client.post(
        "/api/host",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "remark": unique_name("finalmask_legacy_interval"),
            "address": ["127.0.0.1"],
            "port": 443,
            "inbound_tag": inbound,
            "priority": 1,
            "final_mask_settings": {
                "tcp": [
                    {
                        "type": "fragment",
                        "settings": {
                            "packets": "tlshello",
                            "length": "10-20",
                            "interval": "5-10",
                        },
                    }
                ]
            },
        },
    )
    assert create_response.status_code == status.HTTP_201_CREATED, create_response.text
    host_id = create_response.json()["id"]

    try:
        get_res = client.get(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        assert get_res.status_code == status.HTTP_200_OK
        settings = ((get_res.json().get("final_mask_settings") or {}).get("tcp") or [{}])[0].get("settings") or {}
        assert settings.get("lengths") == ["10-20"]
        assert settings.get("delays") == ["5-10"]
        assert "interval" not in settings
        assert "length" not in settings
    finally:
        client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])

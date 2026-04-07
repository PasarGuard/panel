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

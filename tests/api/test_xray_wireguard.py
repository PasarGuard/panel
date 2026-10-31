import io
import zipfile
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

import pytest

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


def wireguard_config(core_type, tag, secret, addresses):
    if core_type == "wg":
        return {"interface_name": tag, "private_key": secret, "listen_port": 51820, "address": addresses}
    return {
        "inbounds": [
            {
                "tag": tag,
                "protocol": "wireguard",
                "port": 51821,
                "settings": {"secretKey": secret, "address": addresses, "peers": [], "mtu": 1380},
            }
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
    }


def test_xray_wireguard_lifecycle_preserves_kernel_allocations(access_token):
    headers = auth_headers(access_token)
    secret, public = generate_wireguard_keypair()
    kernel_tag, xray_tag = unique_name("kernel_wg"), unique_name("xray_wg")
    kernel = create_core(access_token, type="wg", config=wireguard_config("wg", kernel_tag, secret, ["10.91.0.1/24"]))
    kernel_group = create_group(access_token, inbound_tags=[kernel_tag])
    kernel_user = create_user(access_token, group_ids=[kernel_group["id"]])
    kernel_settings = kernel_user["proxy_settings"]["wireguard"]
    xray = create_core(access_token, config=wireguard_config("xray", xray_tag, secret, ["10.92.0.1/24", "fd92::1/64"]))
    xray_group = create_group(access_token, inbound_tags=[xray_tag])
    user = create_user(access_token, group_ids=[kernel_group["id"], xray_group["id"]])
    host = client.post(
        "/api/host",
        headers=headers,
        json={
            "remark": "Xray WG",
            "address": ["198.51.100.20"],
            "inbound_tag": xray_tag,
            "priority": 1,
        },
    )
    try:
        assert host.status_code == 201, host.text
        wg = user["proxy_settings"]["wireguard"]
        assert wg["peer_ips"] == ["10.91.0.3/32", "10.92.0.2/32", "fd92::2/128"]
        detail = next(item for item in get_inbound_details(access_token) if item["tag"] == xray_tag)
        assert detail["protocol"] == "wireguard"
        assert detail["network"] == "udp"

        response = client.get(f"{user['subscription_url']}/links")
        assert response.status_code == 200
        link = urlsplit(response.text.strip())
        assert link.port == 51821
        query = parse_qs(link.query)
        assert query["publickey"] == [public]
        assert query["address"] == ["10.92.0.2/32,fd92::2/128"]
        assert query["mtu"] == ["1380"]
        response = client.get(f"{user['subscription_url']}/wireguard")
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            body = archive.read(archive.namelist()[0]).decode()
        assert "Address = 10.92.0.2/32, fd92::2/128" in body
        assert f"PublicKey = {public}" in body
        assert "Endpoint = 198.51.100.20:51821" in body

        # Moving an Xray subnet reconciles only the relevant allocations.
        config = deepcopy(xray["config"])
        config["inbounds"][0]["settings"]["address"] = ["10.93.0.1/24"]
        payload = {
            "name": xray["name"],
            "type": "xray",
            "config": config,
            "exclude_inbound_tags": [],
            "fallbacks_inbound_tags": [],
        }
        response = client.put(f"/api/core/{xray['id']}", headers=headers, json=payload, params={"restart_nodes": False})
        assert response.status_code == 200, response.text
        updated = client.get(f"/api/user/{user['username']}", headers=headers).json()["proxy_settings"]["wireguard"]
        assert updated["peer_ips"] == ["10.91.0.3/32", "10.93.0.2/32"]
        assert updated["private_key"] == wg["private_key"]

        # Excluding and restoring the inbound releases/recreates its allocation.
        payload["exclude_inbound_tags"] = [xray_tag]
        response = client.put(f"/api/core/{xray['id']}", headers=headers, json=payload, params={"restart_nodes": False})
        assert response.status_code == 200, response.text
        assert client.get(f"/api/user/{user['username']}", headers=headers).json()["proxy_settings"]["wireguard"][
            "peer_ips"
        ] == ["10.91.0.3/32"]
        payload["exclude_inbound_tags"] = []
        response = client.put(f"/api/core/{xray['id']}", headers=headers, json=payload, params={"restart_nodes": False})
        assert response.status_code == 200, response.text
        delete_core(access_token, xray["id"])
        xray = None
        assert client.get(f"/api/user/{user['username']}", headers=headers).json()["proxy_settings"]["wireguard"][
            "peer_ips"
        ] == ["10.91.0.3/32"]
        assert (
            client.get(f"/api/user/{kernel_user['username']}", headers=headers).json()["proxy_settings"]["wireguard"]
            == kernel_settings
        )
    finally:
        delete_user(access_token, user["username"])
        delete_user(access_token, kernel_user["username"])
        delete_group(access_token, xray_group["id"])
        delete_group(access_token, kernel_group["id"])
        if host.status_code == 201:
            client.delete(f"/api/host/{host.json()['id']}", headers=headers)
        if xray:
            delete_core(access_token, xray["id"])
        delete_core(access_token, kernel["id"])


@pytest.mark.parametrize("addresses", [[], None, ["10.95.0.1"], ["10.95.0.1/32"]])
def test_xray_core_with_unmanaged_wireguard_inbound_saves(access_token, addresses):
    secret, _ = generate_wireguard_keypair()
    tag = unique_name("xray_wg_unmanaged")
    core = create_core(access_token, config=wireguard_config("xray", tag, secret, addresses))
    try:
        response = client.get("/api/inbounds", headers=auth_headers(access_token))
        assert response.status_code == 200, response.text
        assert tag not in response.json()
    finally:
        delete_core(access_token, core["id"])


@pytest.mark.parametrize("first_type,second_type", [("wg", "xray"), ("xray", "wg"), ("xray", "xray")])
def test_wireguard_overlap_validation_across_backends(access_token, first_type, second_type):
    secret, _ = generate_wireguard_keypair()
    first = create_core(
        access_token,
        type=first_type,
        config=wireguard_config(first_type, unique_name("wg_first"), secret, ["10.94.0.1/24"]),
    )
    try:
        config = wireguard_config(second_type, unique_name("wg_second"), secret, ["10.94.0.5/25"])
        response = client.post(
            "/api/core",
            headers=auth_headers(access_token),
            json={
                "name": unique_name("overlap"),
                "type": second_type,
                "config": config,
                "exclude_inbound_tags": [],
                "fallbacks_inbound_tags": [],
            },
        )
        assert response.status_code == 400, response.text
        assert "overlaps" in response.text
        config = wireguard_config(second_type, unique_name("wg_shared"), secret, ["10.94.0.5/24"])
        shared = create_core(access_token, type=second_type, config=config)
        delete_core(access_token, shared["id"])
    finally:
        delete_core(access_token, first["id"])

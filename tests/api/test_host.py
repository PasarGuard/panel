from fastapi import status

from tests.api import client
from tests.api.helpers import create_core, delete_core, get_inbounds, unique_name


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


def test_get_hosts_simple_basic(access_token):
    """Test that hosts/simple returns correct minimal data structure."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds, "No inbounds available for host creation"
    created_ids = []
    created_remarks = []
    try:
        for i in range(3):
            remark = unique_name(f"host_simple_{i}")
            host_id = create_simple_host(access_token, inbounds[i % len(inbounds)], remark=remark, priority=i + 1)
            created_ids.append(host_id)
            created_remarks.append(remark)

        response = client.get(
            "/api/hosts/simple",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "hosts" in data
        assert "total" in data

        for host in data["hosts"]:
            assert set(host.keys()) == {"id", "remark", "address", "port", "inbound_tag", "priority"}

        response_remarks = [h["remark"] for h in data["hosts"]]
        for remark in created_remarks:
            assert remark in response_remarks
    finally:
        for host_id in created_ids:
            client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_get_hosts_simple_search(access_token):
    """Test case-insensitive search by remark."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds, "No inbounds available for host creation"
    created_ids = []
    try:
        remark_alpha = unique_name("host_alpha_search")
        remark_beta = unique_name("host_beta_search")
        remark_other = unique_name("host_other_search")
        created_ids.append(create_simple_host(access_token, inbounds[0], remark=remark_alpha, priority=1))
        created_ids.append(create_simple_host(access_token, inbounds[0], remark=remark_beta, priority=2))
        created_ids.append(create_simple_host(access_token, inbounds[0], remark=remark_other, priority=3))

        response = client.get(
            "/api/hosts/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "alpha_search"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["hosts"]) >= 1
        assert any(h["remark"] == remark_alpha for h in data["hosts"])
    finally:
        for host_id in created_ids:
            client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_get_hosts_simple_sort_ascending(access_token):
    """Test ascending sort by remark."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds, "No inbounds available for host creation"
    created_ids = []
    remarks = []
    try:
        for remark in ["host_c_sort", "host_a_sort", "host_b_sort"]:
            unique_remark = unique_name(remark)
            remarks.append(unique_remark)
            created_ids.append(create_simple_host(access_token, inbounds[0], remark=unique_remark, priority=1))

        response = client.get(
            "/api/hosts/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "remark"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        our_hosts = [h for h in data["hosts"] if h["remark"] in remarks]
        our_remarks = [h["remark"] for h in our_hosts]
        assert our_remarks == sorted(remarks)
    finally:
        for host_id in created_ids:
            client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_get_hosts_simple_sort_descending(access_token):
    """Test descending sort by remark."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds, "No inbounds available for host creation"
    created_ids = []
    remarks = []
    try:
        for remark in ["host_a_desc", "host_b_desc", "host_c_desc"]:
            unique_remark = unique_name(remark)
            remarks.append(unique_remark)
            created_ids.append(create_simple_host(access_token, inbounds[0], remark=unique_remark, priority=1))

        response = client.get(
            "/api/hosts/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "-remark"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        our_hosts = [h for h in data["hosts"] if h["remark"] in remarks]
        our_remarks = [h["remark"] for h in our_hosts]
        assert our_remarks == sorted(remarks, reverse=True)
    finally:
        for host_id in created_ids:
            client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_get_hosts_simple_pagination(access_token):
    """Test pagination with offset and limit."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds, "No inbounds available for host creation"
    created_ids = []
    try:
        for i in range(5):
            remark = unique_name(f"host_pag_{i}")
            created_ids.append(create_simple_host(access_token, inbounds[0], remark=remark, priority=i + 1))

        response1 = client.get(
            "/api/hosts/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 0, "limit": 2},
        )
        response2 = client.get(
            "/api/hosts/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 2, "limit": 2},
        )

        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
        data1 = response1.json()
        data2 = response2.json()
        assert len(data1["hosts"]) == 2
        assert len(data2["hosts"]) == 2

        ids1 = {h["id"] for h in data1["hosts"]}
        ids2 = {h["id"] for h in data2["hosts"]}
        assert len(ids1 & ids2) == 0
    finally:
        for host_id in created_ids:
            client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_get_hosts_simple_skip_pagination(access_token):
    """Test all=true parameter returns all records."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds, "No inbounds available for host creation"
    created_ids = []
    try:
        for i in range(10):
            remark = unique_name(f"host_all_{i}")
            created_ids.append(create_simple_host(access_token, inbounds[0], remark=remark, priority=i + 1))

        response = client.get(
            "/api/hosts/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"all": "true"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "hosts" in data
        assert "total" in data
        assert data["total"] >= 10
    finally:
        for host_id in created_ids:
            client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_get_hosts_simple_empty_search(access_token):
    """Test search with no matching results."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds, "No inbounds available for host creation"
    created_ids = []
    try:
        remark1 = unique_name("known_host_search_1")
        remark2 = unique_name("known_host_search_2")
        created_ids.append(create_simple_host(access_token, inbounds[0], remark=remark1, priority=1))
        created_ids.append(create_simple_host(access_token, inbounds[0], remark=remark2, priority=2))

        response = client.get(
            "/api/hosts/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "nonexistent_host_xyz_12345"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert len(data["hosts"]) == 0
    finally:
        for host_id in created_ids:
            client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])


def test_get_hosts_simple_invalid_sort(access_token):
    """Test error handling for invalid sort parameter."""
    response = client.get(
        "/api/hosts/simple",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"sort": "invalid_field_xyz"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_hosts_simple_search_and_sort(access_token):
    """Test combining search and sort parameters."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds, "No inbounds available for host creation"
    created_ids = []
    remarks = []
    try:
        for remark in ["alpha_host_combo", "beta_host_combo", "gamma_host_combo", "other_host_combo"]:
            unique_remark = unique_name(remark)
            remarks.append(unique_remark)
            created_ids.append(create_simple_host(access_token, inbounds[0], remark=unique_remark, priority=1))

        response = client.get(
            "/api/hosts/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "_host_combo", "sort": "-remark"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        matching = [h for h in data["hosts"] if h["remark"] in remarks and "_host_combo" in h["remark"]]
        matching_remarks = [h["remark"] for h in matching]
        assert len(matching_remarks) >= 3
        assert matching_remarks == sorted(matching_remarks, reverse=True)
    finally:
        for host_id in created_ids:
            client.delete(f"/api/host/{host_id}", headers={"Authorization": f"Bearer {access_token}"})
        delete_core(access_token, core["id"])

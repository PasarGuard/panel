from fastapi import status

from app.core.xray import XRayConfig
from tests.api import client
from tests.api.helpers import create_core, delete_core, get_inbounds, unique_name
from tests.api.sample_data import XRAY_CONFIG as xray_config


def test_core_create(access_token):
    """Test that the core create route is accessible."""

    core = create_core(access_token, name="xray_config")
    assert core["config"] == xray_config
    assert core["name"] == "xray_config"
    for v in core["fallbacks_inbound_tags"]:
        assert v in {"fallback-A", "fallback-B"}
    assert len(core["fallbacks_inbound_tags"]) == 2
    assert len(core["exclude_inbound_tags"]) == 0
    delete_core(access_token, core["id"])


def test_core_update(access_token):
    """Test that the core update route is accessible."""

    core = create_core(access_token)
    response = client.put(
        url=f"/api/core/{core['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "config": xray_config,
            "name": "xray_config_update",
            "exclude_inbound_tags": ["Exclude"],
            "fallbacks_inbound_tags": ["fallback-A", "fallback-B", "fallback-C", "fallback-D"],
        },
        params={"restart_nodes": False},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["config"] == xray_config
    assert response.json()["name"] == "xray_config_update"
    for v in response.json()["exclude_inbound_tags"]:
        assert v in {"Exclude"}
    for v in response.json()["fallbacks_inbound_tags"]:
        assert v in {"fallback-A", "fallback-B", "fallback-C", "fallback-D"}
    assert len(response.json()["fallbacks_inbound_tags"]) == 4
    assert len(response.json()["exclude_inbound_tags"]) == 1
    delete_core(access_token, core["id"])


def test_core_get(access_token):
    """Test that the core get route is accessible."""

    core = create_core(access_token)
    response = client.get(
        url=f"/api/core/{core['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["config"] == xray_config
    delete_core(access_token, core["id"])


def test_core_delete_1(access_token):
    """Test that the core delete route is accessible."""

    response = client.delete(
        url="/api/core/1", headers={"Authorization": f"Bearer {access_token}"}, params={"restart_nodes": True}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_core_delete_2(access_token):
    """Test that the core delete route is accessible."""

    core = create_core(access_token, name="xray_config")
    response = client.delete(
        url=f"/api/core/{core['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_inbounds_get(access_token):
    """Test that the inbounds get route is accessible."""

    core = create_core(access_token)
    config_tags = [
        inbound["tag"] for inbound in xray_config["inbounds"] if inbound["tag"] not in ["fallback-B", "fallback-A"]
    ]
    inbounds = get_inbounds(access_token)
    response_tags = [inbound for inbound in inbounds if "<=>" not in inbound]
    assert len(inbounds) > 0
    assert set(response_tags) == set(config_tags)
    delete_core(access_token, core["id"])


def test_xray_auto_detects_fallback_tls_without_manual_fallback_tags():
    parsed = XRayConfig(xray_config, exclude_inbound_tags=set(), fallbacks_inbound_tags=set())
    fallback_tag = "xhttp<=>fallback-A"

    assert fallback_tag in parsed.inbounds_by_tag
    assert parsed.inbounds_by_tag[fallback_tag]["tls"] == "reality"


# Tests for /api/cores/simple endpoint


def test_get_cores_simple_basic(access_token):
    """Test that cores/simple returns correct minimal data structure."""
    created_core_ids = []
    created_names = []
    try:
        core1 = create_core(access_token, name=unique_name("core_1"))
        core2 = create_core(access_token, name=unique_name("core_2"))
        created_core_ids = [core1["id"], core2["id"]]
        created_names = [core1["name"], core2["name"]]

        response = client.get(
            "/api/cores/simple",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "cores" in data
        assert "total" in data

        for core in data["cores"]:
            assert set(core.keys()) == {"id", "name"}

        response_names = [c["name"] for c in data["cores"]]
        for name in created_names:
            assert name in response_names
    finally:
        for core_id in created_core_ids:
            delete_core(access_token, core_id)


def test_get_cores_simple_search(access_token):
    """Test case-insensitive search by core name."""
    created_core_ids = []
    try:
        core1 = create_core(access_token, name="core_alpha_search")
        core2 = create_core(access_token, name="core_beta_search")
        core3 = create_core(access_token, name="other_core_search")
        created_core_ids = [core1["id"], core2["id"], core3["id"]]

        response = client.get(
            "/api/cores/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "alpha"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["cores"]) >= 1
        assert any(c["name"] == "core_alpha_search" for c in data["cores"])
    finally:
        for core_id in created_core_ids:
            delete_core(access_token, core_id)


def test_get_cores_simple_sort_ascending(access_token):
    """Test ascending sort by core name."""
    created_core_ids = []
    created_names = []
    try:
        core1 = create_core(access_token, name="core_c_sort")
        core2 = create_core(access_token, name="core_a_sort")
        core3 = create_core(access_token, name="core_b_sort")
        created_core_ids = [core1["id"], core2["id"], core3["id"]]
        created_names = [core1["name"], core2["name"], core3["name"]]

        response = client.get(
            "/api/cores/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "name"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        our_cores = [c for c in data["cores"] if c["name"] in created_names]
        our_names = [c["name"] for c in our_cores]
        assert our_names == sorted(created_names)
    finally:
        for core_id in created_core_ids:
            delete_core(access_token, core_id)


def test_get_cores_simple_sort_descending(access_token):
    """Test descending sort by core name."""
    created_core_ids = []
    created_names = []
    try:
        core1 = create_core(access_token, name="core_a_desc")
        core2 = create_core(access_token, name="core_b_desc")
        core3 = create_core(access_token, name="core_c_desc")
        created_core_ids = [core1["id"], core2["id"], core3["id"]]
        created_names = [core1["name"], core2["name"], core3["name"]]

        response = client.get(
            "/api/cores/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "-name"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        our_cores = [c for c in data["cores"] if c["name"] in created_names]
        our_names = [c["name"] for c in our_cores]
        assert our_names == sorted(created_names, reverse=True)
    finally:
        for core_id in created_core_ids:
            delete_core(access_token, core_id)


def test_get_cores_simple_pagination(access_token):
    """Test pagination with offset and limit."""
    created_core_ids = []
    try:
        for i in range(5):
            core = create_core(access_token, name=unique_name(f"core_pag_{i}"))
            created_core_ids.append(core["id"])

        response1 = client.get(
            "/api/cores/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 0, "limit": 2},
        )
        response2 = client.get(
            "/api/cores/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 2, "limit": 2},
        )

        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
        data1 = response1.json()
        data2 = response2.json()
        assert len(data1["cores"]) == 2
        assert len(data2["cores"]) == 2

        ids1 = {c["id"] for c in data1["cores"]}
        ids2 = {c["id"] for c in data2["cores"]}
        assert len(ids1 & ids2) == 0
    finally:
        for core_id in created_core_ids:
            delete_core(access_token, core_id)


def test_get_cores_simple_skip_pagination(access_token):
    """Test all=true parameter returns all records."""
    created_core_ids = []
    try:
        for i in range(10):
            core = create_core(access_token, name=unique_name(f"core_all_{i}"))
            created_core_ids.append(core["id"])

        response = client.get(
            "/api/cores/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"all": "true"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "cores" in data
        assert "total" in data
        assert data["total"] >= 10
    finally:
        for core_id in created_core_ids:
            delete_core(access_token, core_id)


def test_get_cores_simple_empty_search(access_token):
    """Test search with no matching results."""
    created_core_ids = []
    try:
        core1 = create_core(access_token, name="known_core_search_1")
        core2 = create_core(access_token, name="known_core_search_2")
        created_core_ids = [core1["id"], core2["id"]]

        response = client.get(
            "/api/cores/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "nonexistent_core_xyz_12345"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert len(data["cores"]) == 0
    finally:
        for core_id in created_core_ids:
            delete_core(access_token, core_id)


def test_get_cores_simple_invalid_sort(access_token):
    """Test error handling for invalid sort parameter."""
    response = client.get(
        "/api/cores/simple",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"sort": "invalid_field_xyz"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_cores_simple_search_and_sort(access_token):
    """Test combining search and sort parameters."""
    created_core_ids = []
    created_names = []
    try:
        core1 = create_core(access_token, name="alpha_core_combo")
        core2 = create_core(access_token, name="beta_core_combo")
        core3 = create_core(access_token, name="gamma_core_combo")
        core4 = create_core(access_token, name="other_core_combo")
        created_core_ids = [core1["id"], core2["id"], core3["id"], core4["id"]]
        created_names = [core1["name"], core2["name"], core3["name"], core4["name"]]

        response = client.get(
            "/api/cores/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "_core_combo", "sort": "-name"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        matching = [c for c in data["cores"] if c["name"] in created_names and "_core_combo" in c["name"]]
        matching_names = [c["name"] for c in matching]
        assert len(matching_names) >= 3
        assert matching_names == sorted(matching_names, reverse=True)
    finally:
        for core_id in created_core_ids:
            delete_core(access_token, core_id)

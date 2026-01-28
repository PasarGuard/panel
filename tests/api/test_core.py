from fastapi import status

from tests.api import client
from tests.api.helpers import create_core, delete_core, get_inbounds
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

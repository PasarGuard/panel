from fastapi import status

from tests.api import client
from tests.api.helpers import auth_headers


def test_cleanup_settings_round_trip(access_token):
    """Persist cleanup settings through both update and restore operations."""
    settings_response = client.get("/api/settings", headers=auth_headers(access_token))
    assert settings_response.status_code == status.HTTP_200_OK
    original_cleanup = settings_response.json()["cleanup"]

    updated_cleanup = {
        "expired_users_retention_days": 45,
        "usage_history_retention_days": 120,
        "node_stats_retention_days": None,
    }

    try:
        update_response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"cleanup": updated_cleanup},
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["cleanup"] == updated_cleanup

        persisted_response = client.get("/api/settings", headers=auth_headers(access_token))
        assert persisted_response.status_code == status.HTTP_200_OK
        assert persisted_response.json()["cleanup"] == updated_cleanup
    finally:
        restore_response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"cleanup": original_cleanup},
        )
        assert restore_response.status_code == status.HTTP_200_OK

        restored_response = client.get("/api/settings", headers=auth_headers(access_token))
        assert restored_response.status_code == status.HTTP_200_OK
        assert restored_response.json()["cleanup"] == original_cleanup


def test_general_settings_custom_variables_round_trip(access_token):
    settings_response = client.get("/api/settings", headers=auth_headers(access_token))
    assert settings_response.status_code == status.HTTP_200_OK
    original_subscription = settings_response.json()["subscription"]

    custom_variables = [{"key": "CUSTOM_GENERAL_HOST", "value": "{USERNAME}.example.com"}]

    try:
        update_response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={
                "general": {
                    "default_method": settings_response.json()["general"]["default_method"],
                    "custom_variables": custom_variables,
                }
            },
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["general"]["custom_variables"] == custom_variables
        assert update_response.json()["subscription"]["custom_variables"] == custom_variables

        general_response = client.get("/api/settings/general", headers=auth_headers(access_token))
        assert general_response.status_code == status.HTTP_200_OK
        assert general_response.json()["custom_variables"] == custom_variables
    finally:
        restore_response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"subscription": original_subscription},
        )
        assert restore_response.status_code == status.HTTP_200_OK

from fastapi import status

from tests.api import client
from tests.api.helpers import auth_headers


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


def test_general_settings_update_keeps_fields_the_request_left_out(access_token):
    original = client.get("/api/settings", headers=auth_headers(access_token)).json()
    stored_general = {
        **original["general"],
        "on_hold_timeout_action": "disable",
        "usage": {**original["general"]["usage"], "record_node_stats": True},
        "node_health": {**original["general"]["node_health"], "fail_threshold": 7, "max_backoff": 0},
    }
    stored_general.pop("custom_variables", None)

    try:
        response = client.put("/api/settings", headers=auth_headers(access_token), json={"general": stored_general})
        assert response.status_code == status.HTTP_200_OK

        # One top-level field and one nested field: everything else keeps its stored value
        response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"general": {"stop_nodes_on_shutdown": False, "node_health": {"recover_threshold": 4}}},
        )
        assert response.status_code == status.HTTP_200_OK

        general = client.get("/api/settings", headers=auth_headers(access_token)).json()["general"]
        assert general["stop_nodes_on_shutdown"] is False
        assert general["on_hold_timeout_action"] == "disable"
        assert general["usage"]["record_node_stats"] is True
        assert general["node_health"] == {**stored_general["node_health"], "recover_threshold": 4}
    finally:
        restore_general = {key: value for key, value in original["general"].items() if key != "custom_variables"}
        response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"general": restore_general},
        )
        assert response.status_code == status.HTTP_200_OK


def test_settings_update_rejects_invalid_nested_values(access_token):
    response = client.put(
        "/api/settings",
        headers=auth_headers(access_token),
        json={"general": {"node_health": {"fail_threshold": 0}}},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_cleanup_settings_round_trip(access_token):
    """Persist cleanup settings through both update and restore operations."""
    settings_response = client.get("/api/settings", headers=auth_headers(access_token))
    assert settings_response.status_code == status.HTTP_200_OK
    original_cleanup = settings_response.json()["cleanup"]

    updated_cleanup = {
        "expired_users_retention_days": 45,
        "include_limited_users": True,
        "usage_history_retention_days": 120,
        "node_stats_retention_days": None,
        "usage_rollup_hourly_after_days": 7,
        "usage_rollup_half_day_after_days": None,
        "usage_rollup_daily_after_days": 60,
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


def test_cleanup_settings_reject_rollup_out_of_order(access_token):
    """Rollup steps must get coarser as rows get older."""
    response = client.put(
        "/api/settings",
        headers=auth_headers(access_token),
        json={"cleanup": {"usage_rollup_hourly_after_days": 30, "usage_rollup_daily_after_days": 7}},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

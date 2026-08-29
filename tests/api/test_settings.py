from fastapi import status

from tests.api import client
from tests.api.helpers import auth_headers


def test_subscription_rule_defaults_follow_environment(access_token, monkeypatch):
    from app.routers import settings as settings_router

    env_settings = settings_router.subscription_env_settings
    monkeypatch.setattr(env_settings, "use_custom_json_default", False)
    monkeypatch.setattr(env_settings, "use_custom_json_for_v2rayn", False)
    monkeypatch.setattr(env_settings, "use_custom_json_for_v2rayng", False)
    monkeypatch.setattr(env_settings, "use_custom_json_for_streisand", False)
    monkeypatch.setattr(env_settings, "use_custom_json_for_happ", False)
    monkeypatch.setattr(env_settings, "use_custom_json_for_npvtunnel", False)

    response = client.get("/api/settings/subscription/defaults", headers=auth_headers(access_token))

    assert response.status_code == status.HTTP_200_OK
    rules = response.json()
    assert {"pattern": "^[Ii]n[Hh]ive", "target": "xray", "response_headers": {}} in rules
    assert rules[-1] == {"pattern": "^.*", "target": "links_base64", "response_headers": {}}
    assert not any("2rayN" in rule["pattern"] for rule in rules)

    monkeypatch.setattr(env_settings, "use_custom_json_default", True)
    response = client.get("/api/settings/subscription/defaults", headers=auth_headers(access_token))

    assert response.status_code == status.HTTP_200_OK
    xray_rule = response.json()[-2]
    assert xray_rule["target"] == "xray"
    assert "[Vv]2rayNG" in xray_rule["pattern"]
    assert "[Vv]2rayN" in xray_rule["pattern"]


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

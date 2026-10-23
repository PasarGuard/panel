from fastapi import status

from tests.api import client
from tests.api.helpers import auth_headers


def test_general_settings_custom_variables_round_trip(access_token):
    settings_response = client.get("/api/settings", headers=auth_headers(access_token))
    assert settings_response.status_code == status.HTTP_200_OK
    original_subscription = settings_response.json()["subscription"]

    custom_variables = [{"key": "CUSTOM_GENERAL_HOST", "value": "{USERNAME}.example.com"}]
    # The response always carries `use_jinja` (default False for plain format_map variables like this one).
    expected = [{**custom_variables[0], "use_jinja": False}]

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
        assert update_response.json()["general"]["custom_variables"] == expected
        assert update_response.json()["subscription"]["custom_variables"] == expected

        general_response = client.get("/api/settings/general", headers=auth_headers(access_token))
        assert general_response.status_code == status.HTTP_200_OK
        assert general_response.json()["custom_variables"] == expected
    finally:
        restore_response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"subscription": original_subscription},
        )
        assert restore_response.status_code == status.HTTP_200_OK


def test_jinja_custom_variable_that_does_not_render_is_refused(access_token):
    settings_response = client.get("/api/settings", headers=auth_headers(access_token))
    assert settings_response.status_code == status.HTTP_200_OK
    original_subscription = settings_response.json()["subscription"]

    def put(value):
        return client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={
                "subscription": {
                    **original_subscription,
                    "custom_variables": [{"key": "SOON", "value": value, "use_jinja": True}],
                }
            },
        )

    try:
        # Parses, but "∞" (a user without expiry) cannot be compared with a number: found by rendering, which
        # happens in the validation pool when saving.
        response = put("{{ 'soon' if DAYS_LEFT < 5 else '' }}")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
        assert "Custom variable SOON" in response.json()["detail"]
        assert (
            client.get("/api/settings", headers=auth_headers(access_token)).json()["subscription"]["custom_variables"]
            == original_subscription["custom_variables"]
        )

        assert put("{{ 'soon' if DAYS_LEFT is number and DAYS_LEFT < 5 else '' }}").status_code == status.HTTP_200_OK
    finally:
        restore_response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"subscription": original_subscription},
        )
        assert restore_response.status_code == status.HTTP_200_OK


def test_saving_general_custom_variables_renders_them_once(access_token, monkeypatch):
    from app.templates.pool import validation_pool

    settings_response = client.get("/api/settings", headers=auth_headers(access_token))
    original_subscription = settings_response.json()["subscription"]
    renders = []
    run = validation_pool.run

    async def spy(func, *args, **kwargs):
        renders.append(func)
        return await run(func, *args, **kwargs)

    monkeypatch.setattr(validation_pool, "run", spy)
    variables = [{"key": "ONCE", "value": "{{ USERNAME }}", "use_jinja": True}]
    try:
        response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={
                "general": {
                    "default_method": settings_response.json()["general"]["default_method"],
                    "custom_variables": variables,
                },
                "subscription": {**original_subscription, "custom_variables": variables},
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        # Both lists carry them, and the general one replaces the subscription one: one check, not two
        assert len(renders) == 1
    finally:
        restore_response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"subscription": original_subscription},
        )
        assert restore_response.status_code == status.HTTP_200_OK

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import status

from app.models.settings import ConfigFormat
from app.operation.subscription import SubscriptionOperation
from app.subscription.profiles import ProfileValidationError
from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_client_template,
    create_user,
    delete_admin,
    delete_client_template,
    delete_user,
    unique_name,
)

PROFILE_CONTENT = '{"default_pool":"primary","pools":[{"id":"primary"}]}'


def _login(username: str, password: str) -> str:
    response = client.post(
        "/api/admin/token",
        data={"username": username, "password": password, "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access_token"]


def _create_role_without_user_read(access_token: str) -> dict:
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={"name": unique_name("no_profile_preview"), "permissions": {}},
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def _create_role_with_user_read_only(access_token: str) -> dict:
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("no_profile_template_read"),
            "permissions": {"users": {"read": True}},
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def _profile_requests(user: dict, profile_id: int, access_token: str):
    yield client.get(f"{user['subscription_url']}/profile/{profile_id}")
    yield client.get(
        f"/api/user/{user['id']}/subscription/profile/{profile_id}",
        headers=auth_headers(access_token),
    )


def test_profile_endpoints_reject_non_profile_template(access_token):
    template = create_client_template(
        access_token,
        template_type="xray_subscription",
        content=(
            '{"inbounds":[{"tag":"mixed-in","protocol":"socks","settings":{}}],'
            '"outbounds":[{"tag":"direct","protocol":"freedom","settings":{}}]}'
        ),
    )
    user = create_user(access_token)
    try:
        for response in _profile_requests(user, template["id"], access_token):
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert response.json()["detail"] == "Client template is not a subscription profile"
    finally:
        delete_user(access_token, user["username"])


def test_profile_endpoints_reject_inactive_user(access_token):
    template = create_client_template(
        access_token,
        template_type="xray_profile",
        content=PROFILE_CONTENT,
    )
    user = create_user(access_token)
    disable_response = client.put(
        f"/api/user/{user['username']}",
        headers=auth_headers(access_token),
        json={"status": "disabled"},
    )
    assert disable_response.status_code == status.HTTP_200_OK
    try:
        public_response = client.get(f"{user['subscription_url']}/profile/{template['id']}")
        assert public_response.status_code == status.HTTP_403_FORBIDDEN
        assert public_response.json()["detail"] == "Subscription is not active"

        # Admin preview remains available for diagnostics, consistently with
        # the legacy admin subscription preview endpoint.
        admin_response = client.get(
            f"/api/user/{user['id']}/subscription/profile/{template['id']}",
            headers=auth_headers(access_token),
        )
        # This fixture has no eligible endpoint to render, but the admin path
        # must reach that renderer rather than applying the public status gate.
        assert admin_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert admin_response.json()["detail"] == "No eligible endpoints are available for this user profile"
    finally:
        delete_user(access_token, user["username"])


def test_profile_endpoints_return_actionable_validation_error(access_token, monkeypatch):
    template = create_client_template(
        access_token,
        template_type="xray_profile",
        content=PROFILE_CONTENT,
    )
    user = create_user(access_token)

    async def invalid_profile(*args, **kwargs):
        raise ProfileValidationError("Profile has no eligible endpoints in pool(s): primary")

    monkeypatch.setattr("app.operation.subscription.generate_subscription_profile", invalid_profile)
    try:
        for response in _profile_requests(user, template["id"], access_token):
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
            assert response.json()["detail"] == "Profile has no eligible endpoints in pool(s): primary"
    finally:
        delete_user(access_token, user["username"])


def test_public_profile_respects_manual_format_disable(access_token, monkeypatch):
    template = create_client_template(access_token, template_type="xray_profile", content=PROFILE_CONTENT)
    user = create_user(access_token)

    async def settings_with_xray_disabled():
        return SimpleNamespace(manual_sub_request=SimpleNamespace(xray=False, sing_box=True))

    monkeypatch.setattr("app.operation.subscription.subscription_settings", settings_with_xray_disabled)
    try:
        response = client.get(f"{user['subscription_url']}/profile/{template['id']}")
        assert response.status_code == status.HTTP_406_NOT_ACCEPTABLE
        assert response.json()["detail"] == "Client not supported"
    finally:
        delete_user(access_token, user["username"])
        delete_client_template(access_token, template["id"])


def test_rejected_public_profile_does_not_register_hwid(access_token, monkeypatch):
    template = create_client_template(access_token, template_type="xray_profile", content=PROFILE_CONTENT)
    user = create_user(access_token)
    register_hwid = AsyncMock()

    async def invalid_profile(*args, **kwargs):
        raise ProfileValidationError("Profile has no eligible endpoints in pool(s): primary")

    monkeypatch.setattr("app.operation.subscription.generate_subscription_profile", invalid_profile)
    monkeypatch.setattr(SubscriptionOperation, "validate_and_register_hwid", register_hwid)
    try:
        response = client.get(
            f"{user['subscription_url']}/profile/{template['id']}",
            headers={"X-HWID": "must-not-be-recorded"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        register_hwid.assert_not_awaited()
    finally:
        delete_user(access_token, user["username"])
        delete_client_template(access_token, template["id"])


def test_public_profile_credentials_are_private_and_not_cached(access_token, monkeypatch):
    template = create_client_template(access_token, template_type="xray_profile", content=PROFILE_CONTENT)
    user = create_user(access_token)

    async def generated_profile(*args, **kwargs):
        return '{"outbounds":[]}'

    monkeypatch.setattr(SubscriptionOperation, "_render_profile_config", generated_profile)
    try:
        response = client.get(f"{user['subscription_url']}/profile/{template['id']}")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["cache-control"] == "private, no-store"
        assert response.json() == {"outbounds": []}
    finally:
        delete_user(access_token, user["username"])
        delete_client_template(access_token, template["id"])


def test_admin_profile_preview_requires_users_read(access_token):
    role = _create_role_without_user_read(access_token)
    admin = create_admin(access_token, role_id=role["id"])
    try:
        admin_token = _login(admin["username"], admin["password"])
        response = client.get(
            "/api/user/1/subscription/profile/1",
            headers=auth_headers(admin_token),
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, admin["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


def test_admin_profile_preview_requires_client_template_read(access_token):
    role = _create_role_with_user_read_only(access_token)
    admin = create_admin(access_token, role_id=role["id"])
    try:
        admin_token = _login(admin["username"], admin["password"])
        response = client.get(
            "/api/user/1/subscription/profile/1",
            headers=auth_headers(admin_token),
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, admin["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


def test_admin_profile_preview_is_not_cached(access_token, monkeypatch):
    user = create_user(access_token)

    async def generated_profile(self, db, profile_user, profile_id):
        return '{"outbounds":[]}', "application/json", ConfigFormat.xray, None

    monkeypatch.setattr(SubscriptionOperation, "fetch_profile_config", generated_profile)
    try:
        response = client.get(
            f"/api/user/{user['id']}/subscription/profile/12345",
            headers=auth_headers(access_token),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"outbounds": []}
    finally:
        delete_user(access_token, user["username"])


def test_profile_template_rejects_jinja_even_when_it_would_render_as_json(access_token):
    response = client.post(
        "/api/client_template",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("raw_profile"),
            "template_type": "xray_profile",
            "content": '{{ {"default_pool": "primary", "pools": [{"id": "primary"}]} | tojson }}',
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid template content" in response.json()["detail"]


def test_explicit_profile_templates_cannot_claim_automatic_default_semantics(access_token):
    rejected = client.post(
        "/api/client_template",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("default_profile_rejected"),
            "template_type": "xray_profile",
            "content": PROFILE_CONTENT,
            "is_default": True,
        },
    )
    assert rejected.status_code == status.HTTP_400_BAD_REQUEST
    assert "selected explicitly" in rejected.json()["detail"]

    template = create_client_template(access_token, template_type="xray_profile", content=PROFILE_CONTENT)
    try:
        assert template["is_default"] is False
        modified = client.put(
            f"/api/client_template/{template['id']}",
            headers=auth_headers(access_token),
            json={"is_default": True},
        )
        assert modified.status_code == status.HTTP_400_BAD_REQUEST
        assert "selected explicitly" in modified.json()["detail"]
    finally:
        delete_client_template(access_token, template["id"])


def test_settings_reject_missing_or_wrong_profile_reference(access_token):
    settings_response = client.get("/api/settings", headers=auth_headers(access_token))
    assert settings_response.status_code == status.HTTP_200_OK
    subscription = settings_response.json()["subscription"]
    legacy_template = create_client_template(
        access_token,
        template_type="xray_subscription",
        content=(
            '{"inbounds":[{"tag":"mixed-in","protocol":"socks","settings":{}}],'
            '"outbounds":[{"tag":"direct","protocol":"freedom","settings":{}}]}'
        ),
    )

    for profile_id, detail in (
        (2_147_483_647, "not found"),
        (legacy_template["id"], "must use template type xray_profile"),
    ):
        modified = dict(subscription)
        modified["rules"] = [{"pattern": ".*", "target": "xray", "profile_id": profile_id}]
        response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"subscription": modified},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert detail in response.json()["detail"]


def test_referenced_profile_delete_and_bulk_delete_return_conflict(access_token):
    template = create_client_template(
        access_token,
        template_type="xray_profile",
        content=PROFILE_CONTENT,
    )
    settings_response = client.get("/api/settings", headers=auth_headers(access_token))
    assert settings_response.status_code == status.HTTP_200_OK
    original_subscription = settings_response.json()["subscription"]
    modified_subscription = dict(original_subscription)
    modified_subscription["rules"] = [{"pattern": ".*", "target": "xray", "profile_id": template["id"]}]
    update_response = client.put(
        "/api/settings",
        headers=auth_headers(access_token),
        json={"subscription": modified_subscription},
    )
    assert update_response.status_code == status.HTTP_200_OK

    try:
        single_response = client.delete(f"/api/client_template/{template['id']}", headers=auth_headers(access_token))
        bulk_response = client.post(
            "/api/client_templates/bulk/delete",
            headers=auth_headers(access_token),
            json={"ids": [template["id"]]},
        )

        assert single_response.status_code == status.HTTP_409_CONFLICT
        assert bulk_response.status_code == status.HTTP_409_CONFLICT
        assert "referenced by settings rules" in single_response.json()["detail"]
        assert "referenced by settings rules" in bulk_response.json()["detail"]
    finally:
        restore_response = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"subscription": original_subscription},
        )
        assert restore_response.status_code == status.HTTP_200_OK

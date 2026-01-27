from fastapi import status

from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_core,
    create_group,
    create_user_template,
    delete_core,
    delete_group,
    delete_user_template,
    unique_name,
)


def setup_groups(access_token: str, count: int = 1):
    core = create_core(access_token)
    groups = [create_group(access_token, name=unique_name(f"template_group_{idx}")) for idx in range(count)]
    return core, groups


def cleanup_groups(access_token: str, core: dict, groups: list[dict]):
    for group in groups:
        delete_group(access_token, group["id"])
    delete_core(access_token, core["id"])


def test_user_template_create(access_token):
    """Test that the user template create route is accessible."""
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]], name="test_user_template")
    try:
        assert template["name"] == "test_user_template"
        assert template["group_ids"] == [groups[0]["id"]]
        assert template["data_limit"] == (1024 * 1024 * 1024)
        assert template["expire_duration"] == 3600
        assert template["reset_usages"]
        assert template["status"] == "active"
        assert template["extra_settings"]["flow"] == ""
        assert template["extra_settings"]["method"] is None
    finally:
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_user_templates_get(access_token):
    """Test that the user template get route is accessible."""
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    try:
        response = client.get(
            "/api/user_templates",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert any(item["id"] == template["id"] for item in response.json())
    finally:
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_user_template_update(access_token):
    """Test that the user template update route is accessible."""
    core, groups = setup_groups(access_token, 2)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    try:
        response = client.put(
            f"/api/user_template/{template['id']}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "name": "test_user_template_updated",
                "group_ids": [group["id"] for group in groups],
                "expire_duration": (86400 * 30),
                "extra_settings": {"flow": "xtls-rprx-vision", "method": "xchacha20-poly1305"},
                "status": "active",
                "reset_usages": False,
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == "test_user_template_updated"
        assert response.json()["group_ids"] == [group["id"] for group in groups]
        assert response.json()["expire_duration"] == (86400 * 30)
        assert not response.json()["reset_usages"]
        assert response.json()["extra_settings"]["flow"] == "xtls-rprx-vision"
        assert response.json()["extra_settings"]["method"] == "xchacha20-poly1305"
    finally:
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_user_template_get_by_id(access_token):
    """Test that the user template get by id route is accessible."""
    core, groups = setup_groups(access_token, 2)
    template = create_user_template(access_token, group_ids=[group["id"] for group in groups])
    try:
        response = client.get(
            f"/api/user_template/{template['id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == template["name"]
        assert set(response.json()["group_ids"]) == {group["id"] for group in groups}
        assert response.json()["expire_duration"] == template["expire_duration"]
    finally:
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_user_template_delete(access_token):
    """Test that the user template delete route is accessible."""
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    try:
        response = client.delete(
            f"/api/user_template/{template['id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
    finally:
        cleanup_groups(access_token, core, groups)

        cleanup_groups(access_token, core, groups)

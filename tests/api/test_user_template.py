from fastapi import status

from tests.api import client
from tests.api.helpers import (
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


# Tests for /api/user_templates/simple endpoint


def test_get_user_templates_simple_basic(access_token):
    """Test that user_templates/simple returns correct minimal data structure."""
    core, groups = setup_groups(access_token, 1)
    created_ids = []
    created_names = []
    try:
        tmpl1 = create_user_template(access_token, group_ids=[groups[0]["id"]], name=unique_name("tmpl_1"))
        tmpl2 = create_user_template(access_token, group_ids=[groups[0]["id"]], name=unique_name("tmpl_2"))
        created_ids = [tmpl1["id"], tmpl2["id"]]
        created_names = [tmpl1["name"], tmpl2["name"]]

        response = client.get(
            "/api/user_templates/simple",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "templates" in data
        assert "total" in data

        for template in data["templates"]:
            assert set(template.keys()) == {"id", "name"}

        response_names = [t["name"] for t in data["templates"]]
        for name in created_names:
            assert name in response_names
    finally:
        for template_id in created_ids:
            delete_user_template(access_token, template_id)
        cleanup_groups(access_token, core, groups)


def test_get_user_templates_simple_search(access_token):
    """Test case-insensitive search by template name."""
    core, groups = setup_groups(access_token, 1)
    created_ids = []
    try:
        tmpl1 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="tmpl_alpha_search")
        tmpl2 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="tmpl_beta_search")
        tmpl3 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="tmpl_other_search")
        created_ids = [tmpl1["id"], tmpl2["id"], tmpl3["id"]]

        response = client.get(
            "/api/user_templates/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "alpha"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["templates"]) >= 1
        assert any(t["name"] == "tmpl_alpha_search" for t in data["templates"])
    finally:
        for template_id in created_ids:
            delete_user_template(access_token, template_id)
        cleanup_groups(access_token, core, groups)


def test_get_user_templates_simple_sort_ascending(access_token):
    """Test ascending sort by name."""
    core, groups = setup_groups(access_token, 1)
    created_ids = []
    created_names = []
    try:
        tmpl1 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="tmpl_c_sort")
        tmpl2 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="tmpl_a_sort")
        tmpl3 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="tmpl_b_sort")
        created_ids = [tmpl1["id"], tmpl2["id"], tmpl3["id"]]
        created_names = [tmpl1["name"], tmpl2["name"], tmpl3["name"]]

        response = client.get(
            "/api/user_templates/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "name"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        our_templates = [t for t in data["templates"] if t["name"] in created_names]
        our_names = [t["name"] for t in our_templates]
        assert our_names == sorted(created_names)
    finally:
        for template_id in created_ids:
            delete_user_template(access_token, template_id)
        cleanup_groups(access_token, core, groups)


def test_get_user_templates_simple_sort_descending(access_token):
    """Test descending sort by name."""
    core, groups = setup_groups(access_token, 1)
    created_ids = []
    created_names = []
    try:
        tmpl1 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="tmpl_a_desc")
        tmpl2 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="tmpl_b_desc")
        tmpl3 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="tmpl_c_desc")
        created_ids = [tmpl1["id"], tmpl2["id"], tmpl3["id"]]
        created_names = [tmpl1["name"], tmpl2["name"], tmpl3["name"]]

        response = client.get(
            "/api/user_templates/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "-name"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        our_templates = [t for t in data["templates"] if t["name"] in created_names]
        our_names = [t["name"] for t in our_templates]
        assert our_names == sorted(created_names, reverse=True)
    finally:
        for template_id in created_ids:
            delete_user_template(access_token, template_id)
        cleanup_groups(access_token, core, groups)


def test_get_user_templates_simple_pagination(access_token):
    """Test pagination with offset and limit."""
    core, groups = setup_groups(access_token, 1)
    created_ids = []
    try:
        for i in range(5):
            tmpl = create_user_template(access_token, group_ids=[groups[0]["id"]], name=unique_name(f"tmpl_pag_{i}"))
            created_ids.append(tmpl["id"])

        response1 = client.get(
            "/api/user_templates/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 0, "limit": 2},
        )
        response2 = client.get(
            "/api/user_templates/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 2, "limit": 2},
        )

        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
        data1 = response1.json()
        data2 = response2.json()
        assert len(data1["templates"]) == 2
        assert len(data2["templates"]) == 2

        ids1 = {t["id"] for t in data1["templates"]}
        ids2 = {t["id"] for t in data2["templates"]}
        assert len(ids1 & ids2) == 0
    finally:
        for template_id in created_ids:
            delete_user_template(access_token, template_id)
        cleanup_groups(access_token, core, groups)


def test_get_user_templates_simple_skip_pagination(access_token):
    """Test all=true parameter returns all records."""
    core, groups = setup_groups(access_token, 1)
    created_ids = []
    try:
        for i in range(10):
            tmpl = create_user_template(access_token, group_ids=[groups[0]["id"]], name=unique_name(f"tmpl_all_{i}"))
            created_ids.append(tmpl["id"])

        response = client.get(
            "/api/user_templates/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"all": "true"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "templates" in data
        assert "total" in data
        assert data["total"] >= 10
    finally:
        for template_id in created_ids:
            delete_user_template(access_token, template_id)
        cleanup_groups(access_token, core, groups)


def test_get_user_templates_simple_empty_search(access_token):
    """Test search with no matching results."""
    core, groups = setup_groups(access_token, 1)
    created_ids = []
    try:
        tmpl1 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="known_tmpl_search_1")
        tmpl2 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="known_tmpl_search_2")
        created_ids = [tmpl1["id"], tmpl2["id"]]

        response = client.get(
            "/api/user_templates/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "nonexistent_tmpl_xyz_12345"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert len(data["templates"]) == 0
    finally:
        for template_id in created_ids:
            delete_user_template(access_token, template_id)
        cleanup_groups(access_token, core, groups)


def test_get_user_templates_simple_invalid_sort(access_token):
    """Test error handling for invalid sort parameter."""
    response = client.get(
        "/api/user_templates/simple",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"sort": "invalid_field_xyz"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_user_templates_simple_search_and_sort(access_token):
    """Test combining search and sort parameters."""
    core, groups = setup_groups(access_token, 1)
    created_ids = []
    created_names = []
    try:
        tmpl1 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="alpha_tmpl_combo")
        tmpl2 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="beta_tmpl_combo")
        tmpl3 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="gamma_tmpl_combo")
        tmpl4 = create_user_template(access_token, group_ids=[groups[0]["id"]], name="other_tmpl_combo")
        created_ids = [tmpl1["id"], tmpl2["id"], tmpl3["id"], tmpl4["id"]]
        created_names = [tmpl1["name"], tmpl2["name"], tmpl3["name"], tmpl4["name"]]

        response = client.get(
            "/api/user_templates/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "_tmpl_combo", "sort": "-name"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        matching = [t for t in data["templates"] if t["name"] in created_names and "_tmpl_combo" in t["name"]]
        matching_names = [t["name"] for t in matching]
        assert len(matching_names) >= 3
        assert matching_names == sorted(matching_names, reverse=True)
    finally:
        for template_id in created_ids:
            delete_user_template(access_token, template_id)
        cleanup_groups(access_token, core, groups)

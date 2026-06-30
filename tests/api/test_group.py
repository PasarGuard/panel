import random

from fastapi import status

from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_core,
    create_group,
    create_hosts_for_inbounds,
    delete_core,
    delete_group,
    get_inbound_details,
    get_inbounds,
    unique_name,
)


def test_group_create(access_token):
    """Test that the group create route is accessible."""

    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds, "Expected at least one inbound tag"
    created_groups = []
    try:
        for _ in range(3):
            k = min(3, len(inbounds))
            selected_inbounds = random.sample(inbounds, k=k) if k else inbounds
            response = create_group(access_token, name=unique_name("testgroup"), inbound_tags=selected_inbounds)
            created_groups.append(response["id"])
            assert response["name"].startswith("testgroup")
            assert set(response["inbound_tags"]) == set(selected_inbounds)
    finally:
        for group_id in created_groups:
            delete_group(access_token, group_id)
        delete_core(access_token, core["id"])


def test_group_update(access_token):
    """Test that the group update route is accessible."""

    core = create_core(access_token)
    group = create_group(access_token)
    response = client.put(
        url=f"/api/group/{group['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": "testgroup4", "is_disabled": True},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == "testgroup4"
    assert response.json()["is_disabled"] is True
    delete_group(access_token, group["id"])
    delete_core(access_token, core["id"])


def test_group_delete(access_token):
    """Test that the group delete route is accessible."""

    core = create_core(access_token)
    group = create_group(access_token)
    response = client.delete(
        url=f"/api/group/{group['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    delete_core(access_token, core["id"])


def test_group_get_by_id(access_token):
    """Test that the group get by id route is accessible."""

    core = create_core(access_token)
    group = create_group(access_token, name="testgroup_lookup")
    response = client.get(
        url=f"/api/group/{group['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == "testgroup_lookup"
    delete_group(access_token, group["id"])
    delete_core(access_token, core["id"])


def test_groups_get(access_token):
    """Test that the group get route is accessible."""

    core = create_core(access_token)
    group_one = create_group(access_token, name="testgroup_total_1")
    group_two = create_group(access_token, name="testgroup_total_2")
    response = client.get(
        url="/api/groups",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    names = [group["name"] for group in response.json()["groups"]]
    assert "testgroup_total_1" in names
    assert "testgroup_total_2" in names
    delete_group(access_token, group_one["id"])
    delete_group(access_token, group_two["id"])
    delete_core(access_token, core["id"])


# Tests for /api/groups/simple endpoint


def test_get_groups_simple_basic(access_token):
    """Test that groups/simple returns correct minimal data structure."""
    core = create_core(access_token)
    created_group_ids = []
    try:
        # Create 3 groups
        for i in range(3):
            group = create_group(access_token, name=unique_name(f"group_{i}"))
            created_group_ids.append(group["id"])

        # Execute
        response = client.get(
            "/api/groups/simple",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "groups" in data
        assert "total" in data

        # Check that each group has only id and name
        for group in data["groups"]:
            assert set(group.keys()) == {"id", "name"}

        # Check created groups are present
        response_ids = [g["id"] for g in data["groups"]]
        for gid in created_group_ids:
            assert gid in response_ids
    finally:
        for gid in created_group_ids:
            delete_group(access_token, gid)
        delete_core(access_token, core["id"])


def test_get_groups_simple_search(access_token):
    """Test case-insensitive search by group name."""
    core = create_core(access_token)
    created_group_ids = []
    try:
        # Create 3 groups with specific names
        group1 = create_group(access_token, name="group_alpha_search")
        group2 = create_group(access_token, name="group_beta_search")
        group3 = create_group(access_token, name="other_group_search")
        created_group_ids = [group1["id"], group2["id"], group3["id"]]

        # Execute search for "alpha"
        response = client.get(
            "/api/groups/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "alpha"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["groups"]) >= 1
        assert any(g["name"] == "group_alpha_search" for g in data["groups"])
    finally:
        for gid in created_group_ids:
            delete_group(access_token, gid)
        delete_core(access_token, core["id"])


def test_get_groups_simple_sort_ascending(access_token):
    """Test ascending sort by name."""
    core = create_core(access_token)
    created_group_ids = []
    try:
        # Create 3 groups with specific names for ordering
        group1 = create_group(access_token, name="group_c_sort")
        group2 = create_group(access_token, name="group_a_sort")
        group3 = create_group(access_token, name="group_b_sort")
        created_group_ids = [group1["id"], group2["id"], group3["id"]]
        created_names = [group1["name"], group2["name"], group3["name"]]

        # Execute with ascending sort
        response = client.get(
            "/api/groups/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "name"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Find our created groups in the response
        our_groups = [g for g in data["groups"] if g["name"] in created_names]
        our_names = [g["name"] for g in our_groups]
        assert our_names == sorted(created_names)
    finally:
        for gid in created_group_ids:
            delete_group(access_token, gid)
        delete_core(access_token, core["id"])


def test_get_groups_simple_sort_descending(access_token):
    """Test descending sort by name."""
    core = create_core(access_token)
    created_group_ids = []
    try:
        # Create 3 groups with specific names for ordering
        group1 = create_group(access_token, name="group_a_desc")
        group2 = create_group(access_token, name="group_b_desc")
        group3 = create_group(access_token, name="group_c_desc")
        created_group_ids = [group1["id"], group2["id"], group3["id"]]
        created_names = [group1["name"], group2["name"], group3["name"]]

        # Execute with descending sort
        response = client.get(
            "/api/groups/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "-name"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Find our created groups in the response
        our_groups = [g for g in data["groups"] if g["name"] in created_names]
        our_names = [g["name"] for g in our_groups]
        assert our_names == sorted(created_names, reverse=True)
    finally:
        for gid in created_group_ids:
            delete_group(access_token, gid)
        delete_core(access_token, core["id"])


def test_get_groups_simple_pagination(access_token):
    """Test pagination with offset and limit."""
    core = create_core(access_token)
    created_group_ids = []
    try:
        # Create 5 groups
        for i in range(5):
            group = create_group(access_token, name=unique_name(f"group_pag_{i}"))
            created_group_ids.append(group["id"])

        # Execute first request
        response1 = client.get(
            "/api/groups/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 0, "limit": 2},
        )

        # Execute second request
        response2 = client.get(
            "/api/groups/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 2, "limit": 2},
        )

        # Assert
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
        data1 = response1.json()
        data2 = response2.json()

        assert len(data1["groups"]) == 2
        assert len(data2["groups"]) == 2

        # Check no overlap
        ids1 = {g["id"] for g in data1["groups"]}
        ids2 = {g["id"] for g in data2["groups"]}
        assert len(ids1 & ids2) == 0
    finally:
        for gid in created_group_ids:
            delete_group(access_token, gid)
        delete_core(access_token, core["id"])


def test_get_groups_simple_skip_pagination(access_token):
    """Test all=true parameter returns all records."""
    core = create_core(access_token)
    created_group_ids = []
    try:
        # Create 10 groups
        for i in range(10):
            group = create_group(access_token, name=unique_name(f"group_all_{i}"))
            created_group_ids.append(group["id"])

        # Execute with all=true
        response = client.get(
            "/api/groups/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"all": "true"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "groups" in data
        assert "total" in data
        assert data["total"] >= 10
    finally:
        for gid in created_group_ids:
            delete_group(access_token, gid)
        delete_core(access_token, core["id"])


def test_get_groups_simple_empty_search(access_token):
    """Test search with no matching results."""
    core = create_core(access_token)
    group = create_group(access_token, name="known_group_search")
    try:
        # Execute search for non-existent group
        response = client.get(
            "/api/groups/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "nonexistent_xyz"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert len(data["groups"]) == 0
    finally:
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_get_groups_simple_invalid_sort(access_token):
    """Test error handling for invalid sort parameter."""
    # Execute with invalid sort
    response = client.get(
        "/api/groups/simple",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"sort": "invalid_field"},
    )

    # Assert
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_groups_simple_search_and_sort(access_token):
    """Test combining search and sort parameters."""
    core = create_core(access_token)
    created_group_ids = []
    try:
        # Create 4 groups
        group1 = create_group(access_token, name="prod_alpha_combo")
        group2 = create_group(access_token, name="prod_beta_combo")
        group3 = create_group(access_token, name="prod_gamma_combo")
        group4 = create_group(access_token, name="test_group_combo")
        created_group_ids = [group1["id"], group2["id"], group3["id"], group4["id"]]

        # Execute with search and sort
        response = client.get(
            "/api/groups/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "prod", "sort": "-name"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should return 3 groups (those with "prod")
        matching_groups = [g for g in data["groups"] if "prod" in g["name"]]
        assert len(matching_groups) >= 3

        # Check they're sorted descending
        matching_names = [g["name"] for g in matching_groups]
        assert matching_names == sorted(matching_names, reverse=True)
    finally:
        for gid in created_group_ids:
            delete_group(access_token, gid)
        delete_core(access_token, core["id"])


# ─── Host selection tests ────────────────────────────────────────────


def _find_host_for_inbound(hosts: list[dict], inbound_tag: str) -> dict | None:
    """Find a host whose inbound_tag matches the given tag."""
    for h in hosts:
        if h.get("inbound_tag") == inbound_tag:
            return h
    return None


def _find_hosts_for_inbound(hosts: list[dict], inbound_tag: str) -> list[dict]:
    """Find all hosts whose inbound_tag matches the given tag."""
    return [h for h in hosts if h.get("inbound_tag") == inbound_tag]


def test_group_create_with_host_ids(access_token):
    """Creating a group with specific host_ids returns them in the response."""
    core = create_core(access_token)
    hosts = create_hosts_for_inbounds(access_token)
    inbounds = get_inbounds(access_token)
    assert hosts, "Need at least one host"
    assert inbounds, "Need at least one inbound"
    inbound_tag = inbounds[0]
    matching_host = _find_host_for_inbound(hosts, inbound_tag)
    if not matching_host:
        # Hosts were created but none matched this inbound — skip cleanly
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])
        return
    try:
        group = create_group(
            access_token,
            name=unique_name("group_host"),
            inbound_tags=[inbound_tag],
            host_ids=[matching_host["id"]],
        )
        assert group["host_ids"] == [matching_host["id"]]
    finally:
        delete_group(access_token, group["id"])
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_group_create_without_host_ids_defaults_empty(access_token):
    """Creating a group without host_ids defaults to empty list (all hosts allowed)."""
    core = create_core(access_token)
    try:
        group = create_group(access_token, name=unique_name("group_nohost"))
        assert group["host_ids"] == []
    finally:
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_group_get_returns_host_ids(access_token):
    """GET /api/group/{id} returns host_ids."""
    core = create_core(access_token)
    hosts = create_hosts_for_inbounds(access_token)
    inbounds = get_inbounds(access_token)
    inbound_tag = inbounds[0]
    matching_host = _find_host_for_inbound(hosts, inbound_tag)
    if not matching_host:
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])
        return
    try:
        group = create_group(
            access_token,
            name=unique_name("group_get_host"),
            inbound_tags=[inbound_tag],
            host_ids=[matching_host["id"]],
        )
        response = client.get(
            f"/api/group/{group['id']}",
            headers=auth_headers(access_token),
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["host_ids"] == [matching_host["id"]]
    finally:
        delete_group(access_token, group["id"])
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_group_list_returns_host_ids(access_token):
    """GET /api/groups returns host_ids for each group."""
    core = create_core(access_token)
    hosts = create_hosts_for_inbounds(access_token)
    inbounds = get_inbounds(access_token)
    inbound_tag = inbounds[0]
    matching_host = _find_host_for_inbound(hosts, inbound_tag)
    if not matching_host:
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])
        return
    try:
        group = create_group(
            access_token,
            name=unique_name("group_list_host"),
            inbound_tags=[inbound_tag],
            host_ids=[matching_host["id"]],
        )
        response = client.get(
            "/api/groups",
            headers=auth_headers(access_token),
        )
        assert response.status_code == status.HTTP_200_OK
        found = next(g for g in response.json()["groups"] if g["id"] == group["id"])
        assert found["host_ids"] == [matching_host["id"]]
    finally:
        delete_group(access_token, group["id"])
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_group_modify_set_host_ids(access_token):
    """PUT /api/group/{id} can add host_ids to an existing group."""
    core = create_core(access_token)
    hosts = create_hosts_for_inbounds(access_token)
    inbounds = get_inbounds(access_token)
    inbound_tag = inbounds[0]
    matching_host = _find_host_for_inbound(hosts, inbound_tag)
    if not matching_host:
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])
        return
    try:
        group = create_group(
            access_token,
            name=unique_name("group_mod_host"),
            inbound_tags=[inbound_tag],
        )
        assert group["host_ids"] == []

        response = client.put(
            f"/api/group/{group['id']}",
            headers=auth_headers(access_token),
            json={"name": group["name"], "inbound_tags": [inbound_tag], "host_ids": [matching_host["id"]]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["host_ids"] == [matching_host["id"]]
    finally:
        delete_group(access_token, group["id"])
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_group_modify_clear_host_ids(access_token):
    """PUT /api/group/{id} with empty host_ids clears restrictions."""
    core = create_core(access_token)
    hosts = create_hosts_for_inbounds(access_token)
    inbounds = get_inbounds(access_token)
    inbound_tag = inbounds[0]
    matching_host = _find_host_for_inbound(hosts, inbound_tag)
    if not matching_host:
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])
        return
    try:
        group = create_group(
            access_token,
            name=unique_name("group_clear_host"),
            inbound_tags=[inbound_tag],
            host_ids=[matching_host["id"]],
        )
        assert group["host_ids"] == [matching_host["id"]]

        response = client.put(
            f"/api/group/{group['id']}",
            headers=auth_headers(access_token),
            json={"name": group["name"], "inbound_tags": [inbound_tag], "host_ids": []},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["host_ids"] == []
    finally:
        delete_group(access_token, group["id"])
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_group_modify_without_host_ids_keeps_existing(access_token):
    """PUT /api/group/{id} without host_ids field does not change existing host_ids."""
    core = create_core(access_token)
    hosts = create_hosts_for_inbounds(access_token)
    inbounds = get_inbounds(access_token)
    inbound_tag = inbounds[0]
    matching_host = _find_host_for_inbound(hosts, inbound_tag)
    if not matching_host:
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])
        return
    try:
        group = create_group(
            access_token,
            name=unique_name("group_keep_host"),
            inbound_tags=[inbound_tag],
            host_ids=[matching_host["id"]],
        )

        response = client.put(
            f"/api/group/{group['id']}",
            headers=auth_headers(access_token),
            json={"name": "renamed_keep_host", "inbound_tags": [inbound_tag]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == "renamed_keep_host"
        assert response.json()["host_ids"] == [matching_host["id"]]
    finally:
        delete_group(access_token, group["id"])
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_group_multiple_hosts(access_token):
    """Group can be created with multiple host_ids for the same inbound."""
    core = create_core(access_token)
    hosts = create_hosts_for_inbounds(access_token)
    inbounds = get_inbounds(access_token)
    inbound_tag = inbounds[0]
    matching_hosts = _find_hosts_for_inbound(hosts, inbound_tag)
    if len(matching_hosts) < 2:
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])
        return
    try:
        selected_ids = [matching_hosts[0]["id"], matching_hosts[1]["id"]]
        group = create_group(
            access_token,
            name=unique_name("group_multi_host"),
            inbound_tags=[inbound_tag],
            host_ids=selected_ids,
        )
        assert set(group["host_ids"]) == set(selected_ids)
    finally:
        delete_group(access_token, group["id"])
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_group_delete_cleans_host_associations(access_token):
    """Deleting a group cleans up the hosts_groups_association rows."""
    core = create_core(access_token)
    hosts = create_hosts_for_inbounds(access_token)
    inbounds = get_inbounds(access_token)
    inbound_tag = inbounds[0]
    matching_host = _find_host_for_inbound(hosts, inbound_tag)
    if not matching_host:
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])
        return
    try:
        group = create_group(
            access_token,
            name=unique_name("group_del_host"),
            inbound_tags=[inbound_tag],
            host_ids=[matching_host["id"]],
        )
        group_id = group["id"]
        delete_group(access_token, group_id)

        response = client.get(
            f"/api/group/{group_id}",
            headers=auth_headers(access_token),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    finally:
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_group_create_rejects_host_for_wrong_inbound(access_token):
    """Creating a group with a host belonging to a different inbound fails."""
    core = create_core(access_token)
    hosts = create_hosts_for_inbounds(access_token)
    inbounds = get_inbounds(access_token)
    assert len(inbounds) >= 2, "Need at least 2 inbounds"
    inbound_tag = inbounds[0]
    other_inbound_tag = inbounds[1]
    # Pick a host that belongs to a different inbound
    wrong_host = _find_host_for_inbound(hosts, other_inbound_tag)
    if not wrong_host:
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])
        return
    try:
        response = client.post(
            "/api/group",
            headers=auth_headers(access_token),
            json={
                "name": unique_name("group_wrong_host"),
                "inbound_tags": [inbound_tag],
                "host_ids": [wrong_host["id"]],
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    finally:
        for h in hosts:
            client.delete(f"/api/host/{h['id']}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])

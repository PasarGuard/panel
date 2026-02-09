from datetime import datetime, timedelta, timezone

from fastapi import status

from tests.api import client
from tests.api.helpers import (
    create_core,
    create_group,
    create_user,
    create_user_template,
    create_hosts_for_inbounds,
    delete_core,
    delete_group,
    delete_user,
    delete_user_template,
    unique_name,
)


def setup_groups(access_token: str, count: int = 1):
    core = create_core(access_token)
    groups = [create_group(access_token, name=unique_name(f"user_group_{idx}")) for idx in range(count)]
    return core, groups


def cleanup_groups(access_token: str, core: dict, groups: list[dict]):
    for group in groups:
        delete_group(access_token, group["id"])
    delete_core(access_token, core["id"])


def test_user_create_active(access_token):
    """Test that the user create active route is accessible."""
    core, groups = setup_groups(access_token, 2)
    group_ids = [group["id"] for group in groups]
    expire = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    user = create_user(
        access_token,
        group_ids=group_ids,
        payload={
            "username": unique_name("test_user_active"),
            "proxy_settings": {},
            "expire": expire.isoformat(),
            "data_limit": (1024 * 1024 * 1024 * 10),
            "data_limit_reset_strategy": "no_reset",
            "status": "active",
        },
    )
    try:
        assert user["data_limit"] == (1024 * 1024 * 1024 * 10)
        assert user["data_limit_reset_strategy"] == "no_reset"
        assert user["status"] == "active"
        assert set(user["group_ids"]) == set(group_ids)
        response_datetime = datetime.fromisoformat(user["expire"])
        expected_formatted = expire.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
        response_formatted = response_datetime.strftime("%Y-%m-%dT%H:%M:%S")
        assert response_formatted == expected_formatted
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_create_on_hold(access_token):
    """Test that the user create on hold route is accessible."""
    core, groups = setup_groups(access_token, 2)
    group_ids = [group["id"] for group in groups]
    expire = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    user = create_user(
        access_token,
        group_ids=group_ids,
        payload={
            "username": unique_name("test_user_on_hold"),
            "proxy_settings": {},
            "data_limit": (1024 * 1024 * 1024 * 10),
            "data_limit_reset_strategy": "no_reset",
            "status": "on_hold",
            "on_hold_timeout": expire.isoformat(),
            "on_hold_expire_duration": (86400 * 30),
        },
    )
    try:
        assert user["status"] == "on_hold"
        assert user["on_hold_expire_duration"] == (86400 * 30)
        assert set(user["group_ids"]) == set(group_ids)
        response_datetime = datetime.fromisoformat(user["on_hold_timeout"])
        expected_formatted = expire.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
        response_formatted = response_datetime.strftime("%Y-%m-%dT%H:%M:%S")
        assert response_formatted == expected_formatted
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_users_get(access_token):
    """Test that the users get route is accessible."""
    core, groups = setup_groups(access_token, 1)
    usernames = []
    try:
        for _ in range(2):
            user = create_user(
                access_token,
                group_ids=[groups[0]["id"]],
                payload={"username": unique_name("test_user_list")},
            )
            usernames.append(user["username"])

        response = client.get(
            "/api/users?load_sub=true",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        listed_usernames = {user["username"] for user in response.json()["users"]}
        for username in usernames:
            assert username in listed_usernames
    finally:
        for username in usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_user_subscriptions(access_token):
    """Test that the user subscriptions route is accessible."""
    user_subscription_formats = [
        "",
        "info",
        "usage",
        "apps",
        "sing_box",
        "clash_meta",
        "clash",
        "outline",
        "links",
        "links_base64",
        "xray",
    ]

    core, groups = setup_groups(access_token, 1)
    hosts = create_hosts_for_inbounds(access_token)
    user = create_user(
        access_token,
        group_ids=[group["id"] for group in groups],
        payload={"username": unique_name("test_user_subscriptions")},
    )
    try:
        for usf in user_subscription_formats:
            url = f"{user['subscription_url']}/{usf}"
            response = client.get(url, headers={"Accept": "text/html"} if usf == "" else None)
            assert response.status_code == status.HTTP_200_OK
    finally:
        delete_user(access_token, user["username"])
        for host in hosts:
            client.delete(f"/api/host/{host['id']}", headers={"Authorization": f"Bearer {access_token}"})
        cleanup_groups(access_token, core, groups)


def test_user_sub_update_user_agent(access_token):
    """Test that the user sub_update user_agent is accessible."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_agent")},
    )
    try:
        url = user["subscription_url"]
        user_agent = "v2rayNG/1.9.46 This is PasarGuard Test"
        client.get(url, headers={"User-Agent": user_agent})
        response = client.get(
            f"/api/user/{user['username']}/sub_update",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["updates"][0]["user_agent"] == user_agent
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_sub_update_user_agent_truncates_long_values(access_token):
    """Ensure overly long User-Agent strings are stored without failing."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_agent_truncate")},
    )
    try:
        url = user["subscription_url"]
        long_user_agent = "A" * 1000
        client.get(url, headers={"User-Agent": long_user_agent})
        response = client.get(
            f"/api/user/{user['username']}/sub_update",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["updates"][0]["user_agent"] == long_user_agent[:512]
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_get(access_token):
    """Test that the user get by id route is accessible."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_get")},
    )
    try:
        response = client.get(
            f"/api/users?username={user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["users"]) == 1
        assert response.json()["users"][0]["username"] == user["username"]
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_reset_user_usage(access_token):
    """Test that the user usage can be reset."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_reset")},
    )
    try:
        response = client.post(
            f"/api/user/{user['username']}/reset",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_update(access_token):
    """Test that the user update route is accessible."""
    core, groups = setup_groups(access_token, 2)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_update")},
    )
    try:
        response = client.put(
            f"/api/user/{user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "group_ids": [groups[1]["id"]],
                "data_limit": (1024 * 1024 * 1024 * 10),
                "next_plan": {"data_limit": 10000, "expire": 10000, "add_remaining_traffic": False},
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["group_ids"] == [groups[1]["id"]]
        assert response.json()["data_limit"] == (1024 * 1024 * 1024 * 10)
        assert response.json()["next_plan"]["data_limit"] == 10000
        assert response.json()["next_plan"]["expire"] == 10000
        assert response.json()["next_plan"]["add_remaining_traffic"] is False
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_reset_by_next_user_usage(access_token):
    """Test that the user next plan is available."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_next_plan")},
    )
    try:
        update = client.put(
            f"/api/user/{user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"next_plan": {"data_limit": 100, "expire": 100, "add_remaining_traffic": True}},
        )
        assert update.status_code == status.HTTP_200_OK
        response = client.post(
            f"/api/user/{user['username']}/active_next",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_revoke_user_subscription(access_token):
    """Test revoke user subscription info."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_revoke")},
    )
    try:
        response = client.post(
            f"/api/user/{user['username']}/revoke_sub",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
    finally:
        delete_user(access_token, user["username"])
        cleanup_groups(access_token, core, groups)


def test_user_delete(access_token):
    """Test that the user delete route is accessible."""
    core, groups = setup_groups(access_token, 1)
    user = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("test_user_delete")},
    )
    try:
        response = client.delete(
            f"/api/user/{user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
    finally:
        cleanup_groups(access_token, core, groups)


def test_create_user_with_template(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    username = unique_name("test_user_template")
    try:
        response = client.post(
            "/api/user/from_template",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"username": username, "user_template_id": template["id"]},
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["username"] == username
        assert response.json()["data_limit"] == template["data_limit"]
        assert response.json()["status"] == template["status"]
    finally:
        delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_modify_user_with_template(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    username = unique_name("test_user_template_modify")
    client.post(
        "/api/user/from_template",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"username": username, "user_template_id": template["id"]},
    )
    try:
        response = client.put(
            f"/api/user/from_template/{username}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"user_template_id": template["id"]},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data_limit"] == template["data_limit"]
        assert response.json()["status"] == template["status"]
    finally:
        delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_bulk_create_users_from_template_sequence(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    base_username = unique_name("bulk_template_seq")
    count = 2
    start_number = 3
    expected_usernames: list[str] = []

    try:
        response = client.post(
            "/api/users/bulk/from_template",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "user_template_id": template["id"],
                "strategy": "sequence",
                "username": base_username,
                "count": count,
                "start_number": start_number,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["created"] == count
        assert len(response.json()["subscription_urls"]) == count

        expected_usernames = [f"{base_username}{start_number + idx}" for idx in range(count)]

        for username in expected_usernames:
            user_response = client.get(f"/api/user/{username}", headers={"Authorization": f"Bearer {access_token}"})
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["data_limit"] == template["data_limit"]
            assert user_response.json()["status"] == template["status"]
    finally:
        for username in expected_usernames:
            delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_bulk_create_users_from_template_random(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])
    count = 2
    created_usernames: list[str] = []

    try:
        response = client.post(
            "/api/users/bulk/from_template",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "user_template_id": template["id"],
                "count": count,
                "strategy": "random",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["created"] == count
        assert len(response.json()["subscription_urls"]) == count

        users_response = client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"group": groups[0]["id"]},
        )
        assert users_response.status_code == status.HTTP_200_OK
        users = users_response.json()["users"]
        created_usernames = [user["username"] for user in users]
        assert len(created_usernames) == count
        for user in users:
            assert user["data_limit"] == template["data_limit"]
            assert user["status"] == template["status"]
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


def test_bulk_create_users_from_template_random_with_username_rejected(access_token):
    core, groups = setup_groups(access_token, 1)
    template = create_user_template(access_token, group_ids=[groups[0]["id"]])

    try:
        response = client.post(
            "/api/users/bulk/from_template",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "user_template_id": template["id"],
                "count": 1,
                "strategy": "random",
                "username": "should_fail",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "username must be null when strategy is 'random'" in response.text
    finally:
        delete_user_template(access_token, template["id"])
        cleanup_groups(access_token, core, groups)


# Tests for /api/users/simple endpoint

def test_get_users_simple_basic(access_token):
    """Test that users/simple returns correct minimal data structure."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 3 users
        for i in range(3):
            user = create_user(access_token, username=unique_name(f"user_{i}"))
            created_usernames.append(user["username"])

        # Execute
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "users" in data
        assert "total" in data

        # Check that each user has only id and username
        for user in data["users"]:
            assert set(user.keys()) == {"id", "username"}

        # Check all created usernames are present
        response_usernames = [u["username"] for u in data["users"]]
        for username in created_usernames:
            assert username in response_usernames
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_search(access_token):
    """Test case-insensitive search by username."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 3 users with specific names
        user1 = create_user(access_token, username="test_search_alice")
        user2 = create_user(access_token, username="test_search_bob")
        user3 = create_user(access_token, username="test_search_CHARLIE")
        created_usernames = [user1["username"], user2["username"], user3["username"]]

        # Execute search for "alice"
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "alice"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["users"]) >= 1
        assert any(u["username"] == "test_search_alice" for u in data["users"])
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_sort_ascending(access_token):
    """Test ascending sort by username."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 3 users with specific names for ordering
        user1 = create_user(access_token, username="user_c_sort")
        user2 = create_user(access_token, username="user_a_sort")
        user3 = create_user(access_token, username="user_b_sort")
        created_usernames = [user1["username"], user2["username"], user3["username"]]

        # Execute with ascending sort
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "username"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Find our created users in the response
        our_users = [u for u in data["users"] if u["username"] in created_usernames]
        our_usernames = [u["username"] for u in our_users]
        assert our_usernames == sorted(created_usernames)
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_sort_descending(access_token):
    """Test descending sort by username."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 3 users with specific names for ordering
        user1 = create_user(access_token, username="user_a_desc")
        user2 = create_user(access_token, username="user_b_desc")
        user3 = create_user(access_token, username="user_c_desc")
        created_usernames = [user1["username"], user2["username"], user3["username"]]

        # Execute with descending sort
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sort": "-username"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Find our created users in the response
        our_users = [u for u in data["users"] if u["username"] in created_usernames]
        our_usernames = [u["username"] for u in our_users]
        assert our_usernames == sorted(created_usernames, reverse=True)
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_pagination(access_token):
    """Test pagination with offset and limit."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 5 users
        for i in range(5):
            user = create_user(access_token, username=unique_name(f"user_pag_{i}"))
            created_usernames.append(user["username"])

        # Execute first request
        response1 = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 0, "limit": 2},
        )

        # Execute second request
        response2 = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"offset": 2, "limit": 2},
        )

        # Assert
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
        data1 = response1.json()
        data2 = response2.json()

        assert len(data1["users"]) == 2
        assert len(data2["users"]) == 2

        # Check no overlap
        usernames1 = {u["username"] for u in data1["users"]}
        usernames2 = {u["username"] for u in data2["users"]}
        assert len(usernames1 & usernames2) == 0
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_skip_pagination(access_token):
    """Test all=true parameter returns all records."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 10 users
        for i in range(10):
            user = create_user(access_token, username=unique_name(f"user_all_{i}"))
            created_usernames.append(user["username"])

        # Execute with all=true
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"all": "true"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] >= 10
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_empty_search(access_token):
    """Test search with no matching results."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 2 users
        user1 = create_user(access_token, username="known_user_1")
        user2 = create_user(access_token, username="known_user_2")
        created_usernames = [user1["username"], user2["username"]]

        # Execute search for non-existent user
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "nonexistent_xyz_12345"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert len(data["users"]) == 0
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)


def test_get_users_simple_invalid_sort(access_token):
    """Test error handling for invalid sort parameter."""
    # Execute with invalid sort
    response = client.get(
        "/api/users/simple",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"sort": "invalid_field_xyz"},
    )

    # Assert
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_users_simple_search_and_sort(access_token):
    """Test combining search and sort parameters."""
    core, groups = setup_groups(access_token, 1)
    created_usernames = []
    try:
        # Create 4 users
        user1 = create_user(access_token, username="apple_user_combo")
        user2 = create_user(access_token, username="banana_user_combo")
        user3 = create_user(access_token, username="cherry_user_combo")
        user4 = create_user(access_token, username="other_name_combo")
        created_usernames = [
            user1["username"],
            user2["username"],
            user3["username"],
            user4["username"],
        ]

        # Execute with search and sort
        response = client.get(
            "/api/users/simple",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"search": "_user_combo", "sort": "-username"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should return 3 users (those with _user_combo)
        matching_users = [u for u in data["users"] if "_user_combo" in u["username"]]
        assert len(matching_users) >= 3

        # Check they're sorted descending
        matching_usernames = [u["username"] for u in matching_users]
        assert matching_usernames == sorted(matching_usernames, reverse=True)
    finally:
        for username in created_usernames:
            delete_user(access_token, username)
        cleanup_groups(access_token, core, groups)

from fastapi import status

from tests.api import client
from tests.api.helpers import create_admin, delete_admin, unique_name


def test_admin_login():
    """Test that the admin login route is accessible."""

    response = client.post(
        url="/api/admin/token",
        data={"username": "testadmin", "password": "testadmin", "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()
    return response.json()["access_token"]


def test_get_admin(access_token):
    """Test that the admin get route is accessible."""

    # mock_settings(monkeypatch)
    username = "testadmin"
    response = client.get(
        url="/api/admin",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == username


def test_admin_create(access_token):
    """Test that the admin create route is accessible."""

    username = unique_name("testadmincreate")
    password = f"TestAdmincreate#{unique_name('pwd').split('_')[-1]}"
    admin = create_admin(access_token, username=username, password=password)
    assert admin["username"] == username
    assert admin["is_sudo"] is False
    delete_admin(access_token, username)


def test_admin_db_login(access_token):
    """Test that the admin db login route is accessible."""

    admin = create_admin(access_token)
    response = client.post(
        url="/api/admin/token",
        data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()
    delete_admin(access_token, admin["username"])


def test_update_admin(access_token):
    """Test that the admin update route is accessible."""

    admin = create_admin(access_token)
    password = f"TestAdminupdate#{unique_name('pwd').split('_')[-1]}"
    response = client.put(
        url=f"/api/admin/{admin['username']}",
        json={
            "password": password,
            "is_sudo": False,
            "is_disabled": True,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == admin["username"]
    assert response.json()["is_sudo"] is False
    assert response.json()["is_disabled"] is True
    delete_admin(access_token, admin["username"])


def test_get_admins(access_token):
    """Test that the admins get route is accessible."""

    admin = create_admin(access_token)
    response = client.get(
        url="/api/admins",
        params={"sort": "-created_at"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "admins" in response_data
    assert "total" in response_data
    assert "active" in response_data
    assert "disabled" in response_data
    assert admin["username"] in [record["username"] for record in response_data["admins"]]
    delete_admin(access_token, admin["username"])


def test_disable_admin(access_token):
    """Test that the admin disable route is accessible."""

    admin = create_admin(access_token)
    password = admin["password"]
    disable_response = client.put(
        url=f"/api/admin/{admin['username']}",
        json={"password": password, "is_sudo": False, "is_disabled": True},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert disable_response.status_code == status.HTTP_200_OK

    response = client.post(
        url="/api/admin/token",
        data={"username": admin["username"], "password": password, "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "your account has been disabled"
    delete_admin(access_token, admin["username"])


def test_admin_delete_all_users_endpoint(access_token):
    """Test deleting all users belonging to an admin."""

    admin = create_admin(access_token)
    admin_username = admin["username"]

    created_users = []
    for idx in range(2):
        user_name = unique_name(f"{admin_username}_user_{idx}")
        user_response = client.post(
            "/api/user",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "username": user_name,
                "proxy_settings": {},
                "data_limit": 1024,
                "data_limit_reset_strategy": "no_reset",
                "status": "active",
            },
        )
        assert user_response.status_code == status.HTTP_201_CREATED
        created_users.append(user_name)

        ownership_response = client.put(
            f"/api/user/{user_name}/set_owner",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"admin_username": admin_username},
        )
        assert ownership_response.status_code == status.HTTP_200_OK
        assert ownership_response.json()["admin"]["username"] == admin_username

    response = client.delete(
        url=f"/api/admin/{admin_username}/users",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert str(len(created_users)) in response.json()["detail"]

    for username in created_users:
        user_check = client.get(
            "/api/users",
            params={"username": username},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert user_check.status_code == status.HTTP_200_OK
        assert user_check.json()["users"] == []

    cleanup = client.delete(
        url=f"/api/admin/{admin_username}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert cleanup.status_code == status.HTTP_204_NO_CONTENT


def test_admin_delete(access_token):
    """Test that the admin delete route is accessible."""

    admin = create_admin(access_token)
    response = client.delete(
        url=f"/api/admin/{admin['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

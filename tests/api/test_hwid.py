from fastapi import status
from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_user,
    delete_user,
)


def test_hwid_workflow(access_token):
    """
    Test the full HWID workflow:
    1. Create a user
    2. Fetch subscription with HWID headers (Registration)
    3. Verify HWID is registered via Admin API
    4. Fetch subscription with different HWID (Limit check)
    5. Delete HWID via Admin API
    6. Reset all HWIDs for user
    """
    # 1. Create a user
    user = create_user(access_token)
    user_id = user["id"]
    sub_url = user["subscription_url"]

    try:
        # 2. Fetch subscription with HWID headers (Registration)
        hwid1 = "device-ios-123"
        headers1 = {"X-HWID": hwid1, "X-Device-OS": "iOS", "X-Ver-OS": "16.5", "X-Device-Model": "iPhone 14"}
        response = client.get(sub_url, headers=headers1)
        assert response.status_code == status.HTTP_200_OK

        # 3. Verify HWID is registered via Admin API
        response = client.get(f"/api/user/{user_id}/hwids", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 1
        item = data["hwids"][0]
        assert item["hwid"] == hwid1
        assert item["device_os"] == "iOS"
        assert item["os_version"] == "16.5"
        assert item["device_model"] == "iPhone 14"

        # 4. Fetch subscription with different HWID (Up to limit)
        # fallback_limit is 3 in conftest.py
        response = client.get(sub_url, headers={"X-HWID": "device-2"})
        assert response.status_code == status.HTTP_200_OK
        response = client.get(sub_url, headers={"X-HWID": "device-3"})
        assert response.status_code == status.HTTP_200_OK

        response = client.get(f"/api/user/{user_id}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 3

        # 4b. 4th device should fail
        response = client.get(sub_url, headers={"X-HWID": "device-4"})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Device limit reached" in response.json()["detail"]

        # 5. Delete one HWID via Admin API
        response = client.delete(f"/api/user/{user_id}/hwids/{hwid1}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK

        response = client.get(f"/api/user/{user_id}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 2

        # 6. Reset all HWIDs for user
        response = client.post(f"/api/user/{user_id}/hwids/reset", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK

        response = client.get(f"/api/user/{user_id}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 0

    finally:
        delete_user(access_token, user["username"])

from fastapi import status

from tests.api import client
from tests.api.test_bulk import cleanup, setup_groups
from tests.api.helpers import create_user, unique_name


def _listed(access_token: str, user_ids: list[int]) -> dict[int, dict]:
    response = client.get("/api/users", headers={"Authorization": f"Bearer {access_token}"})
    return {u["id"]: u for u in response.json()["users"] if u["id"] in user_ids}


def test_bulk_data_limit_amount_past_bigint_is_rejected_and_nothing_is_stored(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(
            access_token,
            group_ids=[groups[0]["id"]],
            payload={"username": unique_name("bound_dl"), "data_limit": 1024},
        )
    ]
    user_ids = [u["id"] for u in users]
    try:
        response = client.post(
            "/api/users/bulk/data_limit",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 2**63, "users": user_ids},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert _listed(access_token, user_ids)[user_ids[0]]["data_limit"] == 1024
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_expire_amount_past_any_datetime_is_rejected_and_nothing_is_stored(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(
            access_token,
            group_ids=[groups[0]["id"]],
            payload={"username": unique_name("bound_ex"), "expire": "2030-01-01T00:00:00+00:00"},
        )
    ]
    user_ids = [u["id"] for u in users]
    try:
        before = _listed(access_token, user_ids)[user_ids[0]]["expire"]
        response = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 10**15, "users": user_ids},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert _listed(access_token, user_ids)[user_ids[0]]["expire"] == before
    finally:
        cleanup(access_token, core, groups, users)

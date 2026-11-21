"""A user's next plan stays within the limits of the acting admin's role."""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy import select

from app.db.models import NextPlan
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_core,
    create_group,
    create_user_template,
    delete_admin,
    unique_name,
)

GB = 1024**3


def _role(access_token: str, permissions: dict, limits: dict | None = None) -> dict:
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("role_regression"),
            "permissions": permissions,
            "limits": limits or {},
            "features": {},
            "access": {},
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def _actor(access_token: str, permissions: dict, limits: dict | None = None) -> tuple[dict, dict, str]:
    role = _role(access_token, permissions, limits)
    admin = create_admin(access_token, role_id=role["id"])
    token = client.post(
        "/api/admin/token",
        data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
    ).json()["access_token"]
    return role, admin, token


def _drop_actor(access_token: str, role: dict, admin: dict) -> None:
    delete_admin(access_token, admin["username"])
    client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


_NEXT_PLAN_PERMISSIONS = {
    "users": {"read": {"scope": 1}, "create": True, "delete": {"scope": 1}, "activate_next_plan": {"scope": 1}}
}
_NEXT_PLAN_LIMITS = {"data_limit_max": 10 * GB, "expire_max": 30 * 86400}


def _create_user_with_next_plan(token: str, next_plan: dict):
    return client.post(
        "/api/user",
        headers=auth_headers(token),
        json={
            "username": unique_name("next_plan"),
            "proxy_settings": {},
            "data_limit": GB,
            "expire": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            "status": "active",
            "next_plan": next_plan,
        },
    )


def _store_next_plan(user_id: int, **values) -> None:
    async def write():
        async with TestSession() as session:
            plan = (await session.execute(select(NextPlan).where(NextPlan.user_id == user_id))).scalar_one()
            for key, value in values.items():
                setattr(plan, key, value)
            await session.commit()

    asyncio.run(write())


def test_next_plan_respects_role_data_and_duration_limits(access_token):
    role, admin, token = _actor(access_token, _NEXT_PLAN_PERMISSIONS, limits=_NEXT_PLAN_LIMITS)
    created = []
    try:
        for next_plan in (
            {"data_limit": 100 * GB, "expire": 7 * 86400},
            {"data_limit": 5 * GB, "expire": 90 * 86400},
            # Missing or 0 values become unlimited when the plan is applied.
            {},
            {"data_limit": 0, "expire": 0},
            {"data_limit": 5 * GB},
            {"expire": 7 * 86400},
            # The remaining traffic is added on top, up to twice the role maximum.
            {"data_limit": 5 * GB, "expire": 7 * 86400, "add_remaining_traffic": True},
        ):
            response = _create_user_with_next_plan(token, next_plan)
            if response.status_code == status.HTTP_201_CREATED:
                created.append(response.json()["id"])
            assert response.status_code == status.HTTP_400_BAD_REQUEST, (next_plan, response.text)
            assert response.json()["detail"].startswith("Next plan"), response.text

        response = _create_user_with_next_plan(token, {"data_limit": 5 * GB, "expire": 7 * 86400})
        assert response.status_code == status.HTTP_201_CREATED, response.text
        user_id = response.json()["id"]
        created.append(user_id)

        response = client.post(f"/api/user/by-id/{user_id}/active_next", headers=auth_headers(token))
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["data_limit"] == 5 * GB
        assert response.json()["expire"] is not None
    finally:
        for user_id in created:
            client.delete(f"/api/user/by-id/{user_id}", headers=auth_headers(token))
        _drop_actor(access_token, role, admin)


def test_template_next_plan_with_dashboard_zeros_respects_only_the_template(access_token):
    # The dashboard sends expire/data_limit 0 next to user_template_id: the template supplies both.
    role, admin, token = _actor(
        access_token,
        _NEXT_PLAN_PERMISSIONS,
        limits={**_NEXT_PLAN_LIMITS, "expire_min": 86400, "data_limit_min": GB},
    )
    core = create_core(access_token)
    group = create_group(access_token, name=unique_name("next_plan_group"))
    template = create_user_template(access_token, group_ids=[group["id"]], data_limit=5 * GB, expire_duration=7 * 86400)
    user_id = None
    try:
        plan = {"user_template_id": template["id"], "data_limit": 0, "expire": 0}
        response = _create_user_with_next_plan(token, {**plan, "add_remaining_traffic": True})
        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text

        response = _create_user_with_next_plan(token, plan)
        assert response.status_code == status.HTTP_201_CREATED, response.text
        user_id = response.json()["id"]

        response = client.post(f"/api/user/by-id/{user_id}/active_next", headers=auth_headers(token))
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["data_limit"] == 5 * GB
    finally:
        if user_id is not None:
            client.delete(f"/api/user/by-id/{user_id}", headers=auth_headers(access_token))
        client.delete(f"/api/user_template/{template['id']}", headers=auth_headers(access_token))
        client.delete(f"/api/group/{group['id']}", headers=auth_headers(access_token))
        client.delete(f"/api/core/{core['id']}", headers=auth_headers(access_token))
        _drop_actor(access_token, role, admin)


def test_modify_refuses_an_unlimited_next_plan(access_token):
    role, admin, token = _actor(
        access_token,
        {"users": {**_NEXT_PLAN_PERMISSIONS["users"], "update": {"scope": 1}}},
        limits=_NEXT_PLAN_LIMITS,
    )
    user_id = None
    try:
        response = _create_user_with_next_plan(token, {"data_limit": 5 * GB, "expire": 7 * 86400})
        assert response.status_code == status.HTTP_201_CREATED, response.text
        user_id = response.json()["id"]

        for next_plan in ({}, {"data_limit": 0, "expire": 0}):
            response = client.put(
                f"/api/user/by-id/{user_id}", headers=auth_headers(token), json={"next_plan": next_plan}
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST, (next_plan, response.text)
            assert response.json()["detail"].startswith("Next plan"), response.text
        # Negative values never reach the role limits: the input model refuses them.
        for next_plan in ({"data_limit": -1, "expire": -1}, {"data_limit": 5 * GB, "expire": -1}):
            response = client.put(
                f"/api/user/by-id/{user_id}", headers=auth_headers(token), json={"next_plan": next_plan}
            )
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, (next_plan, response.text)

        response = client.put(f"/api/user/by-id/{user_id}", headers=auth_headers(token), json={"note": "only a note"})
        assert response.status_code == status.HTTP_200_OK, response.text
    finally:
        if user_id is not None:
            client.delete(f"/api/user/by-id/{user_id}", headers=auth_headers(access_token))
        _drop_actor(access_token, role, admin)


def test_stored_unlimited_next_plan_does_not_unlock_unlimited_user(access_token):
    role, admin, token = _actor(access_token, _NEXT_PLAN_PERMISSIONS, limits=_NEXT_PLAN_LIMITS)
    user_id = None
    try:
        response = _create_user_with_next_plan(token, {"data_limit": 5 * GB, "expire": 7 * 86400})
        assert response.status_code == status.HTTP_201_CREATED, response.text
        user_id = response.json()["id"]
        before = response.json()

        # Plans saved before the create-time check, e.g. by an older version.
        for stored in ({"data_limit": 0, "expire": 0}, {"data_limit": -1, "expire": -1}):
            _store_next_plan(user_id, **stored)

            response = client.post(f"/api/user/by-id/{user_id}/active_next", headers=auth_headers(token))
            assert response.status_code == status.HTTP_400_BAD_REQUEST, (stored, response.text)
            assert response.json()["detail"].startswith("Next plan"), response.text

        user = client.get(f"/api/user/by-id/{user_id}", headers=auth_headers(access_token)).json()
        assert user["data_limit"] == before["data_limit"] == GB
        assert user["expire"] is not None
    finally:
        if user_id is not None:
            client.delete(f"/api/user/by-id/{user_id}", headers=auth_headers(access_token))
        _drop_actor(access_token, role, admin)


def test_stored_negative_next_plan_still_loads_in_responses(access_token):
    role, admin, token = _actor(access_token, _NEXT_PLAN_PERMISSIONS, limits=_NEXT_PLAN_LIMITS)
    user_id = None
    try:
        response = _create_user_with_next_plan(token, {"data_limit": -1, "expire": 7 * 86400})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.text

        response = _create_user_with_next_plan(token, {"data_limit": 5 * GB, "expire": 7 * 86400})
        assert response.status_code == status.HTTP_201_CREATED, response.text
        user_id = response.json()["id"]
        _store_next_plan(user_id, data_limit=-1)

        response = client.get(f"/api/user/by-id/{user_id}", headers=auth_headers(token))
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["next_plan"]["data_limit"] == -1

        response = client.get("/api/users", headers=auth_headers(token))
        assert response.status_code == status.HTTP_200_OK, response.text
        assert user_id in [user["id"] for user in response.json()["users"]]
    finally:
        if user_id is not None:
            client.delete(f"/api/user/by-id/{user_id}", headers=auth_headers(access_token))
        _drop_actor(access_token, role, admin)

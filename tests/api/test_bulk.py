import asyncio
from datetime import UTC, datetime as dt, timedelta as td

from fastapi import status
from sqlalchemy import select

from app.db.models import User
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from tests.api import TestSession, client
from tests.api.helpers import (
    create_admin,
    create_core,
    create_group,
    create_user,
    delete_admin,
    delete_core,
    delete_group,
    delete_user,
    unique_name,
)


def setup_groups(access_token: str, count: int = 1):
    core = create_core(access_token)
    groups = [create_group(access_token, name=unique_name(f"bulk_group_{idx}")) for idx in range(count)]
    return core, groups


def cleanup(access_token: str, core: dict, groups: list[dict], users: list[dict]):
    for user in users:
        delete_user(access_token, user["username"])
    for group in groups:
        delete_group(access_token, group["id"])
    delete_core(access_token, core["id"])


def set_user_used_traffic(username: str, used_traffic: int) -> None:
    async def _set_usage():
        async with TestSession() as session:
            result = await session.execute(select(User).where(User.username == username))
            db_user = result.scalar_one()
            db_user.used_traffic = used_traffic
            await session.commit()

    asyncio.run(_set_usage())


def set_user_wireguard_keys(username: str, private_key: str, public_key: str) -> None:
    async def _set_keys():
        async with TestSession() as session:
            result = await session.execute(select(User).where(User.username == username))
            db_user = result.scalar_one()
            proxy_settings = dict(db_user.proxy_settings or {})
            wireguard_settings = dict(proxy_settings.get("wireguard") or {})
            wireguard_settings["private_key"] = private_key
            wireguard_settings["public_key"] = public_key
            proxy_settings["wireguard"] = wireguard_settings
            db_user.proxy_settings = proxy_settings
            await session.commit()

    asyncio.run(_set_keys())


def get_user_sub_revoked_at(username: str):
    async def _get_revoked_at():
        async with TestSession() as session:
            result = await session.execute(select(User).where(User.username == username))
            db_user = result.scalar_one()
            return db_user.sub_revoked_at

    return asyncio.run(_get_revoked_at())


def test_add_groups_to_users(access_token):
    """Test bulk adding groups to users."""

    core, groups = setup_groups(access_token, 2)
    users = [create_user(access_token, payload={"username": unique_name("bulk_user")}) for _ in range(2)]
    group_ids = [group["id"] for group in groups]
    try:
        response = client.post(
            "/api/groups/bulk/add",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"group_ids": group_ids},
        )

        assert response.status_code == status.HTTP_200_OK
        for user in users:
            response = client.get(f"/api/user/{user['username']}", headers={"Authorization": f"Bearer {access_token}"})
            assert set(response.json()["group_ids"]) == set(group_ids)
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_add_wireguard_group_allocates_existing_user_peer_ips(access_token):
    # Users must belong to a group at create time; start with a non-WG group, then bulk-add WG.
    starter_core, starter_groups = setup_groups(access_token, 1)
    starter_group = starter_groups[0]
    users: list[dict] = []
    wg_core = None
    wg_group = None
    try:
        users = [
            create_user(
                access_token,
                group_ids=[starter_group["id"]],
                payload={"username": unique_name("wg_bulk_add_existing_a")},
            ),
            create_user(
                access_token,
                group_ids=[starter_group["id"]],
                payload={"username": unique_name("wg_bulk_add_existing_b")},
            ),
        ]

        interface_private_key, _ = generate_wireguard_keypair()
        interface_name = unique_name("wg_bulk_add_group")
        wg_core = create_core(
            access_token,
            name=unique_name("wireguard_bulk_add_group_core"),
            config={
                "interface_name": interface_name,
                "private_key": interface_private_key,
                "listen_port": 51820,
                "address": ["10.61.0.1/24"],
            },
            type="wg",
            fallbacks=[],
        )
        wg_group = create_group(access_token, name=unique_name("wg_bulk_add_group"), inbound_tags=[interface_name])

        response = client.post(
            "/api/groups/bulk/add",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"group_ids": [wg_group["id"]], "users": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK

        allocated_peer_ips = []
        for user in users:
            user_response = client.get(
                f"/api/user/{user['username']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert user_response.status_code == status.HTTP_200_OK
            wireguard = user_response.json()["proxy_settings"]["wireguard"]
            assert wireguard["private_key"]
            assert wireguard["public_key"] == get_wireguard_public_key(wireguard["private_key"])
            assert len(wireguard["peer_ips"]) == 1
            allocated_peer_ips.append(wireguard["peer_ips"][0])

        assert len(set(allocated_peer_ips)) == len(users)
    finally:
        for user in users:
            delete_user(access_token, user["username"])
        if wg_group is not None:
            delete_group(access_token, wg_group["id"])
        if wg_core is not None:
            delete_core(access_token, wg_core["id"])
        cleanup(access_token, starter_core, starter_groups, [])


def test_remove_groups_from_users(access_token):
    """Test bulk removing groups from users."""
    core, groups = setup_groups(access_token, 2)
    users = [create_user(access_token, payload={"username": unique_name("bulk_user_remove")}) for _ in range(2)]
    group_ids = [group["id"] for group in groups]
    try:
        client.post(
            "/api/groups/bulk/add",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"group_ids": group_ids},
        )
        response = client.post(
            "/api/groups/bulk/remove",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"group_ids": [group_ids[0]]},
        )

        assert response.status_code == status.HTTP_200_OK
        for user in users:
            response = client.get(f"/api/user/{user['username']}", headers={"Authorization": f"Bearer {access_token}"})
            assert set(response.json()["group_ids"]) == {group_ids[1]}
    finally:
        cleanup(access_token, core, groups, users)


def test_update_users_datalimit(access_token):
    """Test bulk updating user data limits."""
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(
            access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user7"), "data_limit": 100}
        ),
        create_user(
            access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user8"), "data_limit": 200}
        ),
    ]
    user_ids = [user["id"] for user in users]
    try:
        response = client.post(
            "/api/users/bulk/data_limit",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "amount": 50,
                "users": user_ids,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        response = client.get("/api/users", headers={"Authorization": f"Bearer {access_token}"})
        listed = {u["id"]: u for u in response.json()["users"] if u["id"] in user_ids}
        assert listed[users[0]["id"]]["data_limit"] == 150
        assert listed[users[1]["id"]]["data_limit"] == 250
    finally:
        cleanup(access_token, core, groups, users)


def test_update_users_expire(access_token):
    """Test bulk updating user expiration dates."""
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user_expire1")}),
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user_expire2")}),
    ]
    client.put(
        f"/api/user/{users[0]['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": "2025-01-01T00:00:00+00:00"},
    )
    client.put(
        f"/api/user/{users[1]['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": "2026-01-01T00:00:00+00:00"},
    )

    try:
        response = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 3600},
        )

        assert response.status_code == status.HTTP_200_OK
        response = client.get("/api/users", headers={"Authorization": f"Bearer {access_token}"})
        listed = {
            u["username"]: u
            for u in response.json()["users"]
            if u["username"] in {users[0]["username"], users[1]["username"]}
        }
        assert (
            dt.fromisoformat(listed[users[0]["username"]]["expire"]).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
            == "2025-01-01T01:00:00"
        )
        assert (
            dt.fromisoformat(listed[users[1]["username"]]["expire"]).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
            == "2026-01-01T01:00:00"
        )
    finally:
        cleanup(access_token, core, groups, users)


def test_update_users_proxy_settings(access_token):
    """Test bulk updating user proxy settings."""
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user_proxy1")}),
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("user_proxy2")}),
    ]
    try:
        response = client.post(
            "/api/users/bulk/proxy_settings",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"method": "xchacha20-poly1305"},
        )

        assert response.status_code == status.HTTP_200_OK
        response = client.get("/api/users", headers={"Authorization": f"Bearer {access_token}"})
        listed = {
            u["username"]: u
            for u in response.json()["users"]
            if u["username"] in {users[0]["username"], users[1]["username"]}
        }
        assert listed[users[0]["username"]]["proxy_settings"]["shadowsocks"]["method"] == "xchacha20-poly1305"
        assert listed[users[1]["username"]]["proxy_settings"]["shadowsocks"]["method"] == "xchacha20-poly1305"
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_expire_with_range(access_token):
    # Setup
    core = create_core(access_token)
    group = create_group(access_token, name=unique_name("bulk_range_group"))

    # Create two users, both expired, but at different times
    # User 1: expired 2 days ago
    # User 2: expired 10 days ago

    now = dt.now(UTC).replace(microsecond=0)
    expire1 = now - td(days=2)
    expire2 = now - td(days=10)

    user1 = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("exp_range1")})
    user2 = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("exp_range2")})

    # Manually set them to expired status by setting expire date in the past
    # Note: the API might return slightly different formatted strings, so we use isoformat
    client.put(
        f"/api/user/{user1['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": expire1.isoformat()},
    )
    client.put(
        f"/api/user/{user2['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": expire2.isoformat()},
    )

    try:
        # Bulk modify expire for those expired between 1 and 3 days ago (should only target user1)
        expired_after = now - td(days=3)
        expired_before = now - td(days=1)

        response = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "amount": 3600,  # Add 1 hour
                "expire_after": expired_after.isoformat(),
                "expire_before": expired_before.isoformat(),
            },
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify user1 was updated
        resp1 = client.get(f"/api/user/{user1['username']}", headers={"Authorization": f"Bearer {access_token}"})
        new_expire1 = dt.fromisoformat(resp1.json()["expire"])
        # Should be approximately expire1 + 1 hour
        assert (new_expire1 - expire1).total_seconds() == 3600

        # Verify user2 was NOT updated
        resp2 = client.get(f"/api/user/{user2['username']}", headers={"Authorization": f"Bearer {access_token}"})
        new_expire2 = dt.fromisoformat(resp2.json()["expire"])
        # Should be exactly expire2 (or very close)
        assert abs((new_expire2 - expire2).total_seconds()) < 1

    finally:
        delete_user(access_token, user1["username"])
        delete_user(access_token, user2["username"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_bulk_expire_anchor_now(access_token):
    """anchor='now' sets expire relative to the current time, ignoring the user's existing expire date."""
    core = create_core(access_token)
    group = create_group(access_token, name=unique_name("bulk_anchor_now_group"))

    now = dt.now(UTC).replace(microsecond=0)
    expired_8_days_ago = now - td(days=8)

    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("anchor_now")})
    client.put(
        f"/api/user/{user['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": expired_8_days_ago.isoformat()},
    )

    try:
        response = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 5 * 24 * 3600, "anchor": "now", "users": [user["id"]]},
        )
        assert response.status_code == status.HTTP_200_OK

        resp = client.get(f"/api/user/{user['username']}", headers={"Authorization": f"Bearer {access_token}"})
        data = resp.json()
        new_expire = dt.fromisoformat(data["expire"])
        expected_expire = now + td(days=5)
        # New expire should be ~now + amount, not old_expire + amount
        assert abs((new_expire - expected_expire).total_seconds()) < 5
        assert data["status"] == "active"
    finally:
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_bulk_expire_anchor_now_initializes_unlimited_users(access_token):
    """An absolute anchor gives unlimited users an expire date instead of skipping them.

    anchor="now" is documented as applying to every matched user "regardless of their current
    expire date", so a user with expire=None is a legitimate target: there is nothing to extend,
    but now + amount is still well defined. Covers the id, group and admin filters, and confirms
    an untargeted user with an existing expire is left alone.
    """
    core, groups = setup_groups(access_token, 2)
    admin = create_admin(access_token)
    id_user = create_user(access_token, group_ids=[groups[1]["id"]], payload={"username": unique_name("expire_id")})
    group_user = create_user(
        access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("expire_group")}
    )
    admin_user = create_user(
        access_token, group_ids=[groups[1]["id"]], payload={"username": unique_name("expire_admin")}
    )
    normal_user = create_user(
        access_token, group_ids=[groups[1]["id"]], payload={"username": unique_name("expire_normal")}
    )
    users = [id_user, group_user, admin_user, normal_user]
    normal_expire = dt(2030, 1, 1, tzinfo=UTC)

    try:
        set_owner = client.put(
            f"/api/user/{admin_user['username']}/set_owner",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"admin_username": admin["username"]},
        )
        assert set_owner.status_code == status.HTTP_200_OK
        set_expire = client.put(
            f"/api/user/{normal_user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"expire": normal_expire.isoformat()},
        )
        assert set_expire.status_code == status.HTTP_200_OK

        # The unlimited user in groups[0] must be counted as a target, not filtered out.
        dry_run = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 3600, "anchor": "now", "group_ids": [groups[0]["id"]], "dry_run": True},
        )
        assert dry_run.status_code == status.HTTP_200_OK
        assert dry_run.json()["affected_users"] == 1

        before_id = dt.now(UTC)
        by_id = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 3600, "anchor": "now", "users": [id_user["id"]]},
        )
        after_id = dt.now(UTC)
        assert by_id.status_code == status.HTTP_200_OK

        before_group = dt.now(UTC)
        by_group = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 3600, "anchor": "now", "group_ids": [groups[0]["id"]]},
        )
        after_group = dt.now(UTC)
        assert by_group.status_code == status.HTTP_200_OK

        # A negative amount lands in the past, so the newly dated user must flip to expired.
        before_admin = dt.now(UTC)
        by_admin = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": -3600, "anchor": "now", "admins": [admin["id"]]},
        )
        after_admin = dt.now(UTC)
        assert by_admin.status_code == status.HTTP_200_OK

        def get_user(user):
            response = client.get(f"/api/user/{user['username']}", headers={"Authorization": f"Bearer {access_token}"})
            assert response.status_code == status.HTTP_200_OK
            return response.json()

        id_expire = dt.fromisoformat(get_user(id_user)["expire"])
        group_expire = dt.fromisoformat(get_user(group_user)["expire"])
        admin_result = get_user(admin_user)
        admin_expire = dt.fromisoformat(admin_result["expire"])
        normal_result = get_user(normal_user)

        assert before_id + td(seconds=3599) <= id_expire <= after_id + td(seconds=3601)
        assert before_group + td(seconds=3599) <= group_expire <= after_group + td(seconds=3601)
        assert before_admin - td(seconds=3601) <= admin_expire <= after_admin - td(seconds=3599)
        assert admin_result["status"] == "expired"
        assert dt.fromisoformat(normal_result["expire"]) == normal_expire
    finally:
        cleanup(access_token, core, groups, users)
        delete_admin(access_token, admin["username"])


def test_bulk_expire_anchor_expire_skips_unlimited_users(access_token):
    """anchor="expire" extends each user's own expire date, so a user without one has no base
    to extend and must still be skipped -- the default anchor keeps its original semantics."""
    core, groups = setup_groups(access_token, 1)
    unlimited = create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("expire_skip")})

    try:
        dry_run = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 3600, "group_ids": [groups[0]["id"]], "dry_run": True},
        )
        assert dry_run.status_code == status.HTTP_200_OK
        assert dry_run.json()["affected_users"] == 0

        applied = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 3600, "group_ids": [groups[0]["id"]]},
        )
        assert applied.status_code == status.HTTP_200_OK

        response = client.get(f"/api/user/{unlimited['username']}", headers={"Authorization": f"Bearer {access_token}"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["expire"] is None
    finally:
        cleanup(access_token, core, groups, [unlimited])


def test_bulk_expire_absolute_anchor_skips_on_hold_users(access_token):
    """On-hold users also have expire=None, but must not be given one by an absolute anchor.

    Their expiry comes from on_hold_expire_duration -- start_user_expire() overwrites expire when
    they first come online -- so a value written here would be reported as applied and then
    silently discarded.
    """
    core, groups = setup_groups(access_token, 1)
    on_hold = create_user(
        access_token,
        group_ids=[groups[0]["id"]],
        payload={"username": unique_name("expire_on_hold"), "status": "on_hold", "on_hold_expire_duration": 86400},
    )

    try:
        dry_run = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 3600, "anchor": "now", "group_ids": [groups[0]["id"]], "dry_run": True},
        )
        assert dry_run.status_code == status.HTTP_200_OK
        assert dry_run.json()["affected_users"] == 0

        applied = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 3600, "anchor": "now", "group_ids": [groups[0]["id"]]},
        )
        assert applied.status_code == status.HTTP_200_OK

        response = client.get(f"/api/user/{on_hold['username']}", headers={"Authorization": f"Bearer {access_token}"})
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["expire"] is None
        assert result["status"] == "on_hold"
        assert result["on_hold_expire_duration"] == 86400
    finally:
        cleanup(access_token, core, groups, [on_hold])


def test_bulk_expire_anchor_unix_timestamp(access_token):
    """anchor=<unix timestamp> sets expire relative to that instant, not the current server time.

    This makes the operation idempotent against downtime: replaying the same call with the same
    anchor + amount always produces the same expire date, regardless of when it actually runs.
    """
    core = create_core(access_token)
    group = create_group(access_token, name=unique_name("bulk_anchor_ts_group"))

    now = dt.now(UTC).replace(microsecond=0)
    anchor_time = now - td(days=30)
    expired_8_days_ago = now - td(days=8)

    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("anchor_ts")})
    client.put(
        f"/api/user/{user['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": expired_8_days_ago.isoformat()},
    )

    try:
        response = client.post(
            "/api/users/bulk/expire",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 5 * 24 * 3600, "anchor": int(anchor_time.timestamp()), "users": [user["id"]]},
        )
        assert response.status_code == status.HTTP_200_OK

        resp = client.get(f"/api/user/{user['username']}", headers={"Authorization": f"Bearer {access_token}"})
        data = resp.json()
        new_expire = dt.fromisoformat(data["expire"])
        expected_expire = anchor_time + td(days=5)
        # New expire should be ~anchor_time + amount, not now + amount and not old_expire + amount
        assert abs((new_expire - expected_expire).total_seconds()) < 5
    finally:
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_bulk_expire_anchor_negative_timestamp_rejected(access_token):
    response = client.post(
        "/api/users/bulk/expire",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"amount": 3600, "anchor": -1},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_bulk_expire_anchor_out_of_range_timestamp_rejected(access_token):
    """A timestamp beyond what datetime can represent must be a clean 422, not an unhandled 500."""
    response = client.post(
        "/api/users/bulk/expire",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"amount": 3600, "anchor": 253402300800},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_bulk_data_limit_with_expire_range_without_expired_status(access_token):
    core = create_core(access_token)
    group = create_group(access_token, name=unique_name("bulk_data_range_group"))

    now = dt.now(UTC).replace(microsecond=0)
    expire1 = now - td(days=2)
    expire2 = now - td(days=10)

    user1 = create_user(
        access_token,
        group_ids=[group["id"]],
        payload={"username": unique_name("data_range1"), "data_limit": 100},
    )
    user2 = create_user(
        access_token,
        group_ids=[group["id"]],
        payload={"username": unique_name("data_range2"), "data_limit": 200},
    )

    client.put(
        f"/api/user/{user1['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": expire1.isoformat()},
    )
    client.put(
        f"/api/user/{user2['username']}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expire": expire2.isoformat()},
    )

    try:
        expired_after = now - td(days=3)
        expired_before = now - td(days=1)

        response = client.post(
            "/api/users/bulk/data_limit",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "amount": 50,
                "expire_after": expired_after.isoformat(),
                "expire_before": expired_before.isoformat(),
            },
        )
        assert response.status_code == status.HTTP_200_OK

        resp1 = client.get(f"/api/user/{user1['username']}", headers={"Authorization": f"Bearer {access_token}"})
        resp2 = client.get(f"/api/user/{user2['username']}", headers={"Authorization": f"Bearer {access_token}"})
        assert resp1.json()["data_limit"] == 150
        assert resp2.json()["data_limit"] == 200

    finally:
        delete_user(access_token, user1["username"])
        delete_user(access_token, user2["username"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_bulk_expire_dry_run(access_token):
    """Dry-run returns affected user count without modifying users."""
    response = client.post(
        "/api/users/bulk/expire",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"amount": 3600, "dry_run": True},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["dry_run"] is True
    assert "affected_users" in data


def test_bulk_delete_users_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_delete")})
        for _ in range(2)
    ]
    try:
        response = client.post(
            "/api/users/bulk/delete",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)

        lookup = client.get(
            "/api/users",
            params={"username": [user["username"] for user in users]},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert lookup.status_code == status.HTTP_200_OK
        assert lookup.json()["users"] == []
    finally:
        cleanup(access_token, core, groups, [])


def test_bulk_reset_users_usage_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_reset")})
        for _ in range(2)
    ]
    try:
        for index, user in enumerate(users, start=1):
            set_user_used_traffic(user["username"], index * 1024)

        response = client.post(
            "/api/users/bulk/reset",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)

        for user in users:
            user_response = client.get(
                f"/api/user/{user['username']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["used_traffic"] == 0
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_revoke_users_subscription_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_revoke")})
        for _ in range(2)
    ]
    try:
        response = client.post(
            "/api/users/bulk/revoke_sub",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)
        for user in users:
            assert get_user_sub_revoked_at(user["username"]) is not None
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_revoke_users_subscription_regenerates_wireguard_keys(access_token):
    interface_private_key, _ = generate_wireguard_keypair()
    interface_name = unique_name("wg_bulk_revoke")
    core = create_core(
        access_token,
        name=unique_name("wireguard_bulk_revoke_core"),
        config={
            "interface_name": interface_name,
            "private_key": interface_private_key,
            "listen_port": 51820,
            "address": ["10.46.0.1/24"],
        },
        type="wg",
        fallbacks=[],
    )
    group = create_group(access_token, name=unique_name("wg_bulk_revoke_group"), inbound_tags=[interface_name])
    users = [
        create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("wg_bulk_revoke_user")})
        for _ in range(2)
    ]
    old_wireguard_by_username = {user["username"]: user["proxy_settings"]["wireguard"] for user in users}

    try:
        for wireguard in old_wireguard_by_username.values():
            assert wireguard["private_key"]
            assert wireguard["public_key"] == get_wireguard_public_key(wireguard["private_key"])
            assert wireguard["peer_ips"]

        response = client.post(
            "/api/users/bulk/revoke_sub",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == len(users)

        for user in users:
            assert get_user_sub_revoked_at(user["username"]) is not None
            user_response = client.get(
                f"/api/user/{user['username']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert user_response.status_code == status.HTTP_200_OK

            old_wireguard = old_wireguard_by_username[user["username"]]
            wireguard = user_response.json()["proxy_settings"]["wireguard"]
            assert wireguard["private_key"]
            assert wireguard["public_key"] == get_wireguard_public_key(wireguard["private_key"])
            assert wireguard["private_key"] != old_wireguard["private_key"]
            assert wireguard["public_key"] != old_wireguard["public_key"]
            assert wireguard["peer_ips"] == old_wireguard["peer_ips"]
    finally:
        cleanup(access_token, core, [group], users)


def test_bulk_disable_users_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_disable")})
        for _ in range(2)
    ]
    try:
        response = client.post(
            "/api/users/bulk/disable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)

        for user in users:
            user_response = client.get(
                f"/api/user/{user['username']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["status"] == "disabled"
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_enable_users_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_enable")})
        for _ in range(2)
    ]
    try:
        disable_response = client.post(
            "/api/users/bulk/disable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )
        assert disable_response.status_code == status.HTTP_200_OK

        response = client.post(
            "/api/users/bulk/enable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)

        for user in users:
            user_response = client.get(
                f"/api/user/{user['username']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["status"] == "active"
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_disable_enable_users_ignore_noops(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_noop")})
        for _ in range(2)
    ]
    try:
        first_user = users[0]
        second_user = users[1]
        disable_single_response = client.put(
            f"/api/user/{first_user['username']}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"status": "disabled"},
        )
        assert disable_single_response.status_code == status.HTTP_200_OK

        disable_bulk_response = client.post(
            "/api/users/bulk/disable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [first_user["id"], second_user["id"]]},
        )
        assert disable_bulk_response.status_code == status.HTTP_200_OK
        assert disable_bulk_response.json()["count"] == 1

        enable_bulk_response = client.post(
            "/api/users/bulk/enable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [first_user["id"], second_user["id"]]},
        )
        assert enable_bulk_response.status_code == status.HTTP_200_OK
        assert enable_bulk_response.json()["count"] == 2

        enable_again_response = client.post(
            "/api/users/bulk/enable",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [first_user["id"], second_user["id"]]},
        )
        assert enable_again_response.status_code == status.HTTP_200_OK
        assert enable_again_response.json()["count"] == 0
    finally:
        cleanup(access_token, core, groups, users)


def test_bulk_set_owner_by_ids(access_token):
    core, groups = setup_groups(access_token, 1)
    users = [
        create_user(access_token, group_ids=[groups[0]["id"]], payload={"username": unique_name("bulk_owner")})
        for _ in range(2)
    ]
    new_owner = create_admin(access_token)
    try:
        response = client.put(
            "/api/users/bulk/set_owner",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"ids": [user["id"] for user in users], "admin_username": new_owner["username"]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == len(users)

        for user in users:
            user_response = client.get(
                f"/api/user/{user['username']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert user_response.status_code == status.HTTP_200_OK
            assert user_response.json()["admin"]["username"] == new_owner["username"]
    finally:
        cleanup(access_token, core, groups, users)
        delete_admin(access_token, new_owner["username"])

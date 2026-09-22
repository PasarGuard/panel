import asyncio

from fastapi import status
from sqlalchemy import select

from app.db.models import User
from app.node.user import core_users
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_core,
    create_group,
    create_user,
    delete_core,
    delete_group,
    delete_user,
    unique_name,
)

XRAY_TAG = "VLESS WebSocket TEST"


def _create_wireguard_core(access_token: str, interface_name: str, address: str) -> dict:
    private_key, _ = generate_wireguard_keypair()
    return create_core(
        access_token,
        name=unique_name("wg_keys_core"),
        config={
            "interface_name": interface_name,
            "private_key": private_key,
            "listen_port": 51820,
            "address": [address],
        },
        type="wg",
        fallbacks=[],
    )


def _create_base_user(access_token: str, group_id: int, wireguard: dict | None = None) -> dict:
    payload = {"username": unique_name("wg_keys_user")}
    if wireguard is not None:
        payload["proxy_settings"] = {"wireguard": wireguard}
    return create_user(access_token, group_ids=[group_id], payload=payload)


def _get_wireguard(access_token: str, username: str) -> dict:
    response = client.get(f"/api/user/{username}", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    return response.json()["proxy_settings"]["wireguard"]


def _store_private_key_only(username: str, private_key: str) -> None:
    async def _store():
        async with TestSession() as session:
            db_user = (await session.execute(select(User).where(User.username == username))).scalar_one()
            proxy_settings = dict(db_user.proxy_settings or {})
            proxy_settings["wireguard"] = {"private_key": private_key, "public_key": None, "peer_ips": []}
            db_user.proxy_settings = proxy_settings
            await session.commit()

    asyncio.run(_store())


def _node_public_keys(interface_name: str, user_ids: list[int]) -> list[str]:
    async def _collect():
        async with TestSession() as session:
            users = await core_users(session, inbound_tags=[interface_name])
            wanted = {str(user_id) for user_id in user_ids}
            return [user.proxies.wireguard.public_key for user in users if user.email in wanted]

    return asyncio.run(_collect())


def _add_group_to_users(access_token: str, group_id: int, user_ids: list[int]) -> None:
    response = client.post(
        "/api/groups/bulk/add",
        headers=auth_headers(access_token),
        json={"group_ids": [group_id], "users": user_ids},
    )
    assert response.status_code == status.HTTP_200_OK


def _add_inbound_to_group(access_token: str, group: dict, inbound_tag: str) -> None:
    response = client.put(
        f"/api/group/{group['id']}",
        headers=auth_headers(access_token),
        json={"name": group["name"], "inbound_tags": [*group["inbound_tags"], inbound_tag]},
    )
    assert response.status_code == status.HTTP_200_OK


class _WireGuardSetup:
    def __init__(self, access_token: str, address: str):
        self.access_token = access_token
        self.xray_core = create_core(access_token, name=unique_name("wg_keys_xray"))
        self.base_group = create_group(access_token, name=unique_name("wg_keys_base"), inbound_tags=[XRAY_TAG])
        self.interface_name = unique_name("wg_keys_if")
        self.wg_core = _create_wireguard_core(access_token, self.interface_name, address)
        self.wg_group = create_group(access_token, name=unique_name("wg_keys_wg"), inbound_tags=[self.interface_name])
        self.users: list[dict] = []

    def user(self, wireguard: dict | None = None) -> dict:
        user = _create_base_user(self.access_token, self.base_group["id"], wireguard)
        self.users.append(user)
        return user

    def close(self) -> None:
        for user in self.users:
            delete_user(self.access_token, user["username"])
        delete_group(self.access_token, self.wg_group["id"])
        delete_group(self.access_token, self.base_group["id"])
        delete_core(self.access_token, self.wg_core["id"])
        delete_core(self.access_token, self.xray_core["id"])


def test_users_sharing_a_keypair_become_distinct_peers_when_granted_wireguard(access_token):
    setup = _WireGuardSetup(access_token, "10.91.0.1/24")
    try:
        private_key, public_key = generate_wireguard_keypair()
        shared = {"private_key": private_key, "public_key": public_key}
        users = [setup.user(shared), setup.user(shared)]
        user_ids = [user["id"] for user in users]

        _add_group_to_users(access_token, setup.wg_group["id"], user_ids)

        node_keys = _node_public_keys(setup.interface_name, user_ids)
        assert len(node_keys) == 2
        assert len(set(node_keys)) == 2

        settings = [_get_wireguard(access_token, user["username"]) for user in users]
        assert all(wg["peer_ips"] for wg in settings)
        assert settings[0]["public_key"] != settings[1]["public_key"]
        for wg in settings:
            assert get_wireguard_public_key(wg["private_key"]) == wg["public_key"]
    finally:
        setup.close()


def test_users_sharing_a_private_key_become_distinct_peers_when_their_group_gains_wireguard(access_token):
    setup = _WireGuardSetup(access_token, "10.92.0.1/24")
    try:
        private_key, _ = generate_wireguard_keypair()
        users = [setup.user(), setup.user()]
        for user in users:
            _store_private_key_only(user["username"], private_key)

        _add_inbound_to_group(access_token, setup.base_group, setup.interface_name)

        user_ids = [user["id"] for user in users]
        node_keys = _node_public_keys(setup.interface_name, user_ids)
        assert len(node_keys) == 2
        assert len(set(node_keys)) == 2

        settings = [_get_wireguard(access_token, user["username"]) for user in users]
        assert all(wg["peer_ips"] for wg in settings)
        assert settings[0]["public_key"] != settings[1]["public_key"]
        for wg in settings:
            assert get_wireguard_public_key(wg["private_key"]) == wg["public_key"]
    finally:
        setup.close()


def test_a_keypair_held_by_another_user_is_replaced_and_the_holder_keeps_it(access_token):
    setup = _WireGuardSetup(access_token, "10.93.0.1/24")
    try:
        private_key, public_key = generate_wireguard_keypair()
        shared = {"private_key": private_key, "public_key": public_key}
        holder, newcomer = setup.user(shared), setup.user(shared)

        _add_group_to_users(access_token, setup.wg_group["id"], [newcomer["id"]])

        newcomer_wg = _get_wireguard(access_token, newcomer["username"])
        assert newcomer_wg["peer_ips"]
        assert newcomer_wg["public_key"] != public_key
        assert newcomer_wg["private_key"] != private_key
        assert get_wireguard_public_key(newcomer_wg["private_key"]) == newcomer_wg["public_key"]

        _add_group_to_users(access_token, setup.wg_group["id"], [holder["id"]])

        holder_wg = _get_wireguard(access_token, holder["username"])
        assert holder_wg["peer_ips"]
        assert holder_wg["private_key"] == private_key
        assert holder_wg["public_key"] == public_key
    finally:
        setup.close()


def test_an_unshared_keypair_is_kept_when_granted_wireguard(access_token):
    setup = _WireGuardSetup(access_token, "10.94.0.1/24")
    try:
        private_key, public_key = generate_wireguard_keypair()
        user = setup.user({"private_key": private_key, "public_key": public_key})

        _add_group_to_users(access_token, setup.wg_group["id"], [user["id"]])

        wg = _get_wireguard(access_token, user["username"])
        assert wg["peer_ips"]
        assert wg["private_key"] == private_key
        assert wg["public_key"] == public_key
    finally:
        setup.close()


def test_a_missing_public_key_is_derived_when_granted_wireguard(access_token):
    setup = _WireGuardSetup(access_token, "10.95.0.1/24")
    try:
        private_key, public_key = generate_wireguard_keypair()
        user = setup.user()
        _store_private_key_only(user["username"], private_key)

        _add_group_to_users(access_token, setup.wg_group["id"], [user["id"]])

        wg = _get_wireguard(access_token, user["username"])
        assert wg["peer_ips"]
        assert wg["private_key"] == private_key
        assert wg["public_key"] == public_key
    finally:
        setup.close()

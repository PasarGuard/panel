from PasarGuardNodeBridge import create_proxy, create_user
from sqlalchemy import select
from sqlalchemy.orm import load_only, selectinload

from app.db import AsyncSession
from app.db.models import Group, ProxyInbound, User, UserStatus


def serialize_user_for_node(id: int, username: str, user_settings: dict, inbounds: list[str] = None):
    vmess_settings = user_settings.get("vmess", {})
    vless_settings = user_settings.get("vless", {})
    trojan_settings = user_settings.get("trojan", {})
    shadowsocks_settings = user_settings.get("shadowsocks", {})

    return create_user(
        f"{id}.{username}",
        create_proxy(
            vmess_id=vmess_settings.get("id"),
            vless_id=vless_settings.get("id"),
            vless_flow=vless_settings.get("flow"),
            trojan_password=trojan_settings.get("password"),
            shadowsocks_password=shadowsocks_settings.get("password"),
            shadowsocks_method=shadowsocks_settings.get("method"),
        ),
        inbounds,
    )


async def core_users(db: AsyncSession):
    stmt = (
        select(User)
        .options(
            load_only(User.id, User.username, User.proxy_settings),
            selectinload(User.groups),
            selectinload(User.groups).selectinload(Group.inbounds).load_only(ProxyInbound.tag),
        )
        .where(User.status.in_([UserStatus.active, UserStatus.on_hold]))
    )
    users = (await db.execute(stmt)).unique().scalars().all()
    bridge_users: list = []

    for user in users:
        inbounds_list = await user.inbounds()
        if len(inbounds_list) > 0:
            bridge_users.append(serialize_user_for_node(user.id, user.username, user.proxy_settings, inbounds_list))

    return bridge_users


async def serialize_users_for_node(users: list[User]):
    bridge_users: list = []

    for user in users:
        inbounds_list = []
        if user.status in [UserStatus.active, UserStatus.on_hold]:
            inbounds_list = await user.inbounds()

        bridge_users.append(serialize_user_for_node(user.id, user.username, user.proxy_settings, inbounds_list))

    return bridge_users

from PasarGuardNodeBridge import create_proxy, create_user
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser
from sqlalchemy import and_, func, select

from app.db import AsyncSession
from app.db.models import Group, ProxyInbound, User, UserStatus, inbounds_groups_association, users_groups_association


def _inbounds_from_loaded_groups(user: User) -> list[str] | None:
    loaded_groups = user.__dict__.get("groups")
    if loaded_groups is None:
        return None

    tags: set[str] = set()
    for group in loaded_groups:
        if group.is_disabled:
            continue

        loaded_inbounds = group.__dict__.get("inbounds")
        if loaded_inbounds is None:
            return None

        for inbound in loaded_inbounds:
            tags.add(inbound.tag)

    return list(tags)


async def serialize_user(user: User) -> ProtoUser:
    user_settings = user.proxy_settings
    inbounds = None
    status = user.__dict__.get("status")
    if status is None:
        status = await user.awaitable_attrs.status

    if status in (UserStatus.active, UserStatus.on_hold):
        inbounds = _inbounds_from_loaded_groups(user)
        if inbounds is None:
            inbounds = await user.inbounds()

    return _serialize_user_for_node(user.id, user.username, user_settings, inbounds)


def _serialize_user_for_node(id: int, username: str, user_settings: dict, inbounds: list[str] = None) -> ProtoUser:
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
    dialect = db.bind.dialect.name

    # Use dialect-specific aggregation and grouping
    if dialect == "postgresql":
        inbound_agg = func.string_agg(ProxyInbound.tag.distinct(), ",").label("inbound_tags")
    else:
        # MySQL and SQLite use group_concat
        inbound_agg = func.group_concat(ProxyInbound.tag.distinct()).label("inbound_tags")

    stmt = (
        select(
            User.id,
            User.username,
            User.proxy_settings,
            inbound_agg,
        )
        .outerjoin(users_groups_association, User.id == users_groups_association.c.user_id)
        .outerjoin(
            Group,
            and_(
                users_groups_association.c.groups_id == Group.id,
                Group.is_disabled.is_(False),
            ),
        )
        .outerjoin(inbounds_groups_association, Group.id == inbounds_groups_association.c.group_id)
        .outerjoin(ProxyInbound, inbounds_groups_association.c.inbound_id == ProxyInbound.id)
        .where(User.status.in_([UserStatus.active, UserStatus.on_hold]))
        .group_by(User.id)
    )

    results = (await db.execute(stmt)).all()
    bridge_users: list = []

    for row in results:
        inbound_tags = row.inbound_tags.split(",") if row.inbound_tags else []
        if inbound_tags:
            bridge_users.append(_serialize_user_for_node(row.id, row.username, row.proxy_settings, inbound_tags))
    return bridge_users


async def serialize_users_for_node(users: list[User]) -> list[ProtoUser]:
    bridge_users: list = []

    for user in users:
        inbounds_list = []
        if user.status in [UserStatus.active, UserStatus.on_hold]:
            loaded_inbounds = _inbounds_from_loaded_groups(user)
            if loaded_inbounds is None:
                inbounds_list = await user.inbounds()
            else:
                inbounds_list = loaded_inbounds

        bridge_users.append(_serialize_user_for_node(user.id, user.username, user.proxy_settings, inbounds_list))

    return bridge_users

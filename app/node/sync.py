from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import GetDB
from app.db.models import Group, User
from app.models.user import UserNotificationResponse
from app.nats.node_rpc import node_nats_client
from app.nats.proto_utils import serialize_proto_message, serialize_proto_messages
from app.node import node_manager
from app.node.user import serialize_users_for_node, serialize_user, _serialize_user_for_node
from config import ROLE

if ROLE.runs_node:

    async def _dispatch_user_update(proto_user):
        await node_manager.update_user(proto_user)

    async def _dispatch_users_update(proto_users):
        await node_manager.update_users(proto_users)

    async def sync_user(db_user: User) -> None:
        proto_user = await serialize_user(db_user)
        await _dispatch_user_update(proto_user)

    async def remove_user(user: UserNotificationResponse) -> None:
        proto_user = _serialize_user_for_node(user.id, user.username, user.proxy_settings.dict())
        await _dispatch_user_update(proto_user)

    async def sync_users(users: list[User]) -> None:
        proto_users = await serialize_users_for_node(users)
        await _dispatch_users_update(proto_users)

else:

    async def _dispatch_user_update(proto_user):
        user_dict = serialize_proto_message(proto_user)
        await node_nats_client.publish("update_user", {"user": user_dict})

    async def _dispatch_users_update(proto_users):
        users_dicts = serialize_proto_messages(proto_users)
        await node_nats_client.publish("update_users", {"users": users_dicts})

    async def sync_user(db_user: User) -> None:
        proto_user = await serialize_user(db_user)
        await _dispatch_user_update(proto_user)

    async def remove_user(user: UserNotificationResponse) -> None:
        proto_user = _serialize_user_for_node(user.id, user.username, user.proxy_settings.dict())
        await _dispatch_user_update(proto_user)

    async def sync_users(users: list[User]) -> None:
        proto_users = await serialize_users_for_node(users)
        await _dispatch_users_update(proto_users)


async def sync_user_by_id(user_id: int) -> None:
    """
    Background-safe user sync that does not rely on request-scoped DB sessions.
    """
    async with GetDB() as db:
        stmt = (
            select(User)
            .options(selectinload(User.groups).selectinload(Group.inbounds))
            .where(User.id == user_id)
        )
        db_user = (await db.execute(stmt)).unique().scalar_one_or_none()

        if db_user is None:
            return

        proto_user = await serialize_user(db_user)

    await _dispatch_user_update(proto_user)


async def sync_users_by_ids(user_ids: list[int]) -> None:
    """
    Background-safe bulk user sync using a fresh DB session.
    """
    if not user_ids:
        return

    unique_user_ids = list(dict.fromkeys(user_ids))

    async with GetDB() as db:
        stmt = (
            select(User)
            .options(selectinload(User.groups).selectinload(Group.inbounds))
            .where(User.id.in_(unique_user_ids))
        )
        db_users = list((await db.execute(stmt)).unique().scalars().all())

        if not db_users:
            return

        proto_users = await serialize_users_for_node(db_users)

    await _dispatch_users_update(proto_users)

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.models.user import UserNotificationResponse
from app.nats.node_rpc import node_nats_client
from app.nats.proto_utils import serialize_proto_message, serialize_proto_messages
from app.node import node_manager
from app.node.user import serialize_users_for_node, serialize_user, _serialize_user_for_node
from app.utils.logger import get_logger
from config import runtime_settings

logger = get_logger("node-sync")


if runtime_settings.role.runs_node:

    async def _dispatch_user_update(proto_user):
        await node_manager.update_user(proto_user)

    async def _dispatch_users_update(proto_users):
        await node_manager.update_users(proto_users)

else:

    async def _dispatch_user_update(proto_user):
        user_dict = serialize_proto_message(proto_user)
        await node_nats_client.publish("update_user", {"user": user_dict})

    async def _dispatch_users_update(proto_users):
        users_dicts = serialize_proto_messages(proto_users)
        await node_nats_client.publish("update_users", {"users": users_dicts})


async def sync_user(db_user: User) -> None:
    if db_user.admin_id and db_user.admin.users_sync_blocked:
        return

    proto_user = await serialize_user(db_user)
    asyncio.create_task(_dispatch_user_update(proto_user))


async def remove_user(user: UserNotificationResponse) -> None:
    proto_user = _serialize_user_for_node(user.id, user.username, user.proxy_settings.dict())
    asyncio.create_task(_dispatch_user_update(proto_user))


async def remove_users(users: list[User]) -> None:
    """Remove multiple users from nodes in a single batch dispatch."""
    if not users:
        return
    proto_users = await serialize_users_for_node(users)
    asyncio.create_task(_dispatch_users_update(proto_users))


async def sync_users(users: list[User], db: AsyncSession) -> None:
    """Sync users to nodes, excluding users of limited admins with disable_users_when_limited=True."""
    from app.db.crud.admin import get_limited_admin_ids_with_user_sync

    excluded_admin_ids = await get_limited_admin_ids_with_user_sync(db)
    proto_users = await serialize_users_for_node(users, excluded_admin_ids=excluded_admin_ids)
    asyncio.create_task(_dispatch_users_update(proto_users))

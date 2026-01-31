from app.db.models import User
from app.models.user import UserNotificationResponse
from app.nats.node_rpc import node_nats_client
from app.nats.proto_utils import serialize_proto_message, serialize_proto_messages
from app.node import node_manager
from app.node.user import serialize_users_for_node, serialize_user, _serialize_user_for_node
from config import IS_NODE_WORKER

if IS_NODE_WORKER:

    async def sync_user(db_user: User) -> None:
        proto_user = await serialize_user(db_user)
        await node_manager.update_user(proto_user)

    async def remove_user(user: UserNotificationResponse) -> None:
        proto_user = _serialize_user_for_node(user.id, user.username, user.proxy_settings.dict())
        await node_manager.update_user(proto_user)

    async def sync_users(users: list[User]) -> None:
        proto_users = await serialize_users_for_node(users)
        await node_manager.update_users(proto_users)

else:

    async def sync_user(db_user: User) -> None:
        proto_user = await serialize_user(db_user)
        user_dict = serialize_proto_message(proto_user)
        await node_nats_client.publish("update_user", {"user": user_dict})

    async def remove_user(user: UserNotificationResponse) -> None:
        proto_user = _serialize_user_for_node(user.id, user.username, user.proxy_settings.dict())
        user_dict = serialize_proto_message(proto_user)
        await node_nats_client.publish("update_user", {"user": user_dict})

    async def sync_users(users: list[User]) -> None:
        proto_users = await serialize_users_for_node(users)
        users_dicts = serialize_proto_messages(proto_users)
        await node_nats_client.publish("update_users", {"users": users_dicts})

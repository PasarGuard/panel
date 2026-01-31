from app.db.models import User, UserStatus
from app.models.user import UserNotificationResponse
from app.nats.node_rpc import node_nats_client
from app.node import node_manager
from config import IS_NODE_WORKER

if IS_NODE_WORKER:

    async def sync_user(db_user: User, user: UserNotificationResponse) -> None:
        if user.status in (UserStatus.active, UserStatus.on_hold):
            inbounds = await db_user.inbounds()
            await node_manager.update_user(user, inbounds)
        else:
            await node_manager.remove_user(user)

    async def remove_user(user: UserNotificationResponse) -> None:
        await node_manager.remove_user(user)

    async def sync_users(users: list[User]) -> None:
        await node_manager.update_users(users)

else:

    async def sync_user(db_user: User, user: UserNotificationResponse) -> None:
        await node_nats_client.publish("update_user", {"username": user.username})

    async def remove_user(user: UserNotificationResponse) -> None:
        await node_nats_client.publish("remove_user", {"username": user.username})

    async def sync_users(users: list[User]) -> None:
        await node_nats_client.publish("update_users", {"users": [user for user in users]})

import asyncio

from app.db.models import User
from app.lifecycle import on_shutdown
from app.models.user import UserNotificationResponse
from app.nats.node_rpc import node_nats_client
from app.nats.proto_utils import serialize_proto_message, serialize_proto_messages
from app.node import node_manager
from app.node.user import serialize_users_for_node, serialize_user, _serialize_user_for_node
from app.utils.logger import get_logger
from config import ROLE

logger = get_logger("node-sync")

_PENDING_SYNC_TASKS: set[asyncio.Task] = set()
_SYNC_SHUTDOWN_TIMEOUT_SECONDS = 8.0


def _on_sync_task_done(task: asyncio.Task) -> None:
    _PENDING_SYNC_TASKS.discard(task)
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except Exception as error:
        logger.warning(f"Failed to inspect sync task result: {error}")
        return
    if exc:
        logger.warning(f"Background node sync task failed: {exc}", exc_info=True)


def schedule_sync_task(coro) -> None:
    task = asyncio.create_task(coro)
    _PENDING_SYNC_TASKS.add(task)
    task.add_done_callback(_on_sync_task_done)


async def flush_pending_sync_tasks(timeout_seconds: float = _SYNC_SHUTDOWN_TIMEOUT_SECONDS) -> None:
    if not _PENDING_SYNC_TASKS:
        return

    tasks = list(_PENDING_SYNC_TASKS)
    done, pending = await asyncio.wait(tasks, timeout=timeout_seconds)

    if pending:
        logger.warning(
            f"Timed out waiting for {len(pending)} background node sync task(s); cancelling unfinished tasks."
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    for task in done:
        if task.cancelled():
            continue
        try:
            exc = task.exception()
        except Exception as error:
            logger.warning(f"Failed to inspect completed sync task: {error}")
            continue
        if exc:
            logger.warning(f"Background node sync task completed with error: {exc}", exc_info=True)


@on_shutdown
async def _flush_sync_tasks_on_shutdown():
    await flush_pending_sync_tasks()


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


async def sync_proto_user(proto_user) -> None:
    await _dispatch_user_update(proto_user)


async def sync_proto_users(proto_users) -> None:
    await _dispatch_users_update(proto_users)


async def sync_remove_users(users: list[UserNotificationResponse]) -> None:
    if not users:
        return

    proto_users = [_serialize_user_for_node(user.id, user.username, user.proxy_settings.dict()) for user in users]
    await _dispatch_users_update(proto_users)

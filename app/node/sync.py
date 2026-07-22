import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_object_session

from app.db.models import Admin, AdminRole, AdminStatus
from app.db.models import User
from app.models.user import UserNotificationResponse
from app.nats.node_rpc import encode_node_command, node_nats_client
from app.nats.proto_utils import serialize_proto_message, serialize_proto_messages
from app.node import node_manager
from app.node.user import _serialize_user_for_node, serialize_user, serialize_users_for_node
from app.utils.logger import get_logger
from config import nats_settings, runtime_settings

logger = get_logger("node-sync")


def _chunk_serialized_users_for_nats(users: list[dict]) -> list[list[dict]]:
    if not users:
        return []

    max_payload_bytes = max(1024, nats_settings.node_command_max_payload_bytes)
    max_batch_size = max(1, nats_settings.node_update_users_batch_size)
    chunks: list[list[dict]] = []
    current: list[dict] = []

    for user in users:
        candidate = [*current, user]
        if current and (
            len(candidate) > max_batch_size
            or len(encode_node_command("update_users", {"users": candidate})) > max_payload_bytes
        ):
            chunks.append(current)
            current = [user]
        else:
            current = candidate

        if len(current) == 1 and len(encode_node_command("update_users", {"users": current})) > max_payload_bytes:
            logger.warning(
                "Single serialized user update exceeds configured NATS node command payload limit: user=%s",
                user.get("email") or user.get("id") or "unknown",
            )

    if current:
        chunks.append(current)

    return chunks


def _loaded_admin_sync_blocked(admin: Admin) -> bool | None:
    state = getattr(admin, "__dict__", {})
    status = state.get("status")
    if status is None:
        return None
    if status not in (AdminStatus.limited, AdminStatus.disabled):
        return False

    role = state.get("role")
    if role is None:
        return None

    if status == AdminStatus.limited:
        return bool(role.disconnect_users_when_limited)
    return bool(role.disconnect_users_when_disabled)


async def _user_sync_blocked(db_user: User) -> bool:
    if not db_user.admin_id:
        return False

    admin = getattr(db_user, "__dict__", {}).get("admin")
    if admin is not None:
        loaded_result = _loaded_admin_sync_blocked(admin)
        if loaded_result is not None:
            return loaded_result

    session = async_object_session(db_user)
    if session is None:
        return False

    stmt = (
        select(Admin.status, AdminRole.disconnect_users_when_limited, AdminRole.disconnect_users_when_disabled)
        .select_from(Admin)
        .join(AdminRole, AdminRole.id == Admin.role_id)
        .where(Admin.id == db_user.admin_id)
    )
    row = (await session.execute(stmt)).one_or_none()
    return bool(row and ((row[0] == AdminStatus.limited and row[1]) or (row[0] == AdminStatus.disabled and row[2])))


async def _blocked_admin_ids_for_users(users: list[User]) -> set[int]:
    admin_ids = {user.admin_id for user in users if user.admin_id is not None}
    if not admin_ids:
        return set()

    loaded_admins_by_id = {
        user.admin_id: admin
        for user in users
        if user.admin_id is not None and (admin := getattr(user, "__dict__", {}).get("admin")) is not None
    }
    if set(loaded_admins_by_id) == admin_ids:
        loaded_results = {
            admin.id: blocked
            for admin in loaded_admins_by_id.values()
            if (blocked := _loaded_admin_sync_blocked(admin)) is not None
        }
        if set(loaded_results) == admin_ids:
            return {admin_id for admin_id, blocked in loaded_results.items() if blocked}

    session = next((async_object_session(user) for user in users if async_object_session(user) is not None), None)
    if session is None:
        return set()

    stmt = (
        select(Admin.id)
        .join(AdminRole, AdminRole.id == Admin.role_id)
        .where(
            Admin.id.in_(admin_ids),
            (
                ((Admin.status == AdminStatus.limited) & (AdminRole.disconnect_users_when_limited.is_(True)))
                | ((Admin.status == AdminStatus.disabled) & (AdminRole.disconnect_users_when_disabled.is_(True)))
            ),
        )
    )
    return set((await session.execute(stmt)).scalars().all())


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
        for users_chunk in _chunk_serialized_users_for_nats(users_dicts):
            await node_nats_client.publish("update_users", {"users": users_chunk})


async def sync_user(db_user: User) -> None:
    if await _user_sync_blocked(db_user):
        return

    proto_user = await serialize_user(db_user)
    asyncio.create_task(_dispatch_user_update(proto_user))


async def remove_user(user: UserNotificationResponse) -> None:
    proto_user = _serialize_user_for_node(user.id, user.proxy_settings.dict())
    asyncio.create_task(_dispatch_user_update(proto_user))


async def remove_users(users: list[User]) -> None:
    """Batch-remove users from nodes (serialized without inbounds so nodes drop them)."""
    if not users:
        return
    proto_users = [_serialize_user_for_node(u.id, u.proxy_settings) for u in users]
    asyncio.create_task(_dispatch_users_update(proto_users))


async def sync_users(users: list[User]) -> None:
    """Sync users to nodes, excluding users whose admin has users_sync_blocked."""
    blocked_admin_ids = await _blocked_admin_ids_for_users(users)
    filtered = [user for user in users if user.admin_id not in blocked_admin_ids]
    proto_users = await serialize_users_for_node(filtered)
    asyncio.create_task(_dispatch_users_update(proto_users))

import asyncio

from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_object_session

from app.db import GetDB
from app.db.crud.wireguard import get_users_accessible_tags
from app.db.models import Admin, AdminRole, AdminStatus, User
from app.models.user import UserNotificationResponse
from app.nats.node_rpc import encode_node_command, node_nats_client
from app.nats.proto_utils import serialize_proto_message, serialize_proto_messages
from app.node import node_manager
from app.node.bridge import register_refresh_handler
from app.node.user import _serialize_user_for_node, core_users, serialize_user, serialize_users_for_node
from app.utils.logger import get_logger
from config import nats_settings, runtime_settings

logger = get_logger("node-sync")
_user_sync_locks: dict[int, asyncio.Lock] = {}


async def _acquire_user_sync_locks(user_ids: list[int]) -> list[asyncio.Lock]:
    """Acquire per-user dispatch locks in a stable order."""
    locks = [_user_sync_locks.setdefault(user_id, asyncio.Lock()) for user_id in sorted(set(user_ids))]
    acquired: list[asyncio.Lock] = []
    try:
        for lock in locks:
            await lock.acquire()
            acquired.append(lock)
    except BaseException:
        _release_user_sync_locks(acquired)
        raise
    return acquired


def _release_user_sync_locks(locks: list[asyncio.Lock]) -> None:
    """Release per-user dispatch locks in reverse acquisition order."""
    for lock in reversed(locks):
        lock.release()


async def _load_current_inbound_tags(user_ids: list[int]) -> dict[int, set[str]]:
    """Load current access in a short-lived transaction before node dispatch."""
    async with GetDB() as db:
        return await get_users_accessible_tags(db, user_ids)


async def _dispatch_users_after_unlock(proto_users, locks: list[asyncio.Lock]) -> None:
    """Dispatch a queued user update and release its ordering locks afterward."""
    try:
        await _dispatch_users_update(proto_users)
    except Exception:
        logger.exception("Failed to dispatch user updates")
    finally:
        _release_user_sync_locks(locks)


async def _dispatch_user_update_after_unlock(proto_user, locks: list[asyncio.Lock]) -> None:
    """Dispatch one queued user update and release its ordering lock."""
    try:
        await _dispatch_user_update(proto_user)
    except Exception:
        logger.exception("Failed to dispatch user update")
    finally:
        _release_user_sync_locks(locks)


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


class CurrentStateReader:
    """Coalesces concurrent current-state reads into indexed queries, one per gather window.

    A query starts only after every request it serves was registered, so a
    delivery is never answered from a read that began before its own claim (and
    therefore before the enqueue and commit that triggered it). Requests that
    arrive while a query is running are served by the next query; the reader
    keeps draining until nothing is pending. There is no cache. Each query
    carries at most ``max_ids_per_query`` ids.
    """

    def __init__(self, gather_seconds: float = 0.005, max_ids_per_query: int = 400, query_timeout: float = 20.0):
        self._gather_seconds = gather_seconds
        self._max_ids = max(1, max_ids_per_query)
        # A hung database call must fail its own batch, not block every later
        # request behind it; waiters see a TimeoutError and their delivery is requeued.
        self._query_timeout = query_timeout
        self._pending: dict[int, list[asyncio.Future]] = {}
        self._task: asyncio.Task | None = None

    async def get(self, user_ids: list[int]) -> dict[int, ProtoUser | None]:
        """Current node payload per id; ``None`` means the user is gone or must be removed from nodes."""
        if not user_ids:
            return {}
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        for user_id in user_ids:
            self._pending.setdefault(user_id, []).append(future)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="node-current-state-reader")
        result = await future
        return {user_id: result.get(user_id) for user_id in user_ids}

    async def _query(self, user_ids: list[int]) -> dict[int, ProtoUser | None]:
        result: dict[int, ProtoUser | None] = dict.fromkeys(user_ids)
        async with asyncio.timeout(self._query_timeout), GetDB() as db:
            for start in range(0, len(user_ids), self._max_ids):
                for proto in await core_users(db, user_ids=user_ids[start : start + self._max_ids]):
                    result[int(proto.email)] = proto
        return result

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._gather_seconds)
            # Snapshot the requests registered so far; later ones wait for the
            # next query. Nothing awaits between an empty check and returning,
            # so a request registered after this point always finds a task to
            # start or a loop that will pick it up.
            pending, self._pending = self._pending, {}
            if not pending:
                return
            futures = {future for waiters in pending.values() for future in waiters}
            try:
                result = await self._query(list(pending))
            except asyncio.CancelledError:
                for future in futures:
                    if not future.done():
                        future.cancel()
                raise
            except Exception as exc:
                for future in futures:
                    if not future.done():
                        future.set_exception(exc)
                continue
            for future in futures:
                if not future.done():
                    future.set_result(result)


_current_state = CurrentStateReader()


async def refresh_node_users(node_id: str, emails: list[str]) -> list[ProtoUser]:
    """Return the current database state of users, as node payloads, for delivery or refresh markers.

    Called by the queue worker right before a claimed batch is sent (so what
    reaches a node is the state committed at that moment, whatever order the
    updates were queued in) and when a refresh marker is resolved. Users that
    no longer exist, are not active/on-hold, have no inbounds, or whose admin
    blocks synchronization resolve to removals, matching a full snapshot.
    Non-numeric emails (not panel users) are not answered; callers keep their
    queued payload for those.
    """
    ids = [int(email) for email in dict.fromkeys(emails) if email.isdigit()]
    if not ids:
        return []
    state = await _current_state.get(ids)
    return [proto if proto is not None else _serialize_user_for_node(user_id, {}) for user_id, proto in state.items()]


register_refresh_handler(refresh_node_users)


async def sync_user(db_user: User) -> None:
    """Serialize and dispatch one user without overtaking another update."""
    locks = await _acquire_user_sync_locks([db_user.id])
    try:
        if await _user_sync_blocked(db_user):
            return
        proto_user = await serialize_user(db_user)
        asyncio.create_task(_dispatch_user_update_after_unlock(proto_user, locks))
        locks = []
    finally:
        _release_user_sync_locks(locks)


async def remove_user(user: UserNotificationResponse) -> None:
    """Dispatch a removal update in order with other updates for the user."""
    locks = await _acquire_user_sync_locks([user.id])
    try:
        proto_user = _serialize_user_for_node(user.id, user.proxy_settings.dict())
        asyncio.create_task(_dispatch_user_update_after_unlock(proto_user, locks))
        locks = []
    finally:
        _release_user_sync_locks(locks)


async def remove_user_awaited(user: UserNotificationResponse) -> None:
    """Remove a user from nodes and await confirmation before returning.

    Unlike :func:`remove_user`, this coroutine directly awaits the node
    dispatch so callers can be sure the node update completed (or raised)
    before committing the corresponding database deletion.
    """
    proto_user = _serialize_user_for_node(user.id, user.proxy_settings.dict())
    await _dispatch_user_update(proto_user)


async def remove_users(users: list[User]) -> None:
    """Batch-remove users from nodes (serialized without inbounds so nodes drop them)."""
    if not users:
        return
    locks = await _acquire_user_sync_locks([user.id for user in users])
    try:
        proto_users = [_serialize_user_for_node(user.id, user.proxy_settings) for user in users]
        asyncio.create_task(_dispatch_users_after_unlock(proto_users, locks))
        locks = []
    finally:
        _release_user_sync_locks(locks)


async def sync_users(
    users: list[User],
    *,
    inbound_tags_by_user: dict[int, set[str]] | None = None,
    refresh_inbound_tags: bool = False,
    wait_for_dispatch: bool = False,
) -> None:
    """Sync users to nodes in order, excluding blocked administrators."""
    locks = await _acquire_user_sync_locks([user.id for user in users])
    try:
        blocked_admin_ids = await _blocked_admin_ids_for_users(users)
        filtered = [user for user in users if user.admin_id not in blocked_admin_ids]
        if refresh_inbound_tags:
            inbound_tags_by_user = await _load_current_inbound_tags([user.id for user in filtered])
        if inbound_tags_by_user is None:
            proto_users = await serialize_users_for_node(filtered)
        else:
            proto_users = await serialize_users_for_node(filtered, inbound_tags_by_user=inbound_tags_by_user)

        if wait_for_dispatch:
            await _dispatch_users_update(proto_users)
            _release_user_sync_locks(locks)
            locks = []
        else:
            # Keep the locks until the actual dispatch completes. This also
            # preserves ordering for callers that intentionally do not wait.
            asyncio.create_task(_dispatch_users_after_unlock(proto_users, locks))
            locks = []
    finally:
        _release_user_sync_locks(locks)

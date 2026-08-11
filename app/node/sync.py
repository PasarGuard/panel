import asyncio
import uuid
from dataclasses import dataclass

from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_object_session
from sqlalchemy.orm.exc import UnmappedInstanceError

from app.db import GetDB
from app.db.models import Admin, AdminRole, AdminStatus, Node, NodeStatus, User
from app.nats.node_rpc import encode_node_command, node_nats_client
from app.nats.proto_utils import serialize_proto_message, serialize_proto_messages
from app.node import node_manager
from app.node.errors import NodeRevocationError
from app.node.user import _serialize_user_for_node, serialize_user, serialize_users_for_node
from app.utils.logger import get_logger
from config import nats_settings, runtime_settings

logger = get_logger("node-sync")
_abort_retry_tasks: dict[str, asyncio.Task] = {}
_finalize_retry_tasks: dict[str, asyncio.Task] = {}
_resolution_retry_tasks: dict[str, asyncio.Task] = {}


@dataclass(frozen=True, slots=True)
class UserRevocation:
    revocation_id: str
    removal_users: tuple[ProtoUser, ...]
    original_users: tuple[ProtoUser, ...]
    expected_node_ids: frozenset[int] | None = None


def _subset_revocation(revocation: UserRevocation, user_keys: set[str]) -> UserRevocation | None:
    removal = tuple(user for user in revocation.removal_users if user.email in user_keys)
    if not removal:
        return None
    originals = {user.email: user for user in revocation.original_users}
    return UserRevocation(
        revocation.revocation_id,
        removal,
        tuple(originals[user.email] for user in removal),
        revocation.expected_node_ids,
    )


async def _resolve_user_removal_from_fresh_db(revocation: UserRevocation) -> None:
    """Resolve an ambiguous delete commit using a new DB transaction."""
    user_keys = {user.email for user in revocation.removal_users}
    async with GetDB() as db:
        present_keys = set(
            (await db.execute(select(User.sync_id).where(User.sync_id.in_(user_keys)))).scalars().all()
        )
    present = _subset_revocation(revocation, present_keys)
    absent = _subset_revocation(revocation, user_keys - present_keys)
    if present is not None:
        await _dispatch_abort_with_topology_retry(present)
    if absent is not None:
        await _dispatch_finalize_with_topology_retry(absent)


def _schedule_resolution_retry(revocation: UserRevocation) -> None:
    if revocation.revocation_id in _resolution_retry_tasks:
        return

    async def retry() -> None:
        delay = 0.25
        try:
            while True:
                try:
                    await _resolve_user_removal_from_fresh_db(revocation)
                    return
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:
                    logger.error(
                        "Retrying ambiguous database user-removal resolution %s: %s",
                        revocation.revocation_id,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)
        finally:
            _resolution_retry_tasks.pop(revocation.revocation_id, None)

    _resolution_retry_tasks[revocation.revocation_id] = asyncio.create_task(retry())


async def resolve_user_removal_after_db_error(revocation: UserRevocation | None, failed_db=None) -> None:
    """Resolve commit ambiguity; unknown membership remains fenced for retry."""
    if revocation is None:
        return
    if failed_db is not None:
        try:
            # Release locks from the failed transaction before opening the
            # authoritative read. If rollback itself is ambiguous, defer the
            # read until the request context has closed this session.
            await failed_db.rollback()
        except asyncio.CancelledError:
            _schedule_resolution_retry(revocation)
            raise
        except BaseException as exc:
            logger.error("Cannot close failed database delete transaction %s: %s", revocation.revocation_id, exc)
            _schedule_resolution_retry(revocation)
            return
    try:
        await _resolve_user_removal_from_fresh_db(revocation)
    except asyncio.CancelledError:
        _schedule_resolution_retry(revocation)
        raise
    except BaseException as exc:
        logger.error("Cannot resolve ambiguous database delete %s: %s", revocation.revocation_id, exc)
        _schedule_resolution_retry(revocation)


async def _lock_users_for_revocation(users: list[User]) -> set[int] | None:
    """Hold target DB rows until revoke and delete commit/rollback finish.

    Node startup locks its user snapshot after registering the runtime node.
    This complementary lock makes the ordering safe across Panel processes:
    startup either finishes first and is included in the topology snapshot, or
    observes the committed deletion and cannot start with a stale user.
    """
    user_ids = sorted({user.id for user in users})
    if not user_ids:
        return set()
    sessions = set()
    for user in users:
        try:
            sessions.add(async_object_session(user))
        except UnmappedInstanceError:
            # Lightweight DTO-like test/custom integrations have no ORM
            # session. Production CRUD passes mapped User instances.
            continue
    sessions.discard(None)
    if not sessions:
        return None
    if len(sessions) != 1:
        raise NodeRevocationError("users scheduled for removal belong to different database sessions")
    session = sessions.pop()
    await session.execute(select(User.id).where(User.id.in_(user_ids)).with_for_update())
    return set(
        (
            await session.execute(
                select(Node.id).where(Node.status.not_in([NodeStatus.disabled, NodeStatus.limited])).with_for_update()
            )
        )
        .scalars()
        .all()
    )


async def _refresh_expected_node_ids() -> frozenset[int]:
    """Refresh topology only after a close rejected the preflight snapshot.

    The normal rollback path never depends on a second database connection.
    This fallback handles a node which was legitimately removed after the
    original transaction released its row locks.
    """
    async with GetDB() as db:
        return frozenset(
            (await db.execute(select(Node.id).where(Node.status.not_in([NodeStatus.disabled, NodeStatus.limited]))))
            .scalars()
            .all()
        )


def _is_incomplete_topology_error(exc: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if "runtime topology is incomplete for user revocation" in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


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


def _chunk_serialized_revocations_for_nats(
    users: list[dict], original_users: list[dict], revocation_id: str
) -> list[tuple[list[dict], list[dict]]]:
    """Chunk paired removal/original payloads without exceeding NATS limits."""
    originals_by_key = {user["email"]: user for user in original_users}
    if set(originals_by_key) != {user["email"] for user in users}:
        raise NodeRevocationError("removal and restoration users do not match")

    max_payload_bytes = max(1024, nats_settings.node_command_max_payload_bytes)
    max_batch_size = max(1, nats_settings.node_update_users_batch_size)
    chunks: list[tuple[list[dict], list[dict]]] = []
    current_users: list[dict] = []
    current_originals: list[dict] = []

    for user in users:
        original_user = originals_by_key[user["email"]]
        candidate_users = [*current_users, user]
        candidate_originals = [*current_originals, original_user]
        payload = {
            "users": candidate_users,
            "original_users": candidate_originals,
            "revocation_id": revocation_id,
        }
        if current_users and (
            len(candidate_users) > max_batch_size
            or len(encode_node_command("revoke_users", payload)) > max_payload_bytes
        ):
            chunks.append((current_users, current_originals))
            current_users = [user]
            current_originals = [original_user]
        else:
            current_users = candidate_users
            current_originals = candidate_originals

        if len(current_users) == 1:
            single_payload = {
                "users": current_users,
                "original_users": current_originals,
                "revocation_id": revocation_id,
            }
            if len(encode_node_command("revoke_users", single_payload)) > max_payload_bytes:
                logger.warning(
                    "Single serialized user revocation exceeds configured NATS node command payload limit: user=%s",
                    user.get("email") or "unknown",
                )

    if current_users:
        chunks.append((current_users, current_originals))
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


async def _dispatch_user_removal(proto_user, original_user, expected_node_ids: set[int] | None = None) -> str:
    revocation_id = uuid.uuid4().hex
    if runtime_settings.role.runs_node:
        return await node_manager.revoke_users_and_wait(
            [proto_user],
            revocation_id,
            [original_user],
            expected_node_ids=expected_node_ids,
        )

    user_dict = serialize_proto_message(proto_user)
    original_user_dict = serialize_proto_message(original_user)
    payload = {"user": user_dict, "original_user": original_user_dict, "revocation_id": revocation_id}
    if expected_node_ids is not None:
        payload["expected_node_ids"] = sorted(expected_node_ids)
    try:
        await _request_node_revocation("revoke_user", payload)
    except BaseException as revoke_exc:
        # The worker may have applied the revoke even if its reply was lost.
        try:
            await _compensate_remote_revocation(
                [user_dict],
                [original_user_dict],
                revocation_id,
                expected_node_ids,
            )
        except BaseException as compensation_exc:
            raise NodeRevocationError(
                f"{revoke_exc}; revocation compensation also failed: {compensation_exc}"
            ) from compensation_exc
        raise
    return revocation_id


async def _dispatch_users_removal(
    proto_users,
    original_users,
    expected_node_ids: set[int] | None = None,
) -> str:
    revocation_id = uuid.uuid4().hex
    if runtime_settings.role.runs_node:
        return await node_manager.revoke_users_and_wait(
            proto_users,
            revocation_id,
            original_users,
            expected_node_ids=expected_node_ids,
        )

    serialized_users = serialize_proto_messages(proto_users)
    serialized_original_users = serialize_proto_messages(original_users)
    possibly_applied_chunks: list[tuple[list[dict], list[dict]]] = []
    try:
        for users_chunk, original_users_chunk in _chunk_serialized_revocations_for_nats(
            serialized_users, serialized_original_users, revocation_id
        ):
            # Include the in-flight chunk before awaiting: timeout/cancellation
            # is ambiguous because the worker may have applied it already.
            possibly_applied_chunks.append((users_chunk, original_users_chunk))
            payload = {
                "users": users_chunk,
                "original_users": original_users_chunk,
                "revocation_id": revocation_id,
            }
            if expected_node_ids is not None:
                payload["expected_node_ids"] = sorted(expected_node_ids)
            await _request_node_revocation(
                "revoke_users",
                payload,
            )
    except BaseException as revoke_exc:
        try:
            await _compensate_remote_revocation_chunks(
                possibly_applied_chunks,
                revocation_id,
                expected_node_ids,
            )
        except BaseException as compensation_exc:
            raise NodeRevocationError(
                f"{revoke_exc}; revocation compensation also failed: {compensation_exc}"
            ) from compensation_exc
        raise
    return revocation_id


async def _run_bounded_shielded(operation, description: str) -> None:
    task = asyncio.create_task(operation)

    async def wait_once() -> None:
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=nats_settings.node_rpc_timeout)
        except TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise NodeRevocationError(f"timed out while {description}") from None

    try:
        await wait_once()
    except asyncio.CancelledError:
        # A second cancellation must not cancel the compensating RPC. Give it
        # one bounded chance, then restore cancellation to the caller.
        try:
            await wait_once()
        except BaseException:
            if not task.done():
                task.cancel()
        raise


async def _abort_remote_chunks(
    users_chunks: list[tuple[list[dict], list[dict]]],
    revocation_id: str,
    expected_node_ids: set[int] | frozenset[int] | None = None,
) -> None:
    failures: list[BaseException] = []
    cancellation: asyncio.CancelledError | None = None
    for users_chunk, original_users_chunk in users_chunks:
        try:
            payload = {
                "users": users_chunk,
                "original_users": original_users_chunk,
                "revocation_id": revocation_id,
            }
            if expected_node_ids is not None:
                payload["expected_node_ids"] = sorted(expected_node_ids)
            await _run_bounded_shielded(
                _request_node_revocation("abort_revoke_users", payload),
                "aborting a user revocation chunk",
            )
        except asyncio.CancelledError as exc:
            # Finish every chunk before restoring cancellation; otherwise a
            # later chunk can remain removed while its DB row survives.
            cancellation = exc
        except BaseException as exc:
            failures.append(exc)

    if failures:
        raise NodeRevocationError(
            f"failed to compensate {len(failures)}/{len(users_chunks)} user revocation chunks"
        ) from failures[0]
    if cancellation is not None:
        raise cancellation


async def _compensate_remote_revocation_chunks(
    users_chunks: list[tuple[list[dict], list[dict]]],
    revocation_id: str,
    expected_node_ids: set[int] | None = None,
) -> None:
    await _abort_remote_chunks(users_chunks, revocation_id, expected_node_ids)


async def _compensate_remote_revocation(
    users: list[dict],
    original_users: list[dict],
    revocation_id: str,
    expected_node_ids: set[int] | None = None,
) -> None:
    await _compensate_remote_revocation_chunks(
        [(users, original_users)],
        revocation_id,
        expected_node_ids,
    )


async def _dispatch_users_removal_abort(
    proto_users,
    original_users,
    revocation_id: str,
    expected_node_ids: frozenset[int] | None = None,
) -> None:
    if runtime_settings.role.runs_node:
        await _run_bounded_shielded(
            node_manager.abort_user_revocations(
                proto_users,
                revocation_id,
                original_users,
                expected_node_ids=set(expected_node_ids) if expected_node_ids is not None else None,
            ),
            "aborting local user removals",
        )
        return

    await _abort_remote_chunks(
        _chunk_serialized_revocations_for_nats(
            serialize_proto_messages(proto_users),
            serialize_proto_messages(original_users),
            revocation_id,
        ),
        revocation_id,
        expected_node_ids,
    )


async def _dispatch_users_removal_finalize(
    proto_users,
    revocation_id: str,
    expected_node_ids: frozenset[int] | None = None,
) -> None:
    if runtime_settings.role.runs_node:
        await node_manager.finalize_user_revocations(
            proto_users,
            revocation_id,
            expected_node_ids=set(expected_node_ids) if expected_node_ids is not None else None,
        )
        return

    failures = []
    for users_chunk in _chunk_serialized_users_for_nats(serialize_proto_messages(proto_users)):
        try:
            payload = {"users": users_chunk, "revocation_id": revocation_id}
            if expected_node_ids is not None:
                payload["expected_node_ids"] = sorted(expected_node_ids)
            await _request_node_revocation("finalize_revoke_users", payload)
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise NodeRevocationError(f"failed to finalize {len(failures)} user revocation chunks") from failures[0]


async def _dispatch_abort_with_topology_retry(revocation: UserRevocation) -> None:
    async def dispatch(expected_node_ids: frozenset[int] | None) -> None:
        await _dispatch_users_removal_abort(
            list(revocation.removal_users),
            list(revocation.original_users),
            revocation.revocation_id,
            expected_node_ids,
        )

    try:
        await dispatch(revocation.expected_node_ids)
    except NodeRevocationError as exc:
        if not _is_incomplete_topology_error(exc):
            raise
        await dispatch(await _refresh_expected_node_ids())


async def _dispatch_finalize_with_topology_retry(revocation: UserRevocation) -> None:
    async def dispatch(expected_node_ids: frozenset[int] | None) -> None:
        await _run_bounded_shielded(
            _dispatch_users_removal_finalize(
                list(revocation.removal_users),
                revocation.revocation_id,
                expected_node_ids,
            ),
            "finalizing user removals",
        )

    try:
        await dispatch(revocation.expected_node_ids)
    except NodeRevocationError as exc:
        if not _is_incomplete_topology_error(exc):
            raise
        await dispatch(await _refresh_expected_node_ids())


def _schedule_finalize_retry(revocation: UserRevocation) -> None:
    if revocation.revocation_id in _finalize_retry_tasks:
        return

    async def retry() -> None:
        delay = 0.25
        try:
            while True:
                try:
                    await _dispatch_finalize_with_topology_retry(revocation)
                    return
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:
                    logger.error(
                        "Retrying incomplete user revocation finalize %s: %s",
                        revocation.revocation_id,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)
        finally:
            _finalize_retry_tasks.pop(revocation.revocation_id, None)

    _finalize_retry_tasks[revocation.revocation_id] = asyncio.create_task(retry())


def _schedule_abort_retry(revocation: UserRevocation) -> None:
    if revocation.revocation_id in _abort_retry_tasks:
        return

    async def retry() -> None:
        delay = 0.25
        try:
            while True:
                try:
                    await _dispatch_abort_with_topology_retry(revocation)
                    return
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:
                    logger.error(
                        "Retrying incomplete user revocation abort %s: %s",
                        revocation.revocation_id,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)
        finally:
            _abort_retry_tasks.pop(revocation.revocation_id, None)

    _abort_retry_tasks[revocation.revocation_id] = asyncio.create_task(retry())


async def _request_node_revocation(action: str, payload: dict) -> None:
    """Translate a remote node-worker failure into a retryable local API error."""
    try:
        await node_nats_client.request(action, payload)
    except Exception as exc:
        raise NodeRevocationError(f"cannot confirm user revocation: {exc}") from exc


async def sync_user(db_user: User) -> None:
    if await _user_sync_blocked(db_user):
        return

    proto_user = await serialize_user(db_user)
    asyncio.create_task(_dispatch_user_update(proto_user))


async def remove_user(user: User) -> UserRevocation:
    expected_node_ids = await _lock_users_for_revocation([user])
    removal_user = _serialize_user_for_node(user.sync_id, user.proxy_settings)
    original_user = await serialize_user(user)
    revocation_id = await _dispatch_user_removal(removal_user, original_user, expected_node_ids)
    return UserRevocation(
        revocation_id,
        (removal_user,),
        (original_user,),
        frozenset(expected_node_ids) if expected_node_ids is not None else None,
    )


async def remove_users_and_wait(users: list[User]) -> UserRevocation | None:
    """Publish a batch user removal before reporting cleanup as completed."""
    if not users:
        return
    expected_node_ids = await _lock_users_for_revocation(users)
    removal_users = [_serialize_user_for_node(user.sync_id, user.proxy_settings) for user in users]
    original_users = await serialize_users_for_node(users)
    revocation_id = await _dispatch_users_removal(removal_users, original_users, expected_node_ids)
    return UserRevocation(
        revocation_id,
        tuple(removal_users),
        tuple(original_users),
        frozenset(expected_node_ids) if expected_node_ids is not None else None,
    )


async def abort_user_removal(revocation: UserRevocation) -> None:
    """Abort a provisional fence when the following database delete fails."""
    try:
        await _dispatch_abort_with_topology_retry(revocation)
    except BaseException:
        _schedule_abort_retry(revocation)
        raise


async def abort_users_removal(revocation: UserRevocation) -> None:
    """Abort provisional fences when a following bulk database delete fails."""
    try:
        await _dispatch_abort_with_topology_retry(revocation)
    except BaseException:
        _schedule_abort_retry(revocation)
        raise


async def finalize_user_removal(revocation: UserRevocation) -> None:
    """Make a successful single-user revocation tombstone permanent."""
    try:
        await _dispatch_finalize_with_topology_retry(revocation)
    except BaseException as finalize_exc:
        # The database delete has committed and cannot be rolled back here.
        # Retain NodeManager/store ownership and retry until the idempotent
        # finalize is acknowledged instead of silently poisoning startup.
        logger.error("Failed to finalize user removal; scheduling retry: %s", finalize_exc)
        _schedule_finalize_retry(revocation)
        if isinstance(finalize_exc, asyncio.CancelledError):
            raise


async def finalize_users_removal(revocation: UserRevocation) -> None:
    """Make successful bulk revocation tombstones permanent."""
    try:
        await _dispatch_finalize_with_topology_retry(revocation)
    except BaseException as finalize_exc:
        logger.error("Failed to finalize user removals; scheduling retry: %s", finalize_exc)
        _schedule_finalize_retry(revocation)
        if isinstance(finalize_exc, asyncio.CancelledError):
            raise


async def remove_users(users: list[User]) -> None:
    """Batch-remove users from nodes (serialized without inbounds so nodes drop them)."""
    if not users:
        return
    proto_users = [_serialize_user_for_node(u.sync_id, u.proxy_settings) for u in users]
    asyncio.create_task(_dispatch_users_update(proto_users))


async def sync_users(users: list[User]) -> None:
    """Sync users to nodes, excluding users whose admin has users_sync_blocked."""
    blocked_admin_ids = await _blocked_admin_ids_for_users(users)
    filtered = [user for user in users if user.admin_id not in blocked_admin_ids]
    proto_users = await serialize_users_for_node(filtered)
    asyncio.create_task(_dispatch_users_update(proto_users))

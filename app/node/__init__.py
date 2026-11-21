import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from itertools import count, islice
from typing import Any

from aiorwlock import RWLock
from google.protobuf.message import EncodeError
from PasarGuardNodeBridge import Health, NodeType, PasarGuardNode
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser

from app.db.models import Node, NodeConnectionType
from app.node.bridge import create_node, get_memory_user_sync_store, get_refresh_handler
from app.node.nats_memory import UserSyncValueTooLargeError, ensure_bridge_memory, get_bridge_memory
from app.node.user import core_users
from app.utils.logger import get_logger
from config import nats_settings

type_map = {
    NodeConnectionType.rest: NodeType.rest,
    NodeConnectionType.grpc: NodeType.grpc,
}


class UserSyncPreemptedError(RuntimeError):
    """A connection change or removal of the node cancelled an in-flight user sync."""


# Building or storing one user's payload failed in a way that repeats on every attempt.
# Anything else (NATS unreachable or slow, CAS conflicts, the database) is retried.
_PERMANENT_USER_SYNC_ERRORS = (ValueError, TypeError, EncodeError, UserSyncValueTooLargeError)


def _describe_users(emails) -> str:
    emails = list(emails)
    shown = ", ".join(emails[:50])
    return f"{shown} (+{len(emails) - 50} more)" if len(emails) > 50 else shown


class NodeManager:
    # Queueing a user for a node can fail on its own (NATS slow or reconnecting).
    # The node then remembers the user's id and retries with these pauses; after
    # the last one it logs an error and tries again at each health check of the node.
    USER_SYNC_RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0)
    # Users remembered per node; one entry per user, so this is only reached with that many users.
    MAX_PENDING_USER_SYNCS_PER_NODE = 200_000

    def __init__(self):
        self._nodes: dict[int, PasarGuardNode] = {}
        self._node_signatures: dict[int, tuple] = {}
        # keep_alive goes to Start, not to the bridge object; the heartbeat reads it here.
        self._keep_alives: dict[int, int] = {}
        self._user_sync_locks: dict[int, asyncio.Lock] = {}
        self._user_sync_tasks: dict[int, set[asyncio.Task]] = {}
        # Users (by email, which is the user id) a node failed to queue. Only ids are kept:
        # a retry queues the state the database holds then, never an old payload. The value
        # is the number of the latest failure, so a failure during a retry keeps the user.
        self._pending_user_syncs: dict[int, dict[str, int]] = {}
        self._user_sync_failures = count(1)
        self._user_sync_retry_tasks: dict[int, asyncio.Task] = {}
        # Nodes that ran out of retry pauses; they are retried at each health check.
        self._parked_user_syncs: set[int] = set()
        self._background_tasks: set[asyncio.Task] = set()
        # Set while stopping: a batch cancelled by the stop is still remembered, but no retry starts.
        self._stopping_user_syncs = False
        self._lock = RWLock(fast=True)
        self.logger = get_logger("node-manager")

    @staticmethod
    def _connection_signature(node: Node) -> tuple:
        """Fields that, if changed, actually require tearing down the remote backend."""
        return (
            node.connection_type,
            node.address,
            node.port,
            node.api_port,
            node.server_ca,
            node.certificate_sha256,
            node.api_key,
            node.default_timeout,
            node.internal_timeout,
            node.proxy_url,
        )

    def _create_node_kwargs(self, node: Node) -> dict:
        kwargs = {
            "connection": type_map[node.connection_type],
            "address": node.address,
            "port": node.port,
            "api_port": node.api_port,
            "server_ca": node.server_ca,
            "certificate_sha256": node.certificate_sha256,
            "api_key": node.api_key,
            "name": node.name,
            "logger": self.logger,
            "default_timeout": node.default_timeout,
            "internal_timeout": node.internal_timeout,
            "proxy": node.proxy_url,
            "extra": {"id": node.id, "usage_coefficient": node.usage_coefficient},
            "node_id": str(node.id),
            # A delivery claim must outlive the slowest single RPC so an expired
            # claim always means its send is no longer in flight.
            "sync_lease_seconds": max(30.0, 2.0 * float(node.internal_timeout or 15) + 5.0),
        }
        store, coordinator, worker_id = get_bridge_memory()
        if store is not None and coordinator is not None:
            kwargs["user_sync_store"] = store
            kwargs["lifecycle_coordinator"] = coordinator
            kwargs["worker_id"] = worker_id
        else:
            kwargs["user_sync_store"] = get_memory_user_sync_store()
        return kwargs

    async def _shutdown_node(self, node: PasarGuardNode | None, *, remote_stop: bool = True):
        if node is None:
            return

        try:
            await node.set_health(Health.INVALID)
            if remote_stop:
                await node.stop()
        except Exception:
            pass
        finally:
            close = getattr(node, "aclose", None)
            if close is not None:
                try:
                    await close()
                except Exception:
                    self.logger.exception("Failed to close retired node connections")

    async def _cancel_user_syncs(self, node_id: int) -> None:
        current = asyncio.current_task()
        tasks = [task for task in self._user_sync_tasks.get(node_id, ()) if task is not current and not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _track_user_sync(self, node_id: int, task: asyncio.Task | None = None) -> asyncio.Task | None:
        if task is None:
            task = asyncio.current_task()
        if task is not None:
            self._user_sync_tasks.setdefault(node_id, set()).add(task)
        return task

    def _untrack_user_sync(self, node_id: int, task: asyncio.Task | None) -> None:
        if task is None:
            return
        tasks = self._user_sync_tasks.get(node_id)
        if tasks is None:
            return
        tasks.discard(task)
        if not tasks:
            self._user_sync_tasks.pop(node_id, None)

    async def update_node(self, node: Node) -> PasarGuardNode:
        await ensure_bridge_memory()

        self._keep_alives[node.id] = node.keep_alive or 0
        signature = self._connection_signature(node)
        async with self._lock.reader_lock:
            existing = self._nodes.get(node.id)
            existing_signature = self._node_signatures.get(node.id)

        # update_node() runs on every reconnect attempt, including the automated
        # ones the health-check watchdog fires every ~minute. If nothing about the
        # connection actually changed, reuse the live object without interrupting sync.
        if existing is not None and existing_signature == signature:
            existing_extra = await existing.get_extra()
            if existing.name == node.name and existing_extra.get("usage_coefficient") == node.usage_coefficient:
                return existing

        # A connection change takes precedence over an old user sync: the sync talks to
        # the old address/credentials, and cancelling it keeps a failed bridge fallback
        # from holding this node's lock for minutes. A metadata-only change (name or
        # usage coefficient) keeps the sync and waits for the lock instead, so pending
        # user deltas are not dropped; bulk deliveries release the lock between batches
        # and continue on the replacement object.
        if existing_signature != signature:
            await self._cancel_user_syncs(node.id)

        lock = self._user_sync_locks.setdefault(node.id, asyncio.Lock())
        async with lock:
            # Another update may have completed while this call was waiting.
            async with self._lock.reader_lock:
                existing = self._nodes.get(node.id)
                existing_signature = self._node_signatures.get(node.id)
            if existing is not None and existing_signature == signature:
                existing_extra = await existing.get_extra()
                if existing.name == node.name and existing_extra.get("usage_coefficient") == node.usage_coefficient:
                    return existing

            creation_error: Exception | None = None
            async with self._lock.writer_lock:
                old_node: PasarGuardNode | None = self._nodes.pop(node.id, None)
                self._node_signatures.pop(node.id, None)
                try:
                    new_node = create_node(**self._create_node_kwargs(node))
                except Exception as exc:
                    creation_error = exc
                else:
                    self._nodes[node.id] = new_node
                    self._node_signatures[node.id] = signature

            if creation_error is not None:
                try:
                    await self._shutdown_node(old_node, remote_stop=False)
                except Exception:
                    self.logger.exception("Failed to shut down old node after creation failure")
                raise creation_error

            # Metadata-only changes require a fresh bridge object, but must not stop a
            # healthy remote backend. The reconnect path will attach the replacement.
            await self._shutdown_node(old_node, remote_stop=existing_signature != signature)

        return new_node

    async def remove_node(self, id: int, *, remote_stop: bool = True) -> None:
        # A removed or disconnected node gets a full snapshot when it is started
        # again, so users still waiting to be queued for it are no longer needed.
        await self._drop_pending_user_syncs(id)
        await self._cancel_user_syncs(id)

        # Keep the per-node lock identity stable for the lifetime of the manager so a
        # waiter cannot overlap a later operation through a newly-created lock.
        lock = self._user_sync_locks.setdefault(id, asyncio.Lock())
        async with lock, self._lock.writer_lock:
            old_node: PasarGuardNode | None = self._nodes.pop(id, None)
            self._node_signatures.pop(id, None)
            self._keep_alives.pop(id, None)
            self._user_sync_tasks.pop(id, None)

        # Do cleanup without holding the lock to avoid slow delete operations.
        asyncio.create_task(self._shutdown_node(old_node, remote_stop=remote_stop))

    async def get_node(self, id: int) -> PasarGuardNode | None:
        async with self._lock.reader_lock:
            return self._nodes.get(id, None)

    async def stop_node_if_current(self, node_id: int, node: PasarGuardNode) -> bool:
        """Stop a node only while it is still the manager's current connection."""
        lock = self._user_sync_locks.setdefault(node_id, asyncio.Lock())
        async with lock:
            if await self.get_node(node_id) is not node:
                return False
            await node.stop()
            return True

    async def get_nodes(self) -> dict[int, PasarGuardNode]:
        async with self._lock.reader_lock:
            return self._nodes

    async def get_keep_alive_nodes(self) -> list[tuple[int, PasarGuardNode, int]]:
        """Nodes whose core stops without regular requests, with their keep_alive."""
        async with self._lock.reader_lock:
            return [
                (node_id, node, self._keep_alives[node_id])
                for node_id, node in self._nodes.items()
                if self._keep_alives.get(node_id, 0) > 0
            ]

    async def get_healthy_nodes(self) -> list[tuple[int, PasarGuardNode]]:
        async with self._lock.reader_lock:
            nodes: list[tuple[int, PasarGuardNode]] = [
                (id, node) for id, node in self._nodes.items() if (await node.get_health() == Health.HEALTHY)
            ]
            return nodes

    async def get_broken_nodes(self) -> list[tuple[int, PasarGuardNode]]:
        async with self._lock.reader_lock:
            nodes: list[tuple[int, PasarGuardNode]] = [
                (id, node) for id, node in self._nodes.items() if (await node.get_health() == Health.BROKEN)
            ]
            return nodes

    async def get_not_connected_nodes(self) -> list[tuple[int, PasarGuardNode]]:
        async with self._lock.reader_lock:
            nodes: list[tuple[int, PasarGuardNode]] = [
                (id, node) for id, node in self._nodes.items() if (await node.get_health() == Health.NOT_CONNECTED)
            ]
            return nodes

    async def _snapshot_nodes(self) -> list[PasarGuardNode]:
        async with self._lock.reader_lock:
            return list(self._nodes.values())

    async def _snapshot_node_items(self) -> list[tuple[int, PasarGuardNode]]:
        async with self._lock.reader_lock:
            return list(self._nodes.items())

    @staticmethod
    def _chunk_users(users: list[ProtoUser], size: int) -> list[list[ProtoUser]]:
        return [users[start : start + size] for start in range(0, len(users), size)]

    async def _sync_user_batch_to_node(self, node: PasarGuardNode, batch: list[ProtoUser]) -> list[ProtoUser]:
        """Deliver one bounded batch directly; returns the users that failed."""
        users_to_sync = batch
        supports_chunked = True
        supports_chunked_check = getattr(node, "_supports_chunked_sync", None)
        if callable(supports_chunked_check):
            supports_chunked, _ = await supports_chunked_check()

        if supports_chunked:
            users_to_sync = await node.sync_users_chunked(
                batch,
                chunk_size=len(batch),
                flush_pending=False,
            )
            if not users_to_sync:
                return []

        sync_batch_users = getattr(node, "_sync_batch_users", None)
        if callable(sync_batch_users):
            users_to_sync = await sync_batch_users(users_to_sync)

        return list(users_to_sync)

    async def _sync_user_batches(
        self, node_id: int, node: PasarGuardNode, users: list[ProtoUser], *, batch_size: int | None = None
    ) -> None:
        batch_size = max(1, batch_size or nats_settings.node_update_users_batch_size)
        failed_count = 0

        for batch in self._chunk_users(users, batch_size):
            failed_count += len(await self._sync_user_batch_to_node(node, batch))

        if failed_count:
            raise RuntimeError(f"failed to sync {failed_count}/{len(users)} users to node {node_id}")

    async def _sync_users_to_node(self, node_id: int, node: PasarGuardNode | None, users: list[ProtoUser]):
        batch_size = max(1, nats_settings.node_update_users_batch_size)
        lock = self._user_sync_locks.setdefault(node_id, asyncio.Lock())
        failed_count = 0
        task = self._track_user_sync(node_id)

        try:
            # The bridge exposes the fence methods on local nodes too, but the
            # process-local store cannot provide shared fencing/recovery. Keep the
            # direct path unless the complete shared protocol is available.
            current_node = node
            if current_node is None:
                async with lock:
                    current_node = await self.get_node(node_id)
            if current_node is None:
                return
            if self._supports_shared_sync(current_node):
                # Bulk updates use the same durable, fenced delivery as single
                # updates only when the shared-store protocol is available.
                await current_node.update_users(users)
                return

            for batch in self._chunk_users(users, batch_size):
                # Release the lock after every bounded batch so node lifecycle operations
                # can preempt a large sync. Managed calls resolve the current node again
                # after every yield and therefore never continue on a replaced instance.
                async with lock:
                    current_node = node if node is not None else await self.get_node(node_id)
                    if current_node is None:
                        return
                    failed_count += len(await self._sync_user_batch_to_node(current_node, batch))
        finally:
            self._untrack_user_sync(node_id, task)

        if failed_count:
            raise RuntimeError(f"failed to sync {failed_count}/{len(users)} users to node {node_id}")

    async def _run_preemptible_sync(
        self, node_id: int, sync: Coroutine[Any, Any, PasarGuardNode | None]
    ) -> PasarGuardNode | None:
        """Run a user sync in its own tracked task so lifecycle operations can preempt it.

        A connection change or removal of the node cancels only that task, never the
        caller (for example the admin's HTTP request); the caller gets
        ``UserSyncPreemptedError`` instead. Cancelling the caller still cancels the sync.
        """
        task = asyncio.create_task(sync)
        self._track_user_sync(node_id, task)
        try:
            return await task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if task.cancelled() and (current is None or not current.cancelling()):
                raise UserSyncPreemptedError(
                    f"user sync to node {node_id} was cancelled by a connection change or removal of the node"
                ) from None
            raise
        finally:
            self._untrack_user_sync(node_id, task)

    async def sync_users_batched(
        self, node_id: int, node: PasarGuardNode, users: list[ProtoUser], *, batch_size: int | None = None
    ) -> PasarGuardNode | None:
        """Apply a large initial user set through bounded delta batches.

        Holds the per-node lock for all batches, so a metadata-only edit waits for the
        whole set; a connection change or removal preempts it like ``sync_full``.
        """
        return await self._run_preemptible_sync(
            node_id, self._sync_users_batched(node_id, node, users, batch_size=batch_size)
        )

    async def _sync_users_batched(
        self, node_id: int, node: PasarGuardNode, users: list[ProtoUser], *, batch_size: int | None
    ) -> PasarGuardNode | None:
        lock = self._user_sync_locks.setdefault(node_id, asyncio.Lock())
        async with lock:
            if await self.get_node(node_id) is not node:
                return None
            await self._sync_user_batches(node_id, node, users, batch_size=batch_size)
        return node

    @staticmethod
    def _supports_shared_sync(node: PasarGuardNode) -> bool:
        # The panel adapter implements a safe process-local fence as well as
        # the NATS-backed one. The upstream bridge's base fence alone is not
        # enough: it lacks the capture/release protocol used below.
        required = (
            "full_sync_fence",
            "capture_queued_work",
            "release_queued_work",
            "retire_queued_work",
        )
        return all(callable(getattr(node, name, None)) for name in required)

    async def sync_full(
        self,
        node_id: int,
        users: list[ProtoUser] | Callable[[], Awaitable[list[ProtoUser]]],
        *,
        flush_pending: bool = False,
    ) -> PasarGuardNode | None:
        """Push a full user snapshot to a node, coordinated with update_node/remove_node.

        ``users`` may be a deferred loader. It is resolved inside the node's
        full-sync fence, so every update queued afterwards stays queued until
        the snapshot has landed. Flushing is non-destructive: the queued
        entries the snapshot covers are recorded first and retired only after
        the RPC succeeded, so a failed read, a failed RPC, or a crash leaves the
        original queue intact.

        Guards against the reconnect/health-check watchdog tearing down the node object
        mid-sync (which previously restarted the sync from scratch and could loop).
        A connection change or removal cancels the sync before taking the per-node lock,
        while unchanged health-check reconnects and metadata-only edits let it finish.

        The sync runs in its own tracked task, so preemption cancels only that task and
        never the caller (in single-process mode the caller is the admin's HTTP request);
        the caller gets ``UserSyncPreemptedError`` instead. Cancelling the caller still
        cancels the sync.
        """
        return await self._run_preemptible_sync(node_id, self._sync_full(node_id, users, flush_pending=flush_pending))

    async def _sync_full(
        self,
        node_id: int,
        users: list[ProtoUser] | Callable[[], Awaitable[list[ProtoUser]]],
        *,
        flush_pending: bool,
    ) -> PasarGuardNode | None:
        lock = self._user_sync_locks.setdefault(node_id, asyncio.Lock())
        async with lock:
            node = await self.get_node(node_id)
            if node is None:
                return None

            # Do not call full_sync_fence merely because bridge 0.9.x exposes
            # it: without a shared snapshot store it raises NodeAPIError.
            if not self._supports_shared_sync(node):
                if callable(users):
                    users = await users()
                await node.sync_users(users, flush_pending=flush_pending)
                return node
            async with node.full_sync_fence() as held:
                # Always wait for in-flight deliveries to settle; retire the
                # captured entries only when flushing was requested.
                captured = await node.capture_queued_work()
                if not flush_pending:
                    captured = {} if isinstance(captured, dict) else captured
                try:
                    if callable(users):
                        users = await users()
                    # A fence this worker no longer owns must not send or retire.
                    held.check()
                    await node.sync_users(users, flush_pending=False)
                    held.check()
                except BaseException:
                    await node.release_queued_work(captured)
                    raise
                if flush_pending:
                    await node.retire_queued_work(captured)
                else:
                    await node.release_queued_work(captured)
            return node

    async def _update_users(self, users: list[ProtoUser]):
        nodes = await self._snapshot_node_items()
        if not nodes:
            return

        try:
            results = await asyncio.gather(
                *(self._sync_users_to_node(node_id, None, users) for node_id, _node in nodes), return_exceptions=True
            )
        except asyncio.CancelledError as exc:
            # Shutdown or a cancelled caller: whether the batch was queued is unknown.
            for node_id, _node in nodes:
                self._user_sync_failed(node_id, users, exc)
            raise
        for (node_id, _node), result in zip(nodes, results, strict=True):
            if isinstance(result, asyncio.CancelledError):
                # A connection change or removal of the node preempted this delivery.
                self.logger.debug("User sync to node %s was cancelled by a node lifecycle change", node_id)
            elif isinstance(result, Exception):
                self._user_sync_failed(node_id, users, result)

    async def update_users(self, users: list[ProtoUser], *, await_dispatch: bool = False) -> None:
        """Queue a batch, optionally waiting so a producer cannot outrun node dispatch.

        Per-node failures are never raised: the node retries the users on its own.
        """
        if await_dispatch:
            await self._update_users(users)
        else:
            self._spawn(self._update_users(users), name="node-update-users")

    async def update_user(self, user: ProtoUser) -> None:
        """Queue one user on every node.

        A node that fails to queue it retries on its own; the first failure is
        still raised for callers that wait for confirmation.
        """
        nodes = await self._snapshot_node_items()
        if not nodes:
            return

        try:
            results = await asyncio.gather(
                *(node.update_user(user) for _node_id, node in nodes), return_exceptions=True
            )
        except asyncio.CancelledError as exc:
            for node_id, _node in nodes:
                self._user_sync_failed(node_id, [user], exc)
            raise
        for (node_id, _node), result in zip(nodes, results, strict=True):
            if isinstance(result, Exception):
                self._user_sync_failed(node_id, [user], result)
        for result in results:
            if isinstance(result, Exception):
                raise result

    # ------------------------------------------------------ failed queueing retry
    def _spawn(self, coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task:
        """Run a background coroutine, keeping it referenced until it ends."""
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_task_done)
        return task

    def _background_task_done(self, task: asyncio.Task) -> None:
        self._background_tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            self.logger.error("Background node user sync failed: %s", exc, exc_info=exc)

    def _user_sync_failed(self, node_id: int, users: list[ProtoUser], error: BaseException) -> None:
        """Remember the users a node failed to queue and wake its retry."""
        if not users or node_id not in self._nodes:
            return  # a removed node that comes back gets a full snapshot on Start
        self.logger.warning(
            "Failed to queue %d user(s) for node %s, retrying: %s: %s",
            len(users),
            node_id,
            type(error).__name__,
            error,
        )
        pending = self._pending_user_syncs.setdefault(node_id, {})
        failure = next(self._user_sync_failures)
        refused: list[str] = []
        for user in users:
            if user.email not in pending and len(pending) >= self.MAX_PENDING_USER_SYNCS_PER_NODE:
                refused.append(user.email)
                continue
            pending[user.email] = failure
        if refused:
            self.logger.error(
                "Too many users waiting to be queued for node %s; %d user(s) are not retried "
                "and need a manual user sync of the node: %s",
                node_id,
                len(refused),
                _describe_users(refused),
            )
        self._parked_user_syncs.discard(node_id)
        self._start_user_sync_retry(node_id, self.USER_SYNC_RETRY_DELAYS)

    def _clear_pending_user_syncs(self, node_id: int, *, recovered: bool) -> None:
        self._pending_user_syncs.pop(node_id, None)
        if node_id in self._parked_user_syncs:
            self._parked_user_syncs.discard(node_id)
            if recovered:
                self.logger.info("Users waiting to be queued for node %s are queued again", node_id)

    def _start_user_sync_retry(self, node_id: int, delays: tuple[float, ...]) -> None:
        if self._stopping_user_syncs:
            return
        task = self._user_sync_retry_tasks.get(node_id)
        if task is not None and not task.done():
            return
        task = asyncio.create_task(self._retry_user_syncs(node_id, delays), name=f"node-{node_id}-user-sync-retry")
        self._user_sync_retry_tasks[node_id] = task
        task.add_done_callback(lambda done: self._user_sync_retry_done(node_id, done))

    def _user_sync_retry_done(self, node_id: int, task: asyncio.Task) -> None:
        if self._user_sync_retry_tasks.get(node_id) is task:
            self._user_sync_retry_tasks.pop(node_id, None)
        if not task.cancelled() and (exc := task.exception()) is not None:
            self.logger.error("User sync retry for node %s failed: %s", node_id, exc, exc_info=exc)

    def resume_user_sync_retries(self, node_id: int) -> None:
        """Make one immediate attempt for users still waiting to be queued for a node."""
        if self._pending_user_syncs.get(node_id):
            self._start_user_sync_retry(node_id, (0.0,))

    async def _retry_user_syncs(self, node_id: int, delays: tuple[float, ...]) -> None:
        for delay in delays:
            await asyncio.sleep(delay)
            if not self._pending_user_syncs.get(node_id):
                return
            if await self.get_node(node_id) is None:
                self._clear_pending_user_syncs(node_id, recovered=False)
                return
            if await self._retry_user_sync_round(node_id):
                return
        pending = self._pending_user_syncs.get(node_id)
        if pending and node_id not in self._parked_user_syncs:
            self._parked_user_syncs.add(node_id)
            self.logger.error(
                "Could not queue %d user(s) for node %s after %d attempts; retrying at each "
                "health check of the node. Users: %s",
                len(pending),
                node_id,
                len(delays),
                _describe_users(pending),
            )

    async def _retry_user_sync_round(self, node_id: int) -> bool:
        """Queue the current state of the users a node failed to queue; True once none are left.

        A round starts with one user, so a node whose queue is down costs one or two
        writes, and goes on in batches while queueing works. A failed batch is retried
        user by user, so a user that can never be queued does not hold the others back.
        A user leaves the set only when a write of its current state worked and no newer
        failure was recorded for it meanwhile, or when its payload cannot be built or stored.
        """
        batch_size = max(1, nats_settings.node_update_users_batch_size)
        size = 1
        tried: set[str] = set()
        split: list[str] = []
        failed_alone = 0
        while pending := self._pending_user_syncs.get(node_id):
            if split:
                emails = [email for email in (split.pop(0),) if email in pending]
                if not emails:
                    continue
            else:
                emails = list(islice((email for email in pending if email not in tried), size))
                if not emails:
                    break
            tried.update(emails)
            failures = {email: pending[email] for email in emails}
            # A separate task, so a node lifecycle change cancels this attempt, not the retry loop.
            (error,) = await asyncio.gather(self._queue_current_users(node_id, emails), return_exceptions=True)
            if isinstance(error, asyncio.CancelledError):
                return False
            if (pending := self._pending_user_syncs.get(node_id)) is None:
                return True
            if error is None:
                for email, failure in failures.items():
                    if pending.get(email) == failure:
                        del pending[email]
                size, failed_alone = batch_size, 0
            elif len(emails) > 1:
                split, size = emails, 1
            elif isinstance(error, _PERMANENT_USER_SYNC_ERRORS):
                (email,) = emails
                if pending.get(email) == failures[email]:
                    del pending[email]
                    self.logger.error(
                        "User %s cannot be queued for node %s (%s: %s); it is not retried "
                        "and needs a manual user sync of the node",
                        email,
                        node_id,
                        type(error).__name__,
                        error,
                    )
            else:
                (email,) = emails
                if email in pending:
                    pending[email] = pending.pop(email)  # let others go first next round
                self.logger.debug("Retry of user %s for node %s failed: %s", email, node_id, error)
                failed_alone, size = failed_alone + 1, 1
                if failed_alone >= 2:
                    break  # queueing is down for this node
        if not self._pending_user_syncs.get(node_id):
            self._clear_pending_user_syncs(node_id, recovered=True)
            return True
        return False

    async def _queue_current_users(self, node_id: int, emails: list[str]) -> None:
        """Queue for a node the state the database holds now for these users.

        With the NATS queue this only asks the queue to re-read the users before delivery:
        nothing is written over an entry already queued for a user, because that entry is
        delivered from the database anyway and keeps the credentials a node may need to
        find what to remove (an entry being delivered is made to be delivered once more).
        A payload read here could be older than that entry: written over it, the
        credentials of a user changed and then deleted in between would replace the ones
        the node holds. The process-local queue used without NATS does the same: it
        queues the payload read here only for a user with no entry, and gives an entry
        already queued a new revision with its payload kept.
        """
        read = get_refresh_handler()
        if read is None:
            raise RuntimeError("no reader of the current user state is registered")
        task = self._track_user_sync(node_id)
        try:
            current = {user.email: user for user in await read(str(node_id), emails)}
            if missing := [email for email in emails if email not in current]:
                raise ValueError(f"no current state for user(s) {_describe_users(missing)}")
            users = [current[email] for email in emails]
            node = await self.get_node(node_id)
            if node is None:
                return
            request_refresh = getattr(node, "request_refresh", None)
            if callable(request_refresh) and self._supports_shared_sync(node):
                await request_refresh(users)
                return
        finally:
            self._untrack_user_sync(node_id, task)
        await self._sync_users_to_node(node_id, None, users)

    async def _drop_pending_user_syncs(self, node_id: int) -> None:
        task = self._user_sync_retry_tasks.pop(node_id, None)
        self._clear_pending_user_syncs(node_id, recovered=False)
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def stop_user_sync_retries(self) -> None:
        """Stop background user syncs on shutdown; report users that were never queued."""
        self._stopping_user_syncs = True
        try:
            if self._background_tasks:
                # Let batches already being queued finish; a cancelled one is remembered as failed.
                # Short: with the 3 s dispatch drain this stays within ~5 s of the stop grace period.
                await asyncio.wait(set(self._background_tasks), timeout=2.0)
            tasks = [*self._background_tasks, *self._user_sync_retry_tasks.values()]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._stopping_user_syncs = False
        self._user_sync_retry_tasks.clear()
        for node_id, pending in self._pending_user_syncs.items():
            if pending:
                self.logger.error(
                    "Shutting down with %d user(s) never queued for node %s: %s",
                    len(pending),
                    node_id,
                    _describe_users(pending),
                )
        self._pending_user_syncs.clear()
        self._parked_user_syncs.clear()


node_manager: NodeManager = NodeManager()


__all__ = ["UserSyncPreemptedError", "core_users", "node_manager"]

import asyncio
import hashlib

from aiorwlock import RWLock
from PasarGuardNodeBridge import Health, NodeAPIError, NodeType, PasarGuardNode, create_node
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser

from app.db.models import Node, NodeConnectionType
from app.nats import needs_shared_bridge_memory
from app.node.errors import NodeRevocationError
from app.node.nats_memory import ensure_bridge_memory, get_bridge_memory
from app.node.user import core_users
from app.utils.logger import get_logger
from config import nats_settings

type_map = {
    NodeConnectionType.rest: NodeType.rest,
    NodeConnectionType.grpc: NodeType.grpc,
}


class NodeManager:
    def __init__(self):
        self._nodes: dict[int, PasarGuardNode] = {}
        self._retiring_nodes: dict[int, list[PasarGuardNode]] = {}
        self._removing_node_ids: set[int] = set()
        self._replacing_node_ids: set[int] = set()
        self._deleted_node_namespaces: set[str] = set()
        self._runtime_transition_tasks: set[asyncio.Task] = set()
        self._runtime_transition_locks: dict[int, asyncio.Lock] = {}
        self._user_sync_locks: dict[int, asyncio.Lock] = {}
        # A permanent deletion fence. User IDs are generated monotonically and
        # are not reused, so retaining the tombstone prevents an already queued
        # update from re-admitting a deleted user after revocation completes.
        self._deleted_user_keys: set[str] = set()
        self._deletion_fence_owners: dict[str, set[str]] = {}
        self._revocation_nodes: dict[str, list[tuple[int, PasarGuardNode, frozenset[str]]]] = {}
        self._revocations_idle = asyncio.Event()
        self._revocations_idle.set()
        # Deployment mode is immutable for this process. Never build a hybrid
        # manager containing private and NATS-backed bridge stores.
        self._uses_shared_revocation_store = needs_shared_bridge_memory()
        self._lock = RWLock(fast=True)
        self.logger = get_logger("node-manager")

    def _create_node_kwargs(self, node: Node) -> dict:
        kwargs = {
            "connection": type_map[node.connection_type],
            "address": node.address,
            "port": node.port,
            "api_port": node.api_port,
            "server_ca": node.server_ca,
            "api_key": node.api_key,
            "name": node.name,
            "logger": self.logger,
            "default_timeout": node.default_timeout,
            "internal_timeout": node.internal_timeout,
            "proxy": node.proxy_url,
            "extra": {
                "id": node.id,
                "usage_coefficient": node.usage_coefficient,
                "config_signature": self.node_config_signature(node),
            },
            "node_id": self.bridge_namespace(node),
        }
        store, coordinator, worker_id = get_bridge_memory()
        if self._uses_shared_revocation_store and (store is None or coordinator is None):
            raise NodeAPIError(503, "shared node bridge memory is unavailable")
        if store is not None and coordinator is not None:
            kwargs["user_sync_store"] = store
            kwargs["lifecycle_coordinator"] = coordinator
            kwargs["worker_id"] = worker_id
        return kwargs

    @staticmethod
    def bridge_namespace(node: Node) -> str:
        """Return the persisted Bridge namespace, with a test/legacy fallback."""
        return str(getattr(node, "bridge_id", None) or node.id)

    def is_bridge_namespace_deleted(self, namespace: str) -> bool:
        return str(namespace) in self._deleted_node_namespaces

    @staticmethod
    def node_config_signature(node: Node) -> str:
        values = (
            node.connection_type,
            node.address,
            node.port,
            node.api_port,
            node.server_ca,
            node.api_key,
            node.name,
            node.default_timeout,
            node.internal_timeout,
            node.proxy_url,
            node.usage_coefficient,
        )
        return hashlib.sha256(repr(values).encode()).hexdigest()

    async def runtime_matches(self, node: Node) -> bool:
        async with self._lock.reader_lock:
            runtime = self._nodes.get(node.id)
            return runtime is not None and self.runtime_config_matches(runtime, node)

    @classmethod
    def runtime_config_matches(cls, runtime: PasarGuardNode, node: Node) -> bool:
        return bool(
            str(runtime.node_id) == cls.bridge_namespace(node)
            and getattr(runtime, "_extra", {}).get("config_signature")
            == cls.node_config_signature(node)
        )

    @property
    def uses_shared_revocation_store(self) -> bool:
        return self._uses_shared_revocation_store

    async def _shutdown_node(self, node: PasarGuardNode | None, *, remote_stop: bool = True) -> bool:
        if node is None:
            return True

        try:
            await node.set_health(Health.INVALID)
        except Exception:
            pass
        try:
            if remote_stop:
                await node.stop()
            else:
                # Another worker already owns the remote Stop.  This local
                # controller must still cancel and await its background sync
                # and stats tasks before shared state can be purged.
                await node.disconnect()
            return True
        except Exception as exc:
            self.logger.error("Failed to quiesce retiring node runtime: %s", exc)
            return False

    async def _finish_retiring_node(
        self,
        node_id: int,
        node: PasarGuardNode | None,
        *,
        remote_stop: bool = True,
    ) -> None:
        if node is None or not await self._shutdown_node(node, remote_stop=remote_stop):
            return
        async with self._lock.writer_lock:
            retiring = self._retiring_nodes.get(node_id)
            if retiring is None:
                return
            self._retiring_nodes[node_id] = [candidate for candidate in retiring if candidate is not node]
            if not self._retiring_nodes[node_id]:
                self._retiring_nodes.pop(node_id, None)

    async def update_node(self, node: Node) -> PasarGuardNode:
        await ensure_bridge_memory()
        namespace = self.bridge_namespace(node)
        if namespace in self._deleted_node_namespaces:
            await self.remove_node(
                node.id,
                remote_stop=False,
                expected_bridge_namespace=namespace,
            )
            raise NodeAPIError(410, f"node {node.id} incarnation is permanently deleted")
        _, coordinator, _ = get_bridge_memory()
        if self._uses_shared_revocation_store:
            if coordinator is None:
                raise NodeAPIError(503, "shared node bridge memory is unavailable")
            if await coordinator.is_deleted(namespace):
                # A missed broadcast must not leave a stale local controller
                # capable of attaching to or restarting a deleted incarnation.
                await self.remove_node(
                    node.id,
                    remote_stop=False,
                    expected_bridge_namespace=namespace,
                )
                raise NodeAPIError(410, f"node {node.id} incarnation is permanently deleted")
        # Validate shared-memory availability and construct the replacement
        # before mutating the active/retiring topology. A fail-closed 503 must
        # leave the currently working runtime untouched.
        new_node = create_node(**self._create_node_kwargs(node))
        transition = asyncio.create_task(self._replace_runtime(node.id, new_node, coordinator, namespace))
        self._runtime_transition_tasks.add(transition)

        def _transition_done(task: asyncio.Task) -> None:
            self._runtime_transition_tasks.discard(task)
            if task.cancelled():
                return
            # Retrieve failures when a cancelled caller no longer awaits us.
            task.exception()

        transition.add_done_callback(_transition_done)
        return await asyncio.shield(transition)

    async def _replace_runtime(
        self,
        node_id: int,
        new_node: PasarGuardNode,
        coordinator,
        namespace: str,
    ) -> PasarGuardNode:
        transition_lock = self._runtime_transition_locks.setdefault(node_id, asyncio.Lock())
        async with transition_lock:
            return await self._replace_runtime_locked(node_id, new_node, coordinator, namespace)

    async def _replace_runtime_locked(
        self,
        node_id: int,
        new_node: PasarGuardNode,
        coordinator,
        namespace: str,
    ) -> PasarGuardNode:
        """Quiesce every old runtime before making a replacement active."""
        deleted_after_shutdown = False
        async with self._lock.writer_lock:
            if self.is_bridge_namespace_deleted(namespace) or (
                coordinator is not None and await coordinator.is_deleted(namespace)
            ):
                deleted = True
                retiring: list[PasarGuardNode] = []
            else:
                deleted = False
                if node_id in self._removing_node_ids and node_id not in self._replacing_node_ids:
                    raise NodeAPIError(409, f"node {node_id} removal is in progress")
                self._replacing_node_ids.add(node_id)
                self._removing_node_ids.add(node_id)
                old_node = self._nodes.pop(node_id, None)
                if old_node is not None:
                    current = self._retiring_nodes.setdefault(node_id, [])
                    if old_node not in current:
                        current.append(old_node)
                retiring = list(self._retiring_nodes.get(node_id, ()))

        if deleted:
            await self.remove_node(
                node_id,
                remote_stop=False,
                expected_bridge_namespace=namespace,
            )
            raise NodeAPIError(410, f"node {node_id} incarnation is permanently deleted")

        results = await asyncio.gather(
            *(self._shutdown_node(runtime) for runtime in retiring),
            return_exceptions=True,
        )
        succeeded = [runtime for runtime, result in zip(retiring, results) if result is True]
        failed = [runtime for runtime, result in zip(retiring, results) if result is not True]
        async with self._lock.writer_lock:
            current = self._retiring_nodes.get(node_id, [])
            current = [runtime for runtime in current if runtime not in succeeded]
            if current:
                self._retiring_nodes[node_id] = current
            else:
                self._retiring_nodes.pop(node_id, None)
            if failed or current:
                # Keep the replacement barrier retryable. A later update will
                # drain all accumulated retirees before installing anything.
                raise NodeAPIError(503, f"cannot confirm old node {node_id} runtime shutdown")
            if self.is_bridge_namespace_deleted(namespace) or (
                coordinator is not None and await coordinator.is_deleted(namespace)
            ):
                self._replacing_node_ids.discard(node_id)
                self._removing_node_ids.discard(node_id)
                deleted_after_shutdown = True
            else:
                self._nodes[node_id] = new_node
                self._user_sync_locks.setdefault(node_id, asyncio.Lock())
                self._replacing_node_ids.discard(node_id)
                self._removing_node_ids.discard(node_id)

        if deleted_after_shutdown:
            try:
                await new_node.disconnect()
            except Exception:
                pass
            raise NodeAPIError(410, f"node {node_id} incarnation is permanently deleted")

        return new_node

    async def remove_node(
        self,
        id: int,
        *,
        remote_stop: bool = True,
        expected_bridge_namespace: str | None = None,
        permanent_delete: bool = False,
    ) -> None:
        await ensure_bridge_memory()
        _, coordinator, _ = get_bridge_memory()
        async with self._lock.writer_lock:
            active_node = self._nodes.get(id)
            if (
                expected_bridge_namespace is not None
                and active_node is not None
                and str(active_node.node_id) != str(expected_bridge_namespace)
            ):
                # A delayed cross-worker message for a deleted row must not
                # remove a replacement row that reused the public numeric id.
                return
            namespace = str(
                expected_bridge_namespace
                or (active_node.node_id if active_node is not None else "")
            )
            if permanent_delete and namespace:
                self._deleted_node_namespaces.add(namespace)
            if self._uses_shared_revocation_store and permanent_delete:
                if coordinator is None:
                    raise NodeAPIError(503, "shared node lifecycle memory is unavailable")
                if not namespace:
                    raise NodeAPIError(503, f"cannot durably fence node {id} without its Bridge namespace")
                # This durable marker is the correctness mechanism. The later
                # broadcast is only a prompt for sibling-local cleanup.
                await coordinator.mark_deleted(namespace)
            self._removing_node_ids.add(id)
            old_node: PasarGuardNode | None = self._nodes.pop(id, None)
            if old_node is not None:
                self._retiring_nodes.setdefault(id, []).append(old_node)
            retiring = list(self._retiring_nodes.get(id, ()))

        # Stop outside the topology lock, but do not return success (and do
        # not let callers purge shared fencing state) until every runtime is
        # confirmed quiescent.  A failed/ambiguous Stop remains visible in
        # _retiring_nodes so revocation preflight continues to fail closed.
        results = await asyncio.gather(
            *(self._shutdown_node(node, remote_stop=remote_stop) for node in retiring),
            return_exceptions=True,
        )
        failed = [node for node, result in zip(retiring, results) if result is not True]
        succeeded = [node for node, result in zip(retiring, results) if result is True]
        async with self._lock.writer_lock:
            current = self._retiring_nodes.get(id, [])
            if succeeded:
                current = [node for node in current if node not in succeeded]
            if current:
                self._retiring_nodes[id] = current
            else:
                self._retiring_nodes.pop(id, None)
                self._user_sync_locks.pop(id, None)
                self._removing_node_ids.discard(id)
        if failed:
            raise NodeAPIError(503, f"cannot confirm node {id} runtime shutdown")

    async def get_node(self, id: int) -> PasarGuardNode | None:
        async with self._lock.reader_lock:
            return self._nodes.get(id, None)

    async def get_lifecycle_recovery_node(self, id: int) -> PasarGuardNode | None:
        """Return the active controller or a retained ambiguous retiree."""
        async with self._lock.reader_lock:
            active = self._nodes.get(id)
            if active is not None:
                return active
            retiring = self._retiring_nodes.get(id, ())
            return retiring[-1] if retiring else None

    async def get_bridge_namespace(self, id: int) -> str | None:
        async with self._lock.reader_lock:
            node = self._nodes.get(id)
            return None if node is None else str(node.node_id)

    async def get_nodes(self) -> dict[int, PasarGuardNode]:
        async with self._lock.reader_lock:
            return self._nodes

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
            return [
                *self._nodes.items(),
                *((node_id, node) for node_id, retiring in self._retiring_nodes.items() for node in retiring),
            ]

    @staticmethod
    def _chunk_users(users: list[ProtoUser], size: int) -> list[list[ProtoUser]]:
        return [users[start : start + size] for start in range(0, len(users), size)]

    async def _sync_user_batch_to_node(
        self,
        node: PasarGuardNode,
        batch: list[ProtoUser],
        *,
        revocation_id: str | None = None,
    ) -> int:
        users_to_sync = batch
        supports_chunked = True
        supports_chunked_check = getattr(node, "_supports_chunked_sync", None)
        if callable(supports_chunked_check):
            supports_chunked, _ = await supports_chunked_check()

        if supports_chunked:
            kwargs = {
                "chunk_size": len(batch),
                "flush_pending": False,
            }
            if revocation_id is not None:
                # Passing this only for the new revocation path preserves
                # compatibility with older custom bridge subclasses used by
                # ordinary background sync.
                kwargs["revocation_id"] = revocation_id
            users_to_sync = await node.sync_users_chunked(batch, **kwargs)
            if not users_to_sync:
                return 0

            # A revocation permit covers the public direct request. Falling
            # through to the bridge's private batch helper would bypass that
            # permit and reopen the stale-update race.
            if revocation_id is not None:
                return len(users_to_sync)

        elif revocation_id is not None:
            # SyncUsers is a full replacement on the Go node. Sending a
            # one-user removal/restoration through it would erase every other
            # account. Permanent revocation therefore requires the guaranteed
            # partial chunked endpoint and fails closed on legacy nodes.
            raise NodeRevocationError("node does not support partial chunked sync required for user revocation")

        sync_batch_users = getattr(node, "_sync_batch_users", None)
        if callable(sync_batch_users):
            users_to_sync = await sync_batch_users(users_to_sync)

        return len(users_to_sync)

    @staticmethod
    def _user_key(user: ProtoUser) -> str:
        # PasarGuardNodeBridge's protobuf has no panel database `id` field.
        # The serializer intentionally stores that stable ID in `email`.
        return user.email

    def _without_deleted_users(self, users: list[ProtoUser]) -> list[ProtoUser]:
        return [user for user in users if self._user_key(user) not in self._deleted_user_keys]

    async def _sync_users_to_node(
        self,
        node_id: int,
        node: PasarGuardNode,
        users: list[ProtoUser],
        *,
        allow_deleted: bool = False,
        revocation_id: str | None = None,
        allowed_user_keys: frozenset[str] | None = None,
    ):
        batch_size = max(1, nats_settings.node_update_users_batch_size)
        lock = self._user_sync_locks.setdefault(node_id, asyncio.Lock())
        failed_count = 0

        async with lock:
            for batch in self._chunk_users(users, batch_size):
                current_batch = (
                    batch if allow_deleted or self._uses_shared_revocation_store else self._without_deleted_users(batch)
                )
                if allowed_user_keys is not None:
                    current_batch = [user for user in current_batch if self._user_key(user) in allowed_user_keys]
                if current_batch:
                    failed_count += await self._sync_user_batch_to_node(
                        node,
                        current_batch,
                        revocation_id=revocation_id,
                    )

        if failed_count:
            raise RuntimeError(f"failed to sync {failed_count}/{len(users)} users to node {node_id}")

    async def _update_users(
        self,
        users: list[ProtoUser],
        *,
        raise_on_failure: bool = False,
        allow_deleted: bool = False,
        revocation_id: str | None = None,
        node_items: list[tuple[int, PasarGuardNode]] | None = None,
        node_user_keys: dict[int, frozenset[str]] | None = None,
    ):
        if not allow_deleted and not self._uses_shared_revocation_store:
            users = self._without_deleted_users(users)
        if not users:
            return

        nodes = node_items if node_items is not None else await self._snapshot_node_items()
        if not nodes:
            # There are no active runtime nodes that could admit this user.
            return

        results = await asyncio.gather(
            *(
                self._sync_users_to_node(
                    node_id,
                    node,
                    users,
                    allow_deleted=allow_deleted,
                    revocation_id=revocation_id,
                    allowed_user_keys=None if node_user_keys is None else node_user_keys[node_id],
                )
                for node_id, node in nodes
            ),
            return_exceptions=True,
        )
        # ``asyncio.CancelledError`` is a ``BaseException``. With
        # ``return_exceptions=True`` a node task which cancels itself is
        # returned as a result, rather than cancelling this caller. Treat that
        # as an unconfirmed revocation: silently accepting it could let the
        # database delete commit while one node still has the user.
        failures = [
            (node_id, result) for (node_id, _), result in zip(nodes, results) if isinstance(result, BaseException)
        ]
        for node_id, failure in failures:
            self.logger.error("Failed to sync users to node %s: %s", node_id, failure)
        if failures and raise_on_failure:
            failed_node_ids = ", ".join(str(node_id) for node_id, _ in failures)
            raise NodeRevocationError(
                f"failed to sync users to {len(failures)}/{len(nodes)} nodes (node ids: {failed_node_ids})"
            ) from failures[0][1]

    async def update_users(self, users: list[ProtoUser]) -> None:
        asyncio.create_task(self._update_users(users))

    async def update_users_and_wait(self, users: list[ProtoUser]) -> None:
        """Synchronize a removal-sensitive batch and surface node failures."""
        await self._update_users(users, raise_on_failure=True)

    async def wait_for_user_revocations(self) -> None:
        """Delay node startup until every provisional delete is resolved."""
        await self._revocations_idle.wait()

    def filter_permanently_deleted_users(self, users: list[ProtoUser]) -> list[ProtoUser]:
        """Keep an old transaction snapshot from reintroducing tombstoned users."""
        return [user for user in users if self._user_key(user) not in self._deleted_user_keys]

    def _acquire_deletion_fences(self, user_keys: set[str], revocation_id: str) -> None:
        self._revocations_idle.clear()
        for user_key in user_keys:
            # An absent owner entry for an already deleted key denotes a
            # committed tombstone. Do not make it provisional again if a stale
            # or duplicate revoke arrives after the database commit.
            if user_key in self._deleted_user_keys and user_key not in self._deletion_fence_owners:
                continue
            self._deletion_fence_owners.setdefault(user_key, set()).add(revocation_id)
        self._deleted_user_keys.update(user_keys)

    def _release_deletion_fences(self, user_keys: set[str], revocation_id: str) -> None:
        for user_key in user_keys:
            owners = self._deletion_fence_owners.get(user_key)
            if owners is None:
                continue
            owners.discard(revocation_id)
            if not owners:
                self._deletion_fence_owners.pop(user_key, None)
                self._deleted_user_keys.discard(user_key)
        if not self._deletion_fence_owners:
            self._revocations_idle.set()

    def _finalize_deletion_fences(self, user_keys: set[str], revocation_id: str) -> None:
        for user_key in user_keys:
            owners = self._deletion_fence_owners.get(user_key)
            if owners is None or revocation_id not in owners:
                continue
            # Once any overlapping delete commits, the tombstone is permanent.
            # Drop every per-operation owner so successful deletes do not leak
            # revocation IDs and a later abort cannot undo the committed fence.
            self._deletion_fence_owners.pop(user_key, None)
        if not self._deletion_fence_owners:
            self._revocations_idle.set()

    def _record_revocation_nodes(
        self,
        revocation_id: str,
        nodes: list[tuple[int, PasarGuardNode, frozenset[str]]],
    ) -> None:
        """Merge separately transported chunks without losing earlier keys."""
        current = self._revocation_nodes.setdefault(revocation_id, [])
        by_identity = {(node_id, id(node)): index for index, (node_id, node, _) in enumerate(current)}
        for node_id, node, active_user_keys in nodes:
            if not active_user_keys:
                continue
            identity = (node_id, id(node))
            index = by_identity.get(identity)
            if index is None:
                by_identity[identity] = len(current)
                current.append((node_id, node, active_user_keys))
                continue
            old_node_id, old_node, old_keys = current[index]
            current[index] = (old_node_id, old_node, old_keys | active_user_keys)

    def _peek_revocation_nodes(
        self,
        revocation_id: str,
        user_keys: set[str],
    ) -> list[tuple[int, PasarGuardNode, frozenset[str]]] | None:
        """Read this RPC chunk without losing retry state on close failure."""
        current = self._revocation_nodes.get(revocation_id)
        if current is None:
            return None
        selected: list[tuple[int, PasarGuardNode, frozenset[str]]] = []
        for node_id, node, active_user_keys in current:
            selected_keys = active_user_keys & user_keys
            if selected_keys:
                selected.append((node_id, node, frozenset(selected_keys)))
        return selected

    def _discard_revocation_nodes(self, revocation_id: str, user_keys: set[str]) -> None:
        """Forget a chunk only after every bridge close has been acknowledged."""
        current = self._revocation_nodes.get(revocation_id)
        if current is None:
            return
        remaining: list[tuple[int, PasarGuardNode, frozenset[str]]] = []
        for node_id, node, active_user_keys in current:
            remaining_keys = active_user_keys - user_keys
            if remaining_keys:
                remaining.append((node_id, node, frozenset(remaining_keys)))
        if remaining:
            self._revocation_nodes[revocation_id] = remaining
        else:
            self._revocation_nodes.pop(revocation_id, None)

    def _restorable_users(self, users: list[ProtoUser], revocation_id: str) -> list[ProtoUser]:
        """Return users which are still owned exclusively by this failed delete."""
        restorable = []
        for user in users:
            user_key = self._user_key(user)
            owners = self._deletion_fence_owners.get(user_key)
            if owners == {revocation_id}:
                restorable.append(user)
        return restorable

    async def _restore_users_to_node(
        self,
        node_id: int,
        node: PasarGuardNode,
        users: list[ProtoUser],
        revocation_id: str,
        active_user_keys: frozenset[str],
    ) -> bool:
        """Restore authoritative DB state and leave an ordered retry behind."""
        lock = self._user_sync_locks.setdefault(node_id, asyncio.Lock())
        async with lock:
            candidate_users = (
                users if self._uses_shared_revocation_store else self._restorable_users(users, revocation_id)
            )
            current_users = [user for user in candidate_users if self._user_key(user) in active_user_keys]
            direct_succeeded = True
            for batch in self._chunk_users(current_users, max(1, nats_settings.node_update_users_batch_size)):
                try:
                    if await self._sync_user_batch_to_node(
                        node,
                        batch,
                        revocation_id=revocation_id,
                    ):
                        direct_succeeded = False
                except BaseException as exc:
                    direct_succeeded = False
                    self.logger.error("Failed to restore users immediately on node %s: %s", node_id, exc)

            abort = getattr(node, "abort_user_revocation", None)
            if not callable(abort):
                self.logger.error("Node %s bridge does not support revocation abort", node_id)
                return False
            try:
                await abort(sorted(active_user_keys), revocation_id)
            except BaseException as exc:
                self.logger.error("Failed to abort user revocation fence on node %s: %s", node_id, exc)
                return False

            queue_succeeded = False
            if current_users:
                try:
                    # Once the distributed fence is released, leave the
                    # authoritative original state in the retry queue as well.
                    await node.update_users(current_users)
                    queue_succeeded = True
                except BaseException as exc:
                    self.logger.error("Failed to queue user restoration for node %s: %s", node_id, exc)
            else:
                queue_succeeded = True

            return direct_succeeded or queue_succeeded

    async def _restore_failed_revocation(
        self,
        nodes: list[tuple[int, PasarGuardNode, frozenset[str]]],
        users: list[ProtoUser],
        revocation_id: str,
    ) -> list[int]:
        if not users or not nodes:
            return []
        results = await asyncio.gather(
            *(
                self._restore_users_to_node(node_id, node, users, revocation_id, active_user_keys)
                for node_id, node, active_user_keys in nodes
            ),
            return_exceptions=True,
        )
        return [
            node_id
            for (node_id, _, _), result in zip(nodes, results)
            if isinstance(result, BaseException) or result is not True
        ]

    @staticmethod
    async def _unavailable_revocation_nodes(nodes: list[tuple[int, PasarGuardNode]]) -> list[int]:
        health = await asyncio.gather(*(node.get_health() for _, node in nodes), return_exceptions=True)
        return [
            node_id
            for (node_id, node), result in zip(nodes, health)
            if (
                isinstance(result, BaseException)
                or result != Health.HEALTHY
                or not callable(getattr(node, "begin_user_revocation", None))
                or not callable(getattr(node, "abort_user_revocation", None))
                or not callable(getattr(node, "finalize_user_revocation", None))
            )
        ]

    @staticmethod
    def _require_complete_revocation_topology(
        nodes: list[tuple[int, PasarGuardNode]],
        expected_node_ids: set[int] | None,
    ) -> None:
        if expected_node_ids is None:
            return
        missing_node_ids = expected_node_ids - {node_id for node_id, _ in nodes}
        if missing_node_ids:
            node_ids = ", ".join(str(node_id) for node_id in sorted(missing_node_ids))
            raise NodeRevocationError(
                f"runtime topology is incomplete for user revocation (missing node ids: {node_ids})"
            )

    async def _begin_node_revocations(
        self,
        nodes: list[tuple[int, PasarGuardNode]],
        user_keys: set[str],
        revocation_id: str,
    ) -> list[tuple[int, PasarGuardNode, frozenset[str]]]:
        prepared: list[tuple[int, PasarGuardNode, frozenset[str]]] = []
        for node_id, node in nodes:
            begin = node.begin_user_revocation
            try:
                result = await begin(sorted(user_keys), revocation_id)
                active_user_keys = frozenset(result.active_user_keys)
                finalized_user_keys = frozenset(result.finalized_user_keys)
                if active_user_keys & finalized_user_keys or active_user_keys | finalized_user_keys != user_keys:
                    raise NodeRevocationError("node bridge returned an invalid user revocation result")
            except BaseException:
                nodes_to_unwind = [
                    *((prepared_node_id, prepared_node) for prepared_node_id, prepared_node, _ in prepared),
                    (node_id, node),
                ]

                async def unwind(nodes_to_unwind=nodes_to_unwind) -> None:
                    # begin may persist its fences before waiting for active
                    # leases, so the current node is ambiguous as well.
                    for _, prepared_node in reversed(nodes_to_unwind):
                        try:
                            await prepared_node.abort_user_revocation(sorted(user_keys), revocation_id)
                        except BaseException as abort_exc:
                            self.logger.error("Failed to unwind prepared user revocation: %s", abort_exc)

                unwind_task = asyncio.create_task(unwind())
                try:
                    await asyncio.shield(unwind_task)
                except asyncio.CancelledError:
                    await unwind_task
                    raise
                raise
            prepared.append((node_id, node, active_user_keys))
        return prepared

    @classmethod
    def _resolve_revocation_id(cls, users: list[ProtoUser], revocation_id: str | None) -> str:
        if revocation_id:
            return revocation_id
        # Rolling upgrades can pair legacy revoke/abort calls only through data
        # visible to both requests. A stable digest avoids an unobservable UUID.
        user_keys = "\0".join(sorted({cls._user_key(user) for user in users}))
        return f"legacy:{hashlib.sha256(user_keys.encode()).hexdigest()}"

    async def revoke_users_and_wait(
        self,
        users: list[ProtoUser],
        revocation_id: str | None = None,
        restore_users: list[ProtoUser] | None = None,
        *,
        expected_node_ids: set[int] | None = None,
    ) -> str:
        """Fence permanent deletions before removing users from every node."""
        revocation_id = self._resolve_revocation_id(users, revocation_id)
        user_keys = {self._user_key(user) for user in users}
        restore_users = restore_users or list(users)
        restore_user_keys = {self._user_key(user) for user in restore_users}
        if restore_user_keys != user_keys:
            raise NodeRevocationError("removal and restoration users do not match")

        if not self._uses_shared_revocation_store:
            self._acquire_deletion_fences(user_keys, revocation_id)
        nodes: list[tuple[int, PasarGuardNode]] = []
        prepared_nodes: list[tuple[int, PasarGuardNode, frozenset[str]]] = []
        revocation_started = False
        try:
            nodes = await self._snapshot_node_items()
            self._require_complete_revocation_topology(nodes, expected_node_ids)
            unavailable_node_ids = await self._unavailable_revocation_nodes(nodes)
            if unavailable_node_ids:
                node_ids = ", ".join(str(node_id) for node_id in unavailable_node_ids)
                raise NodeRevocationError(f"runtime nodes are not ready for user revocation (node ids: {node_ids})")

            prepared_nodes = await self._begin_node_revocations(nodes, user_keys, revocation_id)
            revocation_started = True
            await self._update_users(
                users,
                raise_on_failure=True,
                allow_deleted=True,
                revocation_id=revocation_id,
                node_items=[(node_id, node) for node_id, node, _ in prepared_nodes],
                node_user_keys={node_id: active_user_keys for node_id, _, active_user_keys in prepared_nodes},
            )
        except BaseException as exc:
            # The database row is kept when revocation is not confirmed, so
            # every possibly-mutated node must converge back to the original
            # authoritative state before normal updates are admitted again.
            restoration_failures: list[int] = []
            try:
                if revocation_started:
                    task = asyncio.create_task(
                        self._restore_failed_revocation(prepared_nodes, restore_users, revocation_id)
                    )
                    try:
                        restoration_failures = await asyncio.shield(task)
                    except asyncio.CancelledError:
                        # A second cancellation must not let the caller tear
                        # down the local fence while compensation is still
                        # mutating the nodes. Finish it before propagating the
                        # original cancellation.
                        restoration_failures = await task
                        raise
                elif prepared_nodes:
                    await asyncio.gather(
                        *(
                            node.abort_user_revocation(sorted(active_user_keys), revocation_id)
                            for _, node, active_user_keys in prepared_nodes
                            if active_user_keys
                        ),
                        return_exceptions=True,
                    )
            finally:
                if not self._uses_shared_revocation_store:
                    self._release_deletion_fences(user_keys, revocation_id)

            if restoration_failures and not isinstance(exc, asyncio.CancelledError):
                failed_node_ids = ", ".join(str(node_id) for node_id in restoration_failures)
                raise NodeRevocationError(
                    f"user revocation failed and restoration was not accepted by nodes: {failed_node_ids}"
                ) from exc
            if not isinstance(exc, (NodeRevocationError, asyncio.CancelledError)):
                raise NodeRevocationError(f"cannot confirm user revocation: {exc}") from exc
            raise
        if not self._uses_shared_revocation_store:
            self._record_revocation_nodes(revocation_id, prepared_nodes)
        return revocation_id

    async def abort_user_revocations(
        self,
        users: list[ProtoUser],
        revocation_id: str | None = None,
        restore_users: list[ProtoUser] | None = None,
        *,
        expected_node_ids: set[int] | None = None,
    ) -> None:
        """Restore users and release provisional fences after a DB rollback."""
        revocation_id = self._resolve_revocation_id(users, revocation_id)
        user_keys = {self._user_key(user) for user in users}
        nodes = self._peek_revocation_nodes(revocation_id, user_keys)
        if not nodes:
            topology = await self._snapshot_node_items()
            self._require_complete_revocation_topology(topology, expected_node_ids)
            nodes = [(node_id, node, frozenset(user_keys)) for node_id, node in topology]
        failures = await self._restore_failed_revocation(nodes, restore_users or [], revocation_id)
        if failures:
            failed_node_ids = ", ".join(str(node_id) for node_id in failures)
            raise NodeRevocationError(f"failed to restore users after database rollback on nodes: {failed_node_ids}")
        if not self._uses_shared_revocation_store:
            self._discard_revocation_nodes(revocation_id, user_keys)
            self._release_deletion_fences(user_keys, revocation_id)

    async def finalize_user_revocations(
        self,
        users: list[ProtoUser],
        revocation_id: str | None = None,
        *,
        expected_node_ids: set[int] | None = None,
    ) -> None:
        """Commit deletion tombstones and discard per-operation ownership."""
        revocation_id = self._resolve_revocation_id(users, revocation_id)
        user_keys = {self._user_key(user) for user in users}
        nodes = self._peek_revocation_nodes(revocation_id, user_keys)
        if not nodes:
            topology = await self._snapshot_node_items()
            self._require_complete_revocation_topology(topology, expected_node_ids)
            nodes = [(node_id, node, frozenset(user_keys)) for node_id, node in topology]
        results = await asyncio.gather(
            *(
                node.finalize_user_revocation(sorted(active_user_keys), revocation_id)
                for _, node, active_user_keys in nodes
                if active_user_keys
                if callable(getattr(node, "finalize_user_revocation", None))
            ),
            return_exceptions=True,
        )
        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            raise NodeRevocationError(f"failed to finalize revocation fences on {len(failures)} nodes") from failures[0]
        if not self._uses_shared_revocation_store:
            self._discard_revocation_nodes(revocation_id, user_keys)
            self._finalize_deletion_fences(user_keys, revocation_id)

    async def update_user(self, user: ProtoUser) -> None:
        user_key = self._user_key(user)
        if not self._uses_shared_revocation_store and user_key in self._deleted_user_keys:
            return

        nodes = await self._snapshot_node_items()
        if not nodes:
            return

        async def sync_one(node_id: int, node: PasarGuardNode) -> None:
            lock = self._user_sync_locks.setdefault(node_id, asyncio.Lock())
            async with lock:
                if not self._uses_shared_revocation_store and user_key in self._deleted_user_keys:
                    return
                await node.update_user(user)

        results = await asyncio.gather(*(sync_one(node_id, node) for node_id, node in nodes), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                raise result


node_manager: NodeManager = NodeManager()


__all__ = ["core_users", "node_manager"]

import asyncio

from aiorwlock import RWLock
from PasarGuardNodeBridge import Health, NodeType, PasarGuardNode, create_node
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser

from app.db.models import Node, NodeConnectionType
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
        self._user_sync_locks: dict[int, asyncio.Lock] = {}
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
            "extra": {"id": node.id, "usage_coefficient": node.usage_coefficient},
            "node_id": str(node.id),
        }
        store, coordinator, worker_id = get_bridge_memory()
        if store is not None and coordinator is not None:
            kwargs["user_sync_store"] = store
            kwargs["lifecycle_coordinator"] = coordinator
            kwargs["worker_id"] = worker_id
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

    async def update_node(self, node: Node) -> PasarGuardNode:
        await ensure_bridge_memory()

        # Serialize against in-flight full syncs (sync_full) so a reconnect/health-check
        # restart doesn't swap the node object out from under a slow peer sync — that race
        # is what turns a slow sync into a stop/start restart loop.
        lock = self._user_sync_locks.setdefault(node.id, asyncio.Lock())
        async with lock:
            async with self._lock.writer_lock:
                old_node: PasarGuardNode | None = self._nodes.pop(node.id, None)

                new_node = create_node(**self._create_node_kwargs(node))

                self._nodes[node.id] = new_node

            # Stop the old node after releasing the lock.
            await self._shutdown_node(old_node)

        return new_node

    async def remove_node(self, id: int, *, remote_stop: bool = True) -> None:
        async with self._lock.writer_lock:
            old_node: PasarGuardNode | None = self._nodes.pop(id, None)
            self._user_sync_locks.pop(id, None)

        # Do cleanup without holding the lock to avoid slow delete operations.
        asyncio.create_task(self._shutdown_node(old_node, remote_stop=remote_stop))

    async def get_node(self, id: int) -> PasarGuardNode | None:
        async with self._lock.reader_lock:
            return self._nodes.get(id, None)

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
            return list(self._nodes.items())

    @staticmethod
    def _chunk_users(users: list[ProtoUser], size: int) -> list[list[ProtoUser]]:
        return [users[start : start + size] for start in range(0, len(users), size)]

    async def _sync_user_batch_to_node(self, node: PasarGuardNode, batch: list[ProtoUser]) -> int:
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
                return 0

        sync_batch_users = getattr(node, "_sync_batch_users", None)
        if callable(sync_batch_users):
            users_to_sync = await sync_batch_users(users_to_sync)

        return len(users_to_sync)

    async def _sync_users_to_node(self, node_id: int, node: PasarGuardNode, users: list[ProtoUser]):
        batch_size = max(1, nats_settings.node_update_users_batch_size)
        lock = self._user_sync_locks.setdefault(node_id, asyncio.Lock())
        failed_count = 0

        async with lock:
            for batch in self._chunk_users(users, batch_size):
                failed_count += await self._sync_user_batch_to_node(node, batch)

        if failed_count:
            raise RuntimeError(f"failed to sync {failed_count}/{len(users)} users to node {node_id}")

    async def sync_full(
        self, node_id: int, users: list[ProtoUser], *, flush_pending: bool = False
    ) -> PasarGuardNode | None:
        """Push a full user snapshot to a node, serialized against update_node/remove_node.

        Guards against the reconnect/health-check watchdog tearing down the node object
        mid-sync (which previously restarted the sync from scratch and could loop).
        """
        lock = self._user_sync_locks.setdefault(node_id, asyncio.Lock())
        async with lock:
            node = await self.get_node(node_id)
            if node is None:
                return None
            await node.sync_users(users, flush_pending=flush_pending)
            return node

    async def _update_users(self, users: list[ProtoUser]):
        nodes = await self._snapshot_node_items()
        if not nodes:
            return

        results = await asyncio.gather(
            *(self._sync_users_to_node(node_id, node, users) for node_id, node in nodes), return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                self.logger.error("Failed to sync users to one of the nodes: %s", result)

    async def update_users(self, users: list[ProtoUser]) -> None:
        asyncio.create_task(self._update_users(users))

    async def update_user(self, user: ProtoUser) -> None:
        nodes = await self._snapshot_nodes()
        if not nodes:
            return

        results = await asyncio.gather(*(node.update_user(user) for node in nodes), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                raise result


node_manager: NodeManager = NodeManager()


__all__ = ["core_users", "node_manager"]

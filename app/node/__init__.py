import asyncio

from aiorwlock import RWLock
from PasarGuardNodeBridge import Health, NodeType, PasarGuardNode, create_node
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser

from app.db.models import Node, NodeConnectionType
from app.node.user import core_users
from app.utils.logger import get_logger

type_map = {
    NodeConnectionType.rest: NodeType.rest,
    NodeConnectionType.grpc: NodeType.grpc,
}


class NodeManager:
    def __init__(self):
        self._nodes: dict[int, PasarGuardNode] = {}
        self._lock = RWLock(fast=True)
        self.logger = get_logger("node-manager")

    async def _shutdown_node(self, node: PasarGuardNode | None):
        if node is None:
            return

        try:
            await node.set_health(Health.INVALID)
            await node.stop()
        except Exception:
            pass

    async def update_node(self, node: Node) -> PasarGuardNode:
        async with self._lock.writer_lock:
            old_node: PasarGuardNode | None = self._nodes.pop(node.id, None)

            new_node = create_node(
                connection=type_map[node.connection_type],
                address=node.address,
                port=node.port,
                api_port=node.api_port,
                server_ca=node.server_ca,
                api_key=node.api_key,
                name=node.name,
                logger=self.logger,
                default_timeout=node.default_timeout,
                internal_timeout=node.internal_timeout,
                proxy=node.proxy_url,
                extra={"id": node.id, "usage_coefficient": node.usage_coefficient},
            )

            self._nodes[node.id] = new_node

        # Stop the old node after releasing the lock.
        await self._shutdown_node(old_node)

        return new_node

    async def remove_node(self, id: int) -> None:
        async with self._lock.writer_lock:
            old_node: PasarGuardNode | None = self._nodes.pop(id, None)

        # Do cleanup without holding the lock to avoid slow delete operations.
        asyncio.create_task(self._shutdown_node(old_node))

    async def get_node(self, id: int) -> PasarGuardNode | None:
        async with self._lock.reader_lock:
            return self._nodes.get(id, None)

    async def get_nodes(self) -> dict[int, PasarGuardNode]:
        async with self._lock.reader_lock:
            return self._nodes

    async def _get_nodes_by_health(self, expected: Health) -> list[tuple[int, PasarGuardNode]]:
        async with self._lock.reader_lock:
            items = list(self._nodes.items())

        health_results = await asyncio.gather(
            *(node.get_health() for _, node in items),
            return_exceptions=True,
        )

        async with self._lock.reader_lock:
            matched = []
            for (node_id, node), health in zip(items, health_results):
                if isinstance(health, Exception):
                    self.logger.warning("Failed to get health for node %s: %s", node_id, health)
                    continue
                if health == expected and self._nodes.get(node_id) is node:
                    matched.append((node_id, node))
            return matched

    async def get_healthy_nodes(self) -> list[tuple[int, PasarGuardNode]]:
        return await self._get_nodes_by_health(Health.HEALTHY)

    async def get_broken_nodes(self) -> list[tuple[int, PasarGuardNode]]:
        return await self._get_nodes_by_health(Health.BROKEN)

    async def get_not_connected_nodes(self) -> list[tuple[int, PasarGuardNode]]:
        return await self._get_nodes_by_health(Health.NOT_CONNECTED)

    async def _snapshot_nodes(self) -> list[PasarGuardNode]:
        async with self._lock.reader_lock:
            return list(self._nodes.values())

    async def _update_users(self, users: list[ProtoUser]):
        nodes = await self._snapshot_nodes()
        if not nodes:
            return

        results = await asyncio.gather(*(node.update_users(users) for node in nodes), return_exceptions=True)
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

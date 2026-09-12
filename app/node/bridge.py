"""Keep bounded background sync batches on the node's delta-update endpoint."""

from contextvars import ContextVar

from PasarGuardNodeBridge import NodeType, PasarGuardNode
from PasarGuardNodeBridge.common.service_pb2 import User
from PasarGuardNodeBridge.grpclib import Node as GrpcNode
from PasarGuardNodeBridge.rest import Node as RestNode

_queued_sync: ContextVar[bool] = ContextVar("queued_node_user_sync", default=False)


class _QueuedBatchSync:
    async def _sync_worker(self):
        token = _queued_sync.set(True)
        try:
            await super()._sync_worker()
        finally:
            _queued_sync.reset(token)

    async def _sync_batch_users(self, users: list[User]) -> list[User]:
        # The bridge normally switches to per-user RPCs below 1000 users.
        # Bounded queue claims still need the efficient delta-batch endpoint.
        # Keep explicit per-user fallbacks outside the background worker intact.
        if _queued_sync.get() and users:
            supported, _ = await self._supports_chunked_sync()
            if supported:
                return await self.sync_users_chunked(
                    users, chunk_size=min(100, len(users)), flush_pending=False, timeout=self._internal_timeout
                )
        return await super()._sync_batch_users(users)


class QueuedGrpcNode(_QueuedBatchSync, GrpcNode):
    pass


class QueuedRestNode(_QueuedBatchSync, RestNode):
    pass


def create_node(connection: NodeType, **kwargs) -> PasarGuardNode:
    if connection is NodeType.grpc:
        return QueuedGrpcNode(**kwargs)
    if connection is NodeType.rest:
        return QueuedRestNode(**kwargs)
    raise ValueError("invalid backend type")

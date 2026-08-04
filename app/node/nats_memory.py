"""NATS JetStream KV backends for pasarguard-node-bridge shared memory."""

from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any
from uuid import uuid4

import nats
from nats.js.client import JetStreamContext
from nats.js.kv import KeyValue
from PasarGuardNodeBridge.common.service_pb2 import User
from PasarGuardNodeBridge.storage import (
    ClaimedUser,
    LifecycleLease,
    LifecycleOperation,
    LifecycleStatus,
    NodeLifecycleState,
)

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_jetstream_context, get_or_create_kv_bucket
from app.nats.kv_cas import CasKv, kv_cas_json, kv_get_json
from app.utils.logger import get_logger
from config import nats_settings

logger = get_logger("node-nats-memory")

WORKER_ID = f"{os.getpid()}:{uuid4().hex[:8]}"

_nc: nats.NATS | None = None
_user_sync_kv: KeyValue | None = None
_lifecycle_kv: KeyValue | None = None
_user_sync_store: NatsUserSyncStore | None = None
_lifecycle_coordinator: NatsNodeLifecycleCoordinator | None = None
_init_lock = asyncio.Lock()


def _b64_user(user: User) -> str:
    return base64.b64encode(user.SerializeToString()).decode("ascii")


def _user_from_b64(data: str) -> User:
    user = User()
    user.ParseFromString(base64.b64decode(data.encode("ascii")))
    return user


def _empty_sync_doc() -> dict[str, Any]:
    return {"pending": {}, "claimed": {}}


def _empty_lifecycle_doc() -> dict[str, Any]:
    return {"state": None, "lease": None}


def _state_from_dict(data: dict[str, Any] | None) -> NodeLifecycleState:
    if not data:
        return NodeLifecycleState()
    operation = data.get("operation")
    return NodeLifecycleState(
        desired=LifecycleStatus(data.get("desired", LifecycleStatus.UNKNOWN)),
        observed=LifecycleStatus(data.get("observed", LifecycleStatus.UNKNOWN)),
        epoch=int(data.get("epoch", 0)),
        operation=LifecycleOperation(operation) if operation else None,
        owner=data.get("owner"),
        node_version=data.get("node_version", "") or "",
        core_version=data.get("core_version", "") or "",
        updated_at=float(data.get("updated_at", 0.0) or 0.0),
    )


def _state_to_dict(state: NodeLifecycleState) -> dict[str, Any]:
    return {
        "desired": state.desired.value,
        "observed": state.observed.value,
        "epoch": state.epoch,
        "operation": state.operation.value if state.operation else None,
        "owner": state.owner,
        "node_version": state.node_version,
        "core_version": state.core_version,
        "updated_at": state.updated_at,
    }


class NatsUserSyncStore:
    def __init__(self, kv: CasKv):
        self._kv = kv

    def _key(self, node_id: str) -> str:
        return f"sync.{node_id}"

    async def enqueue_users(self, node_id: str, users: list[User]) -> None:
        if not users:
            return
        key = self._key(node_id)
        for _ in range(32):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                doc = _empty_sync_doc()
            pending = doc.setdefault("pending", {})
            for user in users:
                pending[user.email] = _b64_user(user)
            if await kv_cas_json(self._kv, key, doc, rev):
                return
        raise RuntimeError(f"failed to enqueue users for node {node_id} after CAS retries")

    async def claim_users(self, node_id: str, worker_id: str, limit: int, lease_seconds: float) -> list[ClaimedUser]:
        if limit <= 0:
            return []
        key = self._key(node_id)
        for _ in range(32):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                return []
            pending: dict[str, str] = doc.setdefault("pending", {})
            claimed: dict[str, dict[str, Any]] = doc.setdefault("claimed", {})

            for token, item in list(claimed.items()):
                if float(item.get("expires_at", 0)) <= now:
                    user_b64 = item.get("user")
                    if isinstance(user_b64, str):
                        user = _user_from_b64(user_b64)
                        pending.setdefault(user.email, user_b64)
                    del claimed[token]

            result: list[ClaimedUser] = []
            for email, user_b64 in list(pending.items()):
                token = f"{worker_id}:{uuid4()}"
                claimed[token] = {"user": user_b64, "expires_at": now + lease_seconds}
                result.append(ClaimedUser(token=token, user=_user_from_b64(user_b64)))
                del pending[email]
                if len(result) >= limit:
                    break

            if await kv_cas_json(self._kv, key, doc, rev):
                return result
        raise RuntimeError(f"failed to claim users for node {node_id} after CAS retries")

    async def ack_users(self, node_id: str, tokens: list[str]) -> None:
        if not tokens:
            return
        key = self._key(node_id)
        token_set = set(tokens)
        for _ in range(32):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                return
            claimed = doc.setdefault("claimed", {})
            for token in token_set:
                claimed.pop(token, None)
            if await kv_cas_json(self._kv, key, doc, rev):
                return
        raise RuntimeError(f"failed to ack users for node {node_id} after CAS retries")

    async def requeue_users(self, node_id: str, claimed_users: list[ClaimedUser]) -> None:
        if not claimed_users:
            return
        key = self._key(node_id)
        for _ in range(32):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                doc = _empty_sync_doc()
            pending = doc.setdefault("pending", {})
            claimed = doc.setdefault("claimed", {})
            for item in claimed_users:
                claimed.pop(item.token, None)
                pending.setdefault(item.user.email, _b64_user(item.user))
            if await kv_cas_json(self._kv, key, doc, rev):
                return
        raise RuntimeError(f"failed to requeue users for node {node_id} after CAS retries")

    async def clear(self, node_id: str) -> None:
        key = self._key(node_id)
        for _ in range(32):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                return
            if await kv_cas_json(self._kv, key, _empty_sync_doc(), rev):
                return
        raise RuntimeError(f"failed to clear users for node {node_id} after CAS retries")


class NatsNodeLifecycleCoordinator:
    def __init__(self, kv: CasKv):
        self._kv = kv

    def _key(self, node_id: str) -> str:
        return f"lifecycle.{node_id}"

    async def try_acquire(
        self, node_id: str, worker_id: str, operation: LifecycleOperation, lease_seconds: float
    ) -> LifecycleLease | None:
        key = self._key(node_id)
        for _ in range(32):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                doc = _empty_lifecycle_doc()

            lease_data = doc.get("lease")
            if lease_data is not None and float(lease_data.get("expires_at", 0)) > now:
                return None

            state = _state_from_dict(doc.get("state"))
            epoch = state.epoch + 1
            lease = LifecycleLease(
                node_id=node_id,
                worker_id=worker_id,
                operation=operation,
                token=f"{worker_id}:{uuid4()}",
                epoch=epoch,
                lease_seconds=lease_seconds,
            )
            state.epoch = epoch
            state.operation = operation
            state.owner = worker_id
            state.updated_at = now
            if operation is LifecycleOperation.START:
                state.desired = LifecycleStatus.HEALTHY
                state.observed = LifecycleStatus.STARTING
            elif operation is LifecycleOperation.STOP:
                state.desired = LifecycleStatus.STOPPED
                state.observed = LifecycleStatus.STOPPING

            doc["state"] = _state_to_dict(state)
            doc["lease"] = {
                "token": lease.token,
                "worker_id": worker_id,
                "operation": operation.value,
                "epoch": epoch,
                "lease_seconds": lease_seconds,
                "expires_at": now + lease_seconds,
            }
            if await kv_cas_json(self._kv, key, doc, rev):
                return lease
        return None

    async def release(self, lease: LifecycleLease, state_update: NodeLifecycleState | None = None) -> None:
        key = self._key(lease.node_id)
        for _ in range(32):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                return
            lease_data = doc.get("lease")
            if lease_data is None or lease_data.get("token") != lease.token:
                return

            state = state_update or _state_from_dict(doc.get("state"))
            if state.epoch != lease.epoch:
                state.epoch = lease.epoch
            state.operation = None
            state.owner = None
            state.updated_at = now
            doc["state"] = _state_to_dict(state)
            doc["lease"] = None
            if await kv_cas_json(self._kv, key, doc, rev):
                return

    async def heartbeat(self, lease: LifecycleLease) -> None:
        key = self._key(lease.node_id)
        for _ in range(32):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                return
            lease_data = doc.get("lease")
            if lease_data is None or lease_data.get("token") != lease.token:
                return
            lease_data["expires_at"] = now + lease.lease_seconds
            doc["lease"] = lease_data
            if await kv_cas_json(self._kv, key, doc, rev):
                return

    async def get_state(self, node_id: str) -> NodeLifecycleState | None:
        doc, _ = await kv_get_json(self._kv, self._key(node_id))
        if doc is None or doc.get("state") is None:
            return None
        return _state_from_dict(doc.get("state"))

    async def has_active_lease(self, node_id: str) -> bool:
        """True when another worker still holds an unexpired lifecycle lease."""
        doc, _ = await kv_get_json(self._kv, self._key(node_id))
        if doc is None:
            return False
        lease_data = doc.get("lease")
        if not lease_data:
            return False
        return float(lease_data.get("expires_at", 0)) > time.time()

    async def update_observed(self, node_id: str, observed: LifecycleStatus, expected_epoch: int | None = None) -> None:
        key = self._key(node_id)
        for _ in range(32):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                doc = _empty_lifecycle_doc()
            state = _state_from_dict(doc.get("state"))
            if expected_epoch is not None and state.epoch != expected_epoch:
                return
            state.observed = observed
            state.updated_at = now
            doc["state"] = _state_to_dict(state)
            if await kv_cas_json(self._kv, key, doc, rev):
                return


async def ensure_bridge_memory() -> tuple[NatsUserSyncStore | None, NatsNodeLifecycleCoordinator | None]:
    """Initialize shared bridge memory when NATS is enabled. Idempotent."""
    global _nc, _user_sync_kv, _lifecycle_kv, _user_sync_store, _lifecycle_coordinator

    if not is_nats_enabled():
        return None, None

    if _user_sync_store is not None and _lifecycle_coordinator is not None:
        return _user_sync_store, _lifecycle_coordinator

    async with _init_lock:
        if _user_sync_store is not None and _lifecycle_coordinator is not None:
            return _user_sync_store, _lifecycle_coordinator

        _nc = await create_nats_client()
        if _nc is None:
            return None, None

        js: JetStreamContext = await get_jetstream_context(_nc)
        _user_sync_kv = await get_or_create_kv_bucket(js, nats_settings.node_user_sync_kv_bucket)
        _lifecycle_kv = await get_or_create_kv_bucket(js, nats_settings.node_lifecycle_kv_bucket)
        if _user_sync_kv is None or _lifecycle_kv is None:
            logger.warning("Failed to create node bridge memory KV buckets")
            return None, None

        _user_sync_store = NatsUserSyncStore(_user_sync_kv)
        _lifecycle_coordinator = NatsNodeLifecycleCoordinator(_lifecycle_kv)
        logger.info("Node bridge NATS memory ready (worker_id=%s)", WORKER_ID)
        return _user_sync_store, _lifecycle_coordinator


def get_bridge_memory() -> tuple[NatsUserSyncStore | None, NatsNodeLifecycleCoordinator | None, str]:
    return _user_sync_store, _lifecycle_coordinator, WORKER_ID


async def shutdown_bridge_memory() -> None:
    global _nc, _user_sync_kv, _lifecycle_kv, _user_sync_store, _lifecycle_coordinator
    if _nc is not None:
        await _nc.close()
    _nc = None
    _user_sync_kv = None
    _lifecycle_kv = None
    _user_sync_store = None
    _lifecycle_coordinator = None

"""NATS JetStream KV backends for pasarguard-node-bridge shared memory."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
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
from app.nats.kv_cas import CasKv, kv_cas_json, kv_get_json, kv_list_keys, kv_put_json
from app.utils.logger import get_logger
from config import nats_settings

logger = get_logger("node-nats-memory")

WORKER_ID = f"{os.getpid()}:{uuid4().hex[:8]}"
# Stay under default NATS max_payload (1MiB) with headroom for JSON framing.
_MAX_USER_SYNC_VALUE_BYTES = min(900_000, nats_settings.node_command_max_payload_bytes)

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


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


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
    """Per-user pending / per-token claimed keys so each KV value stays payload-safe."""

    def __init__(self, kv: CasKv):
        self._kv = kv

    def _pending_prefix(self, node_id: str) -> str:
        return f"p.{node_id}."

    def _claimed_prefix(self, node_id: str) -> str:
        return f"c.{node_id}."

    def _pending_key(self, node_id: str, email: str) -> str:
        return f"{self._pending_prefix(node_id)}{_digest(email)}"

    def _claimed_key(self, node_id: str, token: str) -> str:
        return f"{self._claimed_prefix(node_id)}{_digest(token)}"

    def _ensure_value_size(self, key: str, value: dict[str, Any]) -> None:
        size = len(json.dumps(value, separators=(",", ":")).encode())
        if size > _MAX_USER_SYNC_VALUE_BYTES:
            raise RuntimeError(
                f"user sync KV value for key={key} is {size} bytes; exceeds limit {_MAX_USER_SYNC_VALUE_BYTES}"
            )

    async def enqueue_users(self, node_id: str, users: list[User]) -> None:
        if not users:
            return
        # Latest payload per email wins (dedupe across the batch first).
        by_email = {user.email: user for user in users}
        for email, user in by_email.items():
            key = self._pending_key(node_id, email)
            value = {"email": email, "user": _b64_user(user)}
            self._ensure_value_size(key, value)
            await kv_put_json(self._kv, key, value)

    async def _requeue_expired_claims(self, node_id: str) -> None:
        now = time.time()
        for key in await kv_list_keys(self._kv, self._claimed_prefix(node_id)):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                continue
            if float(doc.get("expires_at", 0)) > now:
                continue
            email = doc.get("email")
            user_b64 = doc.get("user")
            if isinstance(email, str) and isinstance(user_b64, str):
                pending_key = self._pending_key(node_id, email)
                pending_value = {"email": email, "user": user_b64}
                await kv_put_json(self._kv, pending_key, pending_value)
            try:
                await self._kv.delete(key, last=rev)
            except Exception as exc:
                logger.debug("Failed to delete expired claim key=%s: %s", key, exc)

    async def claim_users(self, node_id: str, worker_id: str, limit: int, lease_seconds: float) -> list[ClaimedUser]:
        if limit <= 0:
            return []
        await self._requeue_expired_claims(node_id)

        result: list[ClaimedUser] = []
        now = time.time()
        for pending_key in await kv_list_keys(self._kv, self._pending_prefix(node_id)):
            if len(result) >= limit:
                break
            doc, rev = await kv_get_json(self._kv, pending_key)
            if doc is None:
                continue
            email = doc.get("email")
            user_b64 = doc.get("user")
            if not isinstance(email, str) or not isinstance(user_b64, str):
                continue

            token = f"{worker_id}:{uuid4()}"
            claimed_key = self._claimed_key(node_id, token)
            claimed_value = {
                "token": token,
                "email": email,
                "user": user_b64,
                "expires_at": now + lease_seconds,
            }
            self._ensure_value_size(claimed_key, claimed_value)
            try:
                # Create-only so two workers cannot claim into the same token key.
                if not await kv_cas_json(self._kv, claimed_key, claimed_value, 0):
                    continue
                await self._kv.delete(pending_key, last=rev)
            except Exception as exc:
                logger.debug("Claim race for pending key=%s: %s", pending_key, exc)
                try:
                    await self._kv.delete(claimed_key)
                except Exception as cleanup_exc:
                    logger.debug(
                        "Failed to cleanup claimed key=%s after claim race: %s",
                        claimed_key,
                        cleanup_exc,
                    )
                continue
            result.append(ClaimedUser(token=token, user=_user_from_b64(user_b64)))
        return result

    async def ack_users(self, node_id: str, tokens: list[str]) -> None:
        if not tokens:
            return
        for token in tokens:
            key = self._claimed_key(node_id, token)
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                continue
            try:
                await self._kv.delete(key, last=rev)
            except Exception as exc:
                logger.debug("Failed to ack claim key=%s: %s", key, exc)

    async def requeue_users(self, node_id: str, claimed_users: list[ClaimedUser]) -> None:
        if not claimed_users:
            return
        for item in claimed_users:
            pending_key = self._pending_key(node_id, item.user.email)
            pending_value = {"email": item.user.email, "user": _b64_user(item.user)}
            self._ensure_value_size(pending_key, pending_value)
            await kv_put_json(self._kv, pending_key, pending_value)
            claimed_key = self._claimed_key(node_id, item.token)
            doc, rev = await kv_get_json(self._kv, claimed_key)
            if doc is None:
                continue
            try:
                await self._kv.delete(claimed_key, last=rev)
            except Exception as exc:
                logger.debug("Failed to delete requeued claim key=%s: %s", claimed_key, exc)

    async def clear(self, node_id: str) -> None:
        for key in await kv_list_keys(self._kv, self._pending_prefix(node_id)):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                continue
            try:
                await self._kv.delete(key, last=rev)
            except Exception as exc:
                logger.debug("Failed to clear pending key=%s: %s", key, exc)
        for key in await kv_list_keys(self._kv, self._claimed_prefix(node_id)):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                continue
            try:
                await self._kv.delete(key, last=rev)
            except Exception as exc:
                logger.debug("Failed to clear claimed key=%s: %s", key, exc)


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
        logger.warning("Lifecycle release CAS exhausted for node_id=%s key=%s", lease.node_id, key)

    async def heartbeat(self, lease: LifecycleLease) -> bool:
        key = self._key(lease.node_id)
        for _ in range(32):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                return False
            lease_data = doc.get("lease")
            if lease_data is None or lease_data.get("token") != lease.token:
                return False
            lease_data["expires_at"] = now + lease.lease_seconds
            doc["lease"] = lease_data
            if await kv_cas_json(self._kv, key, doc, rev):
                return True
        logger.warning("Lifecycle heartbeat CAS exhausted for node_id=%s key=%s", lease.node_id, key)
        return False

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
        logger.warning("Lifecycle update_observed CAS exhausted for node_id=%s key=%s", node_id, key)

    async def clear(self, node_id: str) -> None:
        key = self._key(node_id)
        doc, rev = await kv_get_json(self._kv, key)
        if doc is None:
            return
        try:
            await self._kv.delete(key, last=rev)
        except Exception as exc:
            logger.debug("Failed to clear lifecycle key=%s: %s", key, exc)


async def clear_bridge_memory_for_node(node_id: int | str) -> None:
    store, coordinator, _ = get_bridge_memory()
    nid = str(node_id)
    if store is not None:
        await store.clear(nid)
    if coordinator is not None:
        await coordinator.clear(nid)


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
            if _nc is not None:
                with contextlib.suppress(Exception):
                    await _nc.close()
            _nc = None
            _user_sync_kv = None
            _lifecycle_kv = None
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

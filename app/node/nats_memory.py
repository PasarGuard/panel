"""NATS JetStream KV backends for pasarguard-node-bridge shared memory."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import time
from contextvars import ContextVar, Token
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
    StartupUserSyncLease,
    UserRevocationConflictError,
    UserRevocationResult,
    UserSyncLease,
    UserSyncLeaseLostError,
)

from app.nats import needs_shared_bridge_memory
from app.nats.client import create_nats_client, get_jetstream_context, get_or_create_kv_bucket
from app.nats.kv_cas import CasKv, kv_cas_json, kv_get_json, kv_list_keys
from app.utils.logger import get_logger
from config import nats_settings

logger = get_logger("node-nats-memory")

_REVOCATION_METADATA_LEASE_SECONDS = 300.0

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
    """Generation-fenced user queue shared by every Panel/node worker."""

    def __init__(self, kv: CasKv):
        self._kv = kv
        self._authoritative_reconciliation_membership: ContextVar[
            tuple[str, str, frozenset[str]] | None
        ] = ContextVar(f"node-reconciliation-membership-{id(self)}", default=None)

    async def set_authoritative_reconciliation_membership(
        self, node_id: str, worker_id: str, user_keys: list[str]
    ) -> Token[tuple[str, str, frozenset[str]] | None]:
        """Supply row-locked global DB membership for one reconciliation scope."""
        return self._authoritative_reconciliation_membership.set(
            (node_id, worker_id, frozenset(user_keys))
        )

    def reset_authoritative_reconciliation_membership(
        self, token: Token[tuple[str, str, frozenset[str]] | None]
    ) -> None:
        """Synchronously end a DB-locked scope, including cancellation paths."""
        self._authoritative_reconciliation_membership.reset(token)

    def _pending_prefix(self, node_id: str) -> str:
        return f"p.{node_id}."

    def _claimed_prefix(self, node_id: str) -> str:
        return f"c.{node_id}."

    def _pending_key(self, node_id: str, email: str) -> str:
        return f"{self._pending_prefix(node_id)}{_digest(email)}"

    def _claimed_key(self, node_id: str, token: str) -> str:
        return f"{self._claimed_prefix(node_id)}{_digest(token)}"

    def _barrier_prefix(self, node_id: str) -> str:
        return f"b.{node_id}."

    def _barrier_key(self, node_id: str, user_key: str) -> str:
        return f"{self._barrier_prefix(node_id)}{_digest(user_key)}"

    def _execution_prefix(self, node_id: str) -> str:
        return f"x.{node_id}."

    def _execution_key(self, node_id: str, token: str) -> str:
        return f"{self._execution_prefix(node_id)}{_digest(token)}"

    def _revocation_lock_key(self, node_id: str) -> str:
        return f"m.{node_id}"

    def _epoch_key(self, node_id: str) -> str:
        return f"e.{node_id}"

    async def _next_user_sync_epoch(self, node_id: str) -> int:
        key = self._epoch_key(node_id)
        for _ in range(64):
            doc, rev = await kv_get_json(self._kv, key)
            epoch = int((doc or {}).get("epoch", 0)) + 1
            if await kv_cas_json(self._kv, key, {"epoch": epoch}, rev):
                return epoch
        raise RuntimeError(f"failed to reserve user-sync epoch key={key} after CAS retries")

    async def advance_user_sync_epoch(self, node_id: str, minimum_epoch: int) -> None:
        if minimum_epoch < 0:
            raise ValueError("minimum_epoch must be non-negative")
        key = self._epoch_key(node_id)
        for _ in range(64):
            doc, rev = await kv_get_json(self._kv, key)
            current = int((doc or {}).get("epoch", 0))
            if current >= minimum_epoch:
                return
            if await kv_cas_json(self._kv, key, {"epoch": minimum_epoch}, rev):
                return
        raise RuntimeError(f"failed to advance user-sync epoch key={key} after CAS retries")

    @contextlib.asynccontextmanager
    async def _revocation_lock(self, node_id: str, user_keys: list[str]):
        """Serialize multi-key revocation transitions for one node.

        The lease is long relative to the bounded metadata transition and is
        renewed while the owner is alive. Expiry remains fail-closed until the
        periodic authoritative DB-locked recovery resolves it.
        """
        key = self._revocation_lock_key(node_id)
        token = str(uuid4())
        acquired = False
        for _ in range(32):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            # Never steal an expired metadata lock. Its owner may merely be
            # paused and can still resume. Only authoritative recovery, while
            # holding the target DB row locks, may clear this evidence.
            if doc is not None:
                break
            value = {"token": token, "expires_at": now + _REVOCATION_METADATA_LEASE_SECONDS}
            if await kv_cas_json(self._kv, key, value, rev):
                acquired = True
                break
        if not acquired:
            raise UserRevocationConflictError(tuple(sorted(set(user_keys))))

        lease_lost = asyncio.Event()

        async def _assert_owned() -> None:
            if lease_lost.is_set():
                raise UserSyncLeaseLostError(f"revocation metadata lease was lost for node_id={node_id}")
            doc, _ = await kv_get_json(self._kv, key)
            if (
                doc is None
                or doc.get("token") != token
                or float(doc.get("expires_at", 0)) <= time.time()
            ):
                lease_lost.set()
                raise UserSyncLeaseLostError(f"revocation metadata lease was lost for node_id={node_id}")

        async def _renew() -> None:
            try:
                while True:
                    await asyncio.sleep(_REVOCATION_METADATA_LEASE_SECONDS / 3)
                    for _ in range(32):
                        doc, rev = await kv_get_json(self._kv, key)
                        if doc is None or doc.get("token") != token:
                            raise UserSyncLeaseLostError(
                                f"revocation metadata lease was lost for node_id={node_id}"
                            )
                        if float(doc.get("expires_at", 0)) <= time.time():
                            raise UserSyncLeaseLostError(
                                f"revocation metadata lease expired for node_id={node_id}"
                            )
                        doc["expires_at"] = time.time() + _REVOCATION_METADATA_LEASE_SECONDS
                        if await kv_cas_json(self._kv, key, doc, rev):
                            break
                    else:
                        raise UserSyncLeaseLostError(
                            f"revocation metadata lease heartbeat failed for node_id={node_id}"
                        )
            except asyncio.CancelledError:
                raise
            except BaseException:
                lease_lost.set()
                raise

        heartbeat = asyncio.create_task(_renew())
        body_failed = False
        try:
            yield _assert_owned
            await _assert_owned()
        except BaseException:
            body_failed = True
            raise
        finally:
            heartbeat.cancel()
            heartbeat_error: BaseException | None = None
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
            except BaseException as exc:
                heartbeat_error = exc

            async def _release() -> None:
                doc, rev = await kv_get_json(self._kv, key)
                if doc is not None and doc.get("token") == token:
                    await self._kv.delete(key, last=rev)

            release = asyncio.create_task(_release())
            try:
                await asyncio.shield(release)
            except asyncio.CancelledError:
                await release
                raise
            if heartbeat_error is not None and not body_failed:
                raise UserSyncLeaseLostError(
                    f"revocation metadata lease heartbeat failed for node_id={node_id}"
                ) from heartbeat_error

    async def _clear_expired_revocation_lock_for_recovery(
        self,
        node_id: str,
        authorization: tuple[str, str, frozenset[str]],
    ) -> None:
        """Clear stale metadata only for a row-locked authoritative recovery."""
        if authorization[0] != node_id:
            raise UserSyncLeaseLostError("authoritative database locks are required for metadata recovery")
        key = self._revocation_lock_key(node_id)
        for _ in range(32):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None or float(doc.get("expires_at", 0)) > time.time():
                return
            try:
                await self._kv.delete(key, last=rev)
                return
            except Exception as exc:
                logger.debug("Stale revocation metadata lock delete raced node_id=%s: %s", node_id, exc)
                continue
        raise RuntimeError(f"failed to clear stale revocation metadata lock node_id={node_id}")

    def _ensure_value_size(self, key: str, value: dict[str, Any]) -> None:
        size = len(json.dumps(value, separators=(",", ":")).encode())
        if size > _MAX_USER_SYNC_VALUE_BYTES:
            raise RuntimeError(
                f"user sync KV value for key={key} is {size} bytes; exceeds limit {_MAX_USER_SYNC_VALUE_BYTES}"
            )

    @staticmethod
    def _empty_barrier(user_key: str) -> dict[str, Any]:
        return {
            "user_key": user_key,
            "generation": 0,
            "active_owner": None,
            "closing": False,
            "permanent": False,
        }

    async def _get_barrier(self, node_id: str, user_key: str) -> tuple[dict[str, Any], int]:
        doc, rev = await kv_get_json(self._kv, self._barrier_key(node_id, user_key))
        if doc is None or doc.get("user_key") != user_key:
            return self._empty_barrier(user_key), rev
        return doc, rev

    @staticmethod
    def _barrier_allows(barrier: dict[str, Any], generation: int | None = None) -> bool:
        if barrier.get("permanent") or barrier.get("active_owner") is not None or barrier.get("closing"):
            return False
        return generation is None or int(barrier.get("generation", 0)) == generation

    @staticmethod
    def _barrier_allows_lease(barrier: dict[str, Any], generation: int, revocation_id: str | None) -> bool:
        if barrier.get("permanent") or int(barrier.get("generation", 0)) != generation:
            return False
        owner = barrier.get("active_owner")
        if revocation_id is not None:
            return owner == revocation_id and not barrier.get("closing")
        return owner is None and not barrier.get("closing")

    async def _delete_revision(self, key: str, revision: int) -> None:
        try:
            await self._kv.delete(key, last=revision)
        except Exception as exc:
            logger.debug("Failed to delete stale user sync key=%s: %s", key, exc)

    async def _put_pending_if_current(
        self,
        node_id: str,
        email: str,
        user_b64: str,
        generation: int,
        *,
        overwrite: bool,
    ) -> bool:
        """Put pending work only while the matching generation stays unfenced."""
        key = self._pending_key(node_id, email)
        value = {"email": email, "user": user_b64, "generation": generation}
        self._ensure_value_size(key, value)

        for _ in range(32):
            barrier, _ = await self._get_barrier(node_id, email)
            if not self._barrier_allows(barrier, generation):
                return False

            current, rev = await kv_get_json(self._kv, key)
            if current is not None and not overwrite:
                current_generation = int(current.get("generation", 0))
                if current_generation == generation:
                    return True
                if current_generation > generation:
                    return False
            if not await kv_cas_json(self._kv, key, value, rev):
                continue

            # A revoke may have fenced the key between the first read and the
            # pending CAS. Delete only our exact revision; a newer enqueue wins.
            written, written_rev = await kv_get_json(self._kv, key)
            barrier, _ = await self._get_barrier(node_id, email)
            if self._barrier_allows(barrier, generation):
                return True
            if written == value:
                await self._delete_revision(key, written_rev)
            return False
        raise RuntimeError(f"failed to enqueue user sync key={key} after CAS retries")

    async def enqueue_users(self, node_id: str, users: list[User]) -> None:
        if not users:
            return
        # Latest payload per email wins (dedupe across the batch first).
        by_email = {user.email: user for user in users}
        for email, user in by_email.items():
            barrier, _ = await self._get_barrier(node_id, email)
            if not self._barrier_allows(barrier):
                continue
            await self._put_pending_if_current(
                node_id,
                email,
                _b64_user(user),
                int(barrier.get("generation", 0)),
                overwrite=True,
            )

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
            generation = int(doc.get("generation", 0))
            if isinstance(email, str) and isinstance(user_b64, str):
                await self._put_pending_if_current(
                    node_id,
                    email,
                    user_b64,
                    generation,
                    overwrite=False,
                )
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
            generation = int(doc.get("generation", 0))
            barrier, _ = await self._get_barrier(node_id, email)
            if not self._barrier_allows(barrier, generation):
                await self._delete_revision(pending_key, rev)
                continue

            token = f"{worker_id}:{uuid4()}"
            claimed_key = self._claimed_key(node_id, token)
            claimed_value = {
                "token": token,
                "email": email,
                "user": user_b64,
                "generation": generation,
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
            # A fence installed after the pending delete invalidates this
            # claim. The worker would reject it at lease acquisition too, but
            # avoid returning known-stale work in the first place.
            barrier, _ = await self._get_barrier(node_id, email)
            if not self._barrier_allows(barrier, generation):
                claimed_doc, claimed_rev = await kv_get_json(self._kv, claimed_key)
                if claimed_doc is not None:
                    await self._delete_revision(claimed_key, claimed_rev)
                continue
            result.append(ClaimedUser(token=token, user=_user_from_b64(user_b64), generation=generation))
        return result

    async def next_claim_delay(self, node_id: str) -> float | None:
        """Return when valid queued work can next be claimed."""
        now = time.time()
        has_pending = False
        for key in await kv_list_keys(self._kv, self._pending_prefix(node_id)):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                continue
            email = doc.get("email")
            generation = int(doc.get("generation", 0))
            if not isinstance(email, str):
                await self._delete_revision(key, rev)
                continue
            barrier, _ = await self._get_barrier(node_id, email)
            if not self._barrier_allows(barrier, generation):
                await self._delete_revision(key, rev)
                continue
            has_pending = True
        if has_pending:
            return 0.0

        delay: float | None = None
        for key in await kv_list_keys(self._kv, self._claimed_prefix(node_id)):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                continue
            email = doc.get("email")
            generation = int(doc.get("generation", 0))
            if not isinstance(email, str):
                await self._delete_revision(key, rev)
                continue
            barrier, _ = await self._get_barrier(node_id, email)
            if not self._barrier_allows(barrier, generation):
                await self._delete_revision(key, rev)
                continue
            claim_delay = max(0.0, float(doc.get("expires_at", 0)) - now)
            delay = claim_delay if delay is None else min(delay, claim_delay)
        return delay

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
            claimed_key = self._claimed_key(node_id, item.token)
            doc, rev = await kv_get_json(self._kv, claimed_key)
            if doc is None:
                continue
            generation = int(getattr(item, "generation", 0))
            if (
                doc.get("token") != item.token
                or doc.get("email") != item.user.email
                or int(doc.get("generation", 0)) != generation
            ):
                continue
            user_b64 = doc.get("user")
            if not isinstance(user_b64, str):
                continue
            await self._put_pending_if_current(
                node_id,
                item.user.email,
                user_b64,
                generation,
                overwrite=False,
            )
            try:
                await self._kv.delete(claimed_key, last=rev)
            except Exception as exc:
                logger.debug("Failed to delete requeued claim key=%s: %s", claimed_key, exc)

    async def _set_revocation_owner(self, node_id: str, user_key: str, revocation_id: str) -> bool:
        """Acquire one key, returning False when it is already finalized."""
        key = self._barrier_key(node_id, user_key)
        for _ in range(32):
            doc, rev = await self._get_barrier(node_id, user_key)
            if doc.get("permanent"):
                return False
            owner = doc.get("active_owner")
            if owner == revocation_id and not doc.get("closing"):
                return True
            if owner is not None or doc.get("closing"):
                raise UserRevocationConflictError((user_key,))
            doc["active_owner"] = revocation_id
            doc["closing"] = False
            doc["generation"] = int(doc.get("generation", 0)) + 1
            if await kv_cas_json(self._kv, key, doc, rev):
                return True
        raise RuntimeError(f"failed to fence user sync key={user_key} after CAS retries")

    async def _clear_revocation_owner(self, node_id: str, user_key: str, revocation_id: str) -> None:
        key = self._barrier_key(node_id, user_key)
        for _ in range(32):
            doc, rev = await self._get_barrier(node_id, user_key)
            if doc.get("permanent") or doc.get("active_owner") != revocation_id:
                return
            doc["active_owner"] = None
            doc["closing"] = False
            if await kv_cas_json(self._kv, key, doc, rev):
                return
        raise RuntimeError(f"failed to release user revocation key={user_key} after CAS retries")

    async def _restore_barrier_snapshot(
        self,
        node_id: str,
        user_key: str,
        snapshot: dict[str, Any],
        existed: bool,
    ) -> None:
        """Restore a pre-begin barrier while the node metadata lock is held."""
        key = self._barrier_key(node_id, user_key)
        for _ in range(32):
            current, rev = await kv_get_json(self._kv, key)
            if current is None:
                if not existed:
                    return
                if await kv_cas_json(self._kv, key, snapshot, 0):
                    return
                continue
            if not existed:
                await self._kv.delete(key, last=rev)
                return
            if await kv_cas_json(self._kv, key, snapshot, rev):
                return
        raise RuntimeError(f"failed to restore user revocation key={user_key} after CAS retries")

    async def _reopen_revocation_owner(self, node_id: str, user_key: str, revocation_id: str) -> None:
        """Allow the owner to perform an authoritative write after a failed close."""
        key = self._barrier_key(node_id, user_key)
        for _ in range(32):
            doc, rev = await self._get_barrier(node_id, user_key)
            if doc.get("permanent") or doc.get("active_owner") != revocation_id:
                return
            if not doc.get("closing"):
                return
            doc["closing"] = False
            if await kv_cas_json(self._kv, key, doc, rev):
                return
        raise RuntimeError(f"failed to reopen user revocation key={user_key} after CAS retries")

    async def _reopen_revocation_owners(self, node_id: str, user_keys: list[str], revocation_id: str) -> None:
        await asyncio.gather(
            *(self._reopen_revocation_owner(node_id, user_key, revocation_id) for user_key in user_keys)
        )

    async def _purge_user_work(self, node_id: str, user_keys: set[str]) -> None:
        for prefix in (self._pending_prefix(node_id), self._claimed_prefix(node_id)):
            for key in await kv_list_keys(self._kv, prefix):
                doc, rev = await kv_get_json(self._kv, key)
                if doc is not None and doc.get("email") in user_keys:
                    await self._delete_revision(key, rev)

    async def _drain_execution_leases(self, node_id: str, user_keys: set[str]) -> None:
        prefix = self._execution_prefix(node_id)
        while True:
            now = time.time()
            wait_seconds: float | None = None
            found_active = False
            for key in await kv_list_keys(self._kv, prefix):
                doc, _ = await kv_get_json(self._kv, key)
                if doc is None or not (
                    doc.get("covers_all_users") or user_keys.intersection(doc.get("user_keys") or [])
                ):
                    continue
                expires_at = float(doc.get("expires_at", 0))
                if expires_at <= now:
                    # The remote request may have completed after its permit
                    # expired. Keep both the execution record and the newly
                    # installed fence so an operator/reconnect can reconcile
                    # the ambiguous outcome instead of deleting the DB row.
                    raise UserSyncLeaseLostError("an expired user-sync execution lease has an unknown remote outcome")
                found_active = True
                remaining = expires_at - now
                wait_seconds = remaining if wait_seconds is None else min(wait_seconds, remaining)
            if not found_active:
                return
            await asyncio.sleep(min(0.05, max(0.001, wait_seconds or 0.001)))

    async def begin_user_revocation(
        self, node_id: str, user_keys: list[str], revocation_id: str
    ) -> UserRevocationResult:
        if not revocation_id:
            raise ValueError("revocation_id must not be empty")
        keys = sorted(set(user_keys))
        async with self._revocation_lock(node_id, keys) as assert_metadata_owned:
            # Validate the complete set before changing any generation. A
            # conflicting bulk begin must leave unrelated queued work intact.
            barrier_snapshots = {user_key: await self._get_barrier(node_id, user_key) for user_key in keys}
            barriers = {user_key: snapshot[0] for user_key, snapshot in barrier_snapshots.items()}
            conflicts = tuple(
                user_key
                for user_key, barrier in barriers.items()
                if not barrier.get("permanent")
                and (barrier.get("closing") or barrier.get("active_owner") not in (None, revocation_id))
            )
            if conflicts:
                raise UserRevocationConflictError(conflicts)

            acquired: list[str] = []
            finalized: list[str] = []
            attempted: list[str] = []
            try:
                for user_key in keys:
                    await assert_metadata_owned()
                    if barriers[user_key].get("permanent"):
                        finalized.append(user_key)
                    else:
                        attempted.append(user_key)
                        if await self._set_revocation_owner(node_id, user_key, revocation_id):
                            acquired.append(user_key)
            except BaseException:
                await assert_metadata_owned()

                async def restore_snapshots() -> None:
                    await asyncio.gather(
                        *(
                            self._restore_barrier_snapshot(
                                node_id,
                                user_key,
                                barrier_snapshots[user_key][0],
                                barrier_snapshots[user_key][1] != 0,
                            )
                            for user_key in attempted
                        )
                    )

                restore = asyncio.create_task(restore_snapshots())
                try:
                    await asyncio.shield(restore)
                except asyncio.CancelledError:
                    await restore
                    raise
                raise

            active_keys = set(acquired)
            # Fencing happens before cleanup. Any enqueue/claim racing with
            # cleanup observes the new generation and self-deletes or rejects.
            await self._purge_user_work(node_id, active_keys)
            await assert_metadata_owned()
            await self._drain_execution_leases(node_id, active_keys)
            await assert_metadata_owned()
            return UserRevocationResult(tuple(acquired), tuple(finalized))

    async def abort_user_revocation(self, node_id: str, user_keys: list[str], revocation_id: str) -> None:
        if not revocation_id:
            raise ValueError("revocation_id must not be empty")
        keys = sorted(set(user_keys))
        async with self._revocation_lock(node_id, keys) as assert_metadata_owned:
            affected: list[str] = []
            try:
                for user_key in keys:
                    key = self._barrier_key(node_id, user_key)
                    for _ in range(32):
                        await assert_metadata_owned()
                        doc, rev = await self._get_barrier(node_id, user_key)
                        if doc.get("permanent") or doc.get("active_owner") != revocation_id:
                            break
                        doc["closing"] = True
                        if await kv_cas_json(self._kv, key, doc, rev):
                            affected.append(user_key)
                            break
                    else:
                        raise RuntimeError(f"failed to abort user revocation key={user_key} after CAS retries")
                if not affected:
                    return
                await self._drain_execution_leases(node_id, set(affected))
                await assert_metadata_owned()
            except BaseException:
                await assert_metadata_owned()
                # Include every requested key: the current CAS may have
                # succeeded even if its transport reply was lost.
                reopen = asyncio.create_task(self._reopen_revocation_owners(node_id, keys, revocation_id))
                try:
                    await asyncio.shield(reopen)
                except asyncio.CancelledError:
                    await reopen
                    raise
                raise
            for user_key in affected:
                await assert_metadata_owned()
                await self._clear_revocation_owner(node_id, user_key, revocation_id)

    async def finalize_user_revocation(self, node_id: str, user_keys: list[str], revocation_id: str) -> None:
        if not revocation_id:
            raise ValueError("revocation_id must not be empty")
        keys = sorted(set(user_keys))
        async with self._revocation_lock(node_id, keys) as assert_metadata_owned:
            affected: list[str] = []
            try:
                for user_key in keys:
                    key = self._barrier_key(node_id, user_key)
                    for _ in range(32):
                        await assert_metadata_owned()
                        doc, rev = await self._get_barrier(node_id, user_key)
                        if doc.get("permanent") or doc.get("active_owner") != revocation_id:
                            break
                        doc["closing"] = True
                        if await kv_cas_json(self._kv, key, doc, rev):
                            affected.append(user_key)
                            break
                    else:
                        raise RuntimeError(f"failed to finalize user revocation key={user_key} after CAS retries")
                if not affected:
                    return
                await self._drain_execution_leases(node_id, set(affected))
                await assert_metadata_owned()
            except BaseException:
                await assert_metadata_owned()
                reopen = asyncio.create_task(self._reopen_revocation_owners(node_id, keys, revocation_id))
                try:
                    await asyncio.shield(reopen)
                except asyncio.CancelledError:
                    await reopen
                    raise
                raise
            for user_key in affected:
                key = self._barrier_key(node_id, user_key)
                for _ in range(32):
                    await assert_metadata_owned()
                    doc, rev = await self._get_barrier(node_id, user_key)
                    if doc.get("permanent"):
                        break
                    if doc.get("active_owner") != revocation_id or not doc.get("closing"):
                        raise RuntimeError(f"lost ownership while finalizing user revocation key={user_key}")
                    doc["permanent"] = True
                    doc["active_owner"] = None
                    doc["closing"] = False
                    if await kv_cas_json(self._kv, key, doc, rev):
                        break
                else:
                    raise RuntimeError(f"failed to finalize user revocation key={user_key} after CAS retries")
            await self._purge_user_work(node_id, set(keys))
            await assert_metadata_owned()

    async def acquire_user_sync_lease(
        self,
        node_id: str,
        worker_id: str,
        user_keys: list[str],
        lease_seconds: float,
        expected_generations: dict[str, int] | None = None,
        revocation_id: str | None = None,
    ) -> UserSyncLease:
        # A startup snapshot replaces the complete node user set. Do not admit
        # a per-user write while a live wildcard startup lease is in flight.
        for key in await kv_list_keys(self._kv, self._execution_prefix(node_id)):
            doc, _ = await kv_get_json(self._kv, key)
            if doc is not None and doc.get("covers_all_users") and float(doc.get("expires_at", 0)) > time.time():
                return UserSyncLease(node_id, worker_id, "", (), {}, lease_seconds)

        generations: dict[str, int] = {}
        for user_key in dict.fromkeys(user_keys):
            barrier, _ = await self._get_barrier(node_id, user_key)
            generation = int(barrier.get("generation", 0))
            expected = None if expected_generations is None else expected_generations.get(user_key)
            if self._barrier_allows_lease(barrier, generation, revocation_id) and (
                expected_generations is None or expected == generation
            ):
                generations[user_key] = generation

        if not generations:
            return UserSyncLease(node_id, worker_id, "", (), {}, lease_seconds)

        token = f"{worker_id}:{uuid4()}"
        lease = UserSyncLease(
            node_id=node_id,
            worker_id=worker_id,
            token=token,
            user_keys=tuple(generations),
            generations=generations,
            lease_seconds=lease_seconds,
            revocation_id=revocation_id,
            epoch=await self._next_user_sync_epoch(node_id),
        )
        key = self._execution_key(node_id, token)
        value = {
            "token": token,
            "worker_id": worker_id,
            "user_keys": list(lease.user_keys),
            "generations": generations,
            "revocation_id": revocation_id,
            "covers_all_users": False,
            "epoch": lease.epoch,
            "expires_at": time.time() + lease_seconds,
        }
        self._ensure_value_size(key, value)
        if not await kv_cas_json(self._kv, key, value, 0):
            raise RuntimeError(f"failed to create user sync execution lease key={key}")

        # Close the acquire/begin race: begin either sees this lease and waits,
        # or the post-check sees its fence and discards the lease before use.
        for user_key, generation in generations.items():
            barrier, _ = await self._get_barrier(node_id, user_key)
            if not self._barrier_allows_lease(barrier, generation, revocation_id):
                doc, rev = await kv_get_json(self._kv, key)
                if doc is not None:
                    await self._delete_revision(key, rev)
                return UserSyncLease(node_id, worker_id, "", (), {}, lease_seconds)
        for other_key in await kv_list_keys(self._kv, self._execution_prefix(node_id)):
            if other_key == key:
                continue
            other, _ = await kv_get_json(self._kv, other_key)
            if other is not None and other.get("covers_all_users") and float(other.get("expires_at", 0)) > time.time():
                doc, rev = await kv_get_json(self._kv, key)
                if doc is not None:
                    await self._delete_revision(key, rev)
                return UserSyncLease(node_id, worker_id, "", (), {}, lease_seconds)
        return lease

    async def acquire_startup_user_sync_lease(
        self,
        node_id: str,
        worker_id: str,
        user_keys: list[str],
        lease_seconds: float,
    ) -> StartupUserSyncLease:
        """Take a node-wide replacement permit and drain prior writes."""
        unique_keys = tuple(dict.fromkeys(user_keys))
        while True:
            try:
                async with self._revocation_lock(node_id, list(unique_keys)) as assert_metadata_owned:
                    barriers: dict[str, dict[str, Any]] = {}
                    has_provisional = False
                    for key in await kv_list_keys(self._kv, self._barrier_prefix(node_id)):
                        doc, _ = await kv_get_json(self._kv, key)
                        if doc is None:
                            continue
                        user_key = doc.get("user_key")
                        if isinstance(user_key, str):
                            barriers[user_key] = doc
                        if doc.get("active_owner") is not None or doc.get("closing"):
                            has_provisional = True
                    if has_provisional:
                        pass
                    else:
                        now = time.time()
                        for key in await kv_list_keys(self._kv, self._execution_prefix(node_id)):
                            doc, _ = await kv_get_json(self._kv, key)
                            if doc is not None and float(doc.get("expires_at", 0)) <= now:
                                raise UserSyncLeaseLostError(
                                    "an expired user-sync execution lease has an unknown remote outcome"
                                )

                        generations = {
                            user_key: int(barriers.get(user_key, {}).get("generation", 0)) for user_key in unique_keys
                        }
                        included_keys = tuple(
                            user_key for user_key in unique_keys if not barriers.get(user_key, {}).get("permanent")
                        )
                        token = f"{worker_id}:{uuid4()}"
                        lease = UserSyncLease(
                            node_id=node_id,
                            worker_id=worker_id,
                            token=token,
                            user_keys=unique_keys,
                            generations=generations,
                            lease_seconds=lease_seconds,
                            covers_all_users=True,
                            epoch=await self._next_user_sync_epoch(node_id),
                        )
                        lease_key = self._execution_key(node_id, token)
                        value = {
                            "token": token,
                            "worker_id": worker_id,
                            "user_keys": list(unique_keys),
                            "generations": generations,
                            "revocation_id": None,
                            "covers_all_users": True,
                            "epoch": lease.epoch,
                            "expires_at": now + lease_seconds,
                        }
                        self._ensure_value_size(lease_key, value)
                        await assert_metadata_owned()
                        if not await kv_cas_json(self._kv, lease_key, value, 0):
                            raise RuntimeError(f"failed to create startup execution lease key={lease_key}")
                        break
            except UserRevocationConflictError:
                await asyncio.sleep(0.01)
                continue
            await asyncio.sleep(0.01)

        try:
            while True:
                now = time.time()
                active_prior = False
                for key in await kv_list_keys(self._kv, self._execution_prefix(node_id)):
                    if key == lease_key:
                        continue
                    doc, _ = await kv_get_json(self._kv, key)
                    if doc is None:
                        continue
                    if float(doc.get("expires_at", 0)) <= now:
                        raise UserSyncLeaseLostError(
                            "an expired user-sync execution lease has an unknown remote outcome"
                        )
                    active_prior = True
                if not active_prior:
                    return StartupUserSyncLease(lease=lease, included_user_keys=included_keys)
                if not await self.heartbeat_user_sync_lease(lease):
                    raise UserSyncLeaseLostError("startup execution lease expired while draining prior writes")
                await asyncio.sleep(0.01)
        except BaseException:
            await self.release_user_sync_lease(lease)
            raise

    async def acquire_user_sync_reconciliation_lease(
        self,
        node_id: str,
        worker_id: str,
        user_keys: list[str],
        lease_seconds: float,
    ) -> StartupUserSyncLease:
        """Resolve orphan barriers and take an authoritative snapshot lease.

        ``user_keys`` is the current, row-locked database membership.  Once no
        live transport lease remains, provisional barriers left by a crashed
        delete can be decided safely: present rows are restored/unfenced and
        absent rows are finalized permanently.  The full replacement is then
        protected by a newly allocated monotonic epoch.
        """
        unique_keys = tuple(dict.fromkeys(user_keys))
        membership = self._authoritative_reconciliation_membership.get()
        if membership is None or membership[:2] != (node_id, worker_id):
            raise UserSyncLeaseLostError("authoritative database membership was not supplied for reconciliation")
        authoritative_keys = set(membership[2])
        while True:
            await self._clear_expired_revocation_lock_for_recovery(node_id, membership)
            try:
                async with self._revocation_lock(node_id, list(unique_keys)) as assert_metadata_owned:
                    now = time.time()
                    active_prior = False
                    for key in await kv_list_keys(self._kv, self._execution_prefix(node_id)):
                        doc, rev = await kv_get_json(self._kv, key)
                        if doc is None:
                            continue
                        if float(doc.get("expires_at", 0)) <= now:
                            await self._delete_revision(key, rev)
                        else:
                            active_prior = True
                    if active_prior:
                        await asyncio.sleep(0.01)
                        continue

                    absent_orphans: set[str] = set()
                    for barrier_key in await kv_list_keys(self._kv, self._barrier_prefix(node_id)):
                        for _ in range(32):
                            await assert_metadata_owned()
                            doc, rev = await kv_get_json(self._kv, barrier_key)
                            if doc is None:
                                break
                            user_key = doc.get("user_key")
                            provisional = doc.get("active_owner") is not None or bool(doc.get("closing"))
                            if not provisional or not isinstance(user_key, str):
                                break
                            if user_key in authoritative_keys:
                                doc["active_owner"] = None
                                doc["closing"] = False
                            else:
                                doc["permanent"] = True
                                doc["active_owner"] = None
                                doc["closing"] = False
                                absent_orphans.add(user_key)
                            if await kv_cas_json(self._kv, barrier_key, doc, rev):
                                break
                        else:
                            raise RuntimeError(
                                f"failed to resolve orphan user revocation barrier key={barrier_key}"
                            )
                    if absent_orphans:
                        await self._purge_user_work(node_id, absent_orphans)

                    barriers: dict[str, dict[str, Any]] = {}
                    for key in await kv_list_keys(self._kv, self._barrier_prefix(node_id)):
                        doc, _ = await kv_get_json(self._kv, key)
                        if doc is not None and isinstance(doc.get("user_key"), str):
                            barriers[doc["user_key"]] = doc

                    generations = {
                        user_key: int(barriers.get(user_key, {}).get("generation", 0)) for user_key in unique_keys
                    }
                    included_keys = tuple(
                        user_key for user_key in unique_keys if not barriers.get(user_key, {}).get("permanent")
                    )
                    token = f"{worker_id}:{uuid4()}"
                    lease = UserSyncLease(
                        node_id=node_id,
                        worker_id=worker_id,
                        token=token,
                        user_keys=unique_keys,
                        generations=generations,
                        lease_seconds=lease_seconds,
                        covers_all_users=True,
                        epoch=await self._next_user_sync_epoch(node_id),
                    )
                    lease_key = self._execution_key(node_id, token)
                    value = {
                        "token": token,
                        "worker_id": worker_id,
                        "user_keys": list(unique_keys),
                        "generations": generations,
                        "revocation_id": None,
                        "covers_all_users": True,
                        "epoch": lease.epoch,
                        "expires_at": now + lease_seconds,
                    }
                    self._ensure_value_size(lease_key, value)
                    await assert_metadata_owned()
                    if not await kv_cas_json(self._kv, lease_key, value, 0):
                        raise RuntimeError(f"failed to create reconciliation execution lease key={lease_key}")
                    return StartupUserSyncLease(lease=lease, included_user_keys=included_keys)
            except UserRevocationConflictError:
                await asyncio.sleep(0.01)
                continue
            await asyncio.sleep(0.01)

    async def retain_user_sync_lease_keys(self, lease: UserSyncLease, retained_user_keys: list[str]) -> UserSyncLease:
        retained = tuple(dict.fromkeys(retained_user_keys))
        if lease.covers_all_users:
            raise ValueError("a node-wide startup lease cannot be narrowed")
        if not retained or not set(retained).issubset(lease.user_keys):
            raise ValueError("retained_user_keys must be a non-empty subset of the lease")
        key = self._execution_key(lease.node_id, lease.token)
        for _ in range(32):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None or not self._lease_matches(doc, lease):
                raise UserSyncLeaseLostError("user-sync execution lease is no longer owned")
            narrowed = UserSyncLease(
                node_id=lease.node_id,
                worker_id=lease.worker_id,
                token=lease.token,
                user_keys=retained,
                generations={user_key: lease.generations[user_key] for user_key in retained},
                lease_seconds=lease.lease_seconds,
                revocation_id=lease.revocation_id,
                epoch=lease.epoch,
            )
            doc["user_keys"] = list(retained)
            doc["generations"] = narrowed.generations
            if await kv_cas_json(self._kv, key, doc, rev):
                return narrowed
        raise RuntimeError("failed to narrow user-sync execution lease after CAS retries")

    @staticmethod
    def _lease_matches(doc: dict[str, Any], lease: UserSyncLease) -> bool:
        return (
            doc.get("token") == lease.token
            and doc.get("worker_id") == lease.worker_id
            and tuple(doc.get("user_keys") or ()) == lease.user_keys
            and doc.get("generations") == lease.generations
            and doc.get("revocation_id") == lease.revocation_id
            and bool(doc.get("covers_all_users")) == lease.covers_all_users
            and int(doc.get("epoch", 0)) == lease.epoch
        )

    async def heartbeat_user_sync_lease(self, lease: UserSyncLease) -> bool:
        if not lease.token:
            return False
        key = self._execution_key(lease.node_id, lease.token)
        for _ in range(32):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None or not self._lease_matches(doc, lease):
                return False
            if float(doc.get("expires_at", 0)) <= time.time():
                # Keep the record as fail-closed evidence of an unknown remote
                # outcome. Only an explicit release of this exact lease may
                # reconcile it.
                return False
            doc["expires_at"] = time.time() + lease.lease_seconds
            if await kv_cas_json(self._kv, key, doc, rev):
                return True
        logger.warning("User sync lease heartbeat CAS exhausted for node_id=%s", lease.node_id)
        return False

    async def release_user_sync_lease(self, lease: UserSyncLease) -> None:
        if not lease.token:
            return
        key = self._execution_key(lease.node_id, lease.token)
        doc, rev = await kv_get_json(self._kv, key)
        if doc is None or not self._lease_matches(doc, lease):
            return
        await self._delete_revision(key, rev)

    async def needs_authoritative_recovery(self, node_id: str) -> bool:
        """Detect durable orphan evidence that requires a DB-locked reconcile."""
        now = time.time()
        lock_doc, _ = await kv_get_json(self._kv, self._revocation_lock_key(node_id))
        if lock_doc is not None and float(lock_doc.get("expires_at", 0)) <= now:
            return True
        for key in await kv_list_keys(self._kv, self._barrier_prefix(node_id)):
            doc, _ = await kv_get_json(self._kv, key)
            if doc is not None and (doc.get("active_owner") is not None or bool(doc.get("closing"))):
                return True
        for key in await kv_list_keys(self._kv, self._execution_prefix(node_id)):
            doc, _ = await kv_get_json(self._kv, key)
            if doc is not None and float(doc.get("expires_at", 0)) <= now:
                return True
        return False

    async def clear(self, node_id: str) -> None:
        """Flush pending work without erasing revocation fences or poison."""
        for prefix in (
            self._pending_prefix(node_id),
            self._claimed_prefix(node_id),
        ):
            for key in await kv_list_keys(self._kv, prefix):
                doc, rev = await kv_get_json(self._kv, key)
                if doc is not None:
                    await self._delete_revision(key, rev)

    async def purge_node(self, node_id: str) -> None:
        """Delete all memory only after the node itself is removed."""
        for prefix in (
            self._pending_prefix(node_id),
            self._claimed_prefix(node_id),
            self._barrier_prefix(node_id),
            self._execution_prefix(node_id),
        ):
            for key in await kv_list_keys(self._kv, prefix):
                doc, rev = await kv_get_json(self._kv, key)
                if doc is not None:
                    await self._delete_revision(key, rev)
        lock_key = self._revocation_lock_key(node_id)
        lock_doc, lock_rev = await kv_get_json(self._kv, lock_key)
        if lock_doc is not None:
            await self._delete_revision(lock_key, lock_rev)
        epoch_key = self._epoch_key(node_id)
        epoch_doc, epoch_rev = await kv_get_json(self._kv, epoch_key)
        if epoch_doc is not None:
            await self._delete_revision(epoch_key, epoch_rev)


class NatsNodeLifecycleCoordinator:
    def __init__(self, kv: CasKv):
        self._kv = kv

    def _key(self, node_id: str) -> str:
        return f"lifecycle.{node_id}"

    async def mark_deleted(self, node_id: str) -> None:
        """Permanently fence a Bridge incarnation before any remote Stop."""
        key = self._key(node_id)
        for _ in range(32):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                doc = _empty_lifecycle_doc()
            if doc.get("deleted") is True:
                return
            doc["deleted"] = True
            doc["deleted_at"] = time.time()
            if await kv_cas_json(self._kv, key, doc, rev):
                return
        raise RuntimeError(f"failed to persist node deletion tombstone node_id={node_id}")

    async def is_deleted(self, node_id: str) -> bool:
        doc, _ = await kv_get_json(self._kv, self._key(node_id))
        return bool(doc and doc.get("deleted") is True)

    async def try_acquire(
        self, node_id: str, worker_id: str, operation: LifecycleOperation, lease_seconds: float
    ) -> LifecycleLease | None:
        key = self._key(node_id)
        for _ in range(32):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                doc = _empty_lifecycle_doc()

            # A deleted incarnation may only be stopped. START remains fenced
            # even when a worker missed the best-effort cleanup broadcast.
            if doc.get("deleted") is True and operation is not LifecycleOperation.STOP:
                return None

            lease_data = doc.get("lease")
            if lease_data is not None:
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
            if float(lease_data.get("expires_at", 0)) <= now:
                return False
            lease_data["expires_at"] = now + lease.lease_seconds
            doc["lease"] = lease_data
            if await kv_cas_json(self._kv, key, doc, rev):
                return True
        logger.warning("Lifecycle heartbeat CAS exhausted for node_id=%s key=%s", lease.node_id, key)
        return False

    async def reconcile(self, node_id: str, observed: LifecycleStatus) -> bool:
        """Clear only an expired unknown lifecycle lease after a state probe."""
        key = self._key(node_id)
        for _ in range(32):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                doc = _empty_lifecycle_doc()
            lease_data = doc.get("lease")
            if lease_data is not None and float(lease_data.get("expires_at", 0)) > now:
                return False
            state = _state_from_dict(doc.get("state"))
            state.epoch += 1
            state.desired = observed
            state.observed = observed
            state.operation = None
            state.owner = None
            state.updated_at = now
            doc["state"] = _state_to_dict(state)
            doc["lease"] = None
            if await kv_cas_json(self._kv, key, doc, rev):
                return True
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
        await store.purge_node(nid)
    if coordinator is not None:
        await coordinator.clear(nid)


async def ensure_bridge_memory() -> tuple[NatsUserSyncStore | None, NatsNodeLifecycleCoordinator | None]:
    """Initialize NATS KV bridge memory for multi-uvicorn workers. Idempotent.

    Split-role / single-worker deployments keep the bridge's in-process defaults.
    """
    global _nc, _user_sync_kv, _lifecycle_kv, _user_sync_store, _lifecycle_coordinator

    if not needs_shared_bridge_memory():
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

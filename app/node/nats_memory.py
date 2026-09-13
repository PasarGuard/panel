"""NATS JetStream KV backends for pasarguard-node-bridge shared memory."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import time
from collections.abc import Awaitable, Callable
from itertools import islice
from typing import Any
from uuid import uuid4

import nats
import nats.js.errors as nats_js_errors
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

from app.nats import needs_shared_bridge_memory
from app.nats.client import create_nats_client, get_jetstream_context, get_or_create_kv_bucket
from app.nats.kv_cas import CasKv, cas_retry_backoff, kv_cas_json, kv_get_json
from app.nats.kv_index import KvKeyIndex
from app.nats.kv_watch import watch_kv
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


RefreshResolver = Callable[[str, list[str]], Awaitable[list[User]]]


class NatsUserSyncStore:
    """One CAS-guarded KV document per (node, user) for the shared delta queue.

    Key ``p.<node>.<digest(email)>`` holds ``{"email", "user"}`` plus an optional
    ``"claim": {"worker", "until"}`` while a worker is delivering it. Every state
    transition is a revision-guarded write:

    - enqueue: latest payload wins and replaces any in-flight claim, so a stale
      delivery can never acknowledge or requeue over a newer state;
    - claim: in-place update adding the claim, exclusive by CAS;
    - ack: delete guarded by the claim revision (fails when a newer payload
      arrived, leaving that payload pending);
    - requeue / expiry: clear the claim by CAS, or let anyone re-claim once the
      lease has expired. An old payload therefore cannot resurrect a newer one
      even after the newer one was delivered and removed.

    A refresh marker ``{"email", "refresh": true}`` asks whichever worker scans
    next to re-derive the user from the source of truth; the resolved payload
    replaces exactly that marker revision, never a newer enqueue.

    A full snapshot never drains the queue destructively: ``capture_queued``
    records the current revisions behind the fence, and ``retire_captured``
    deletes exactly those revisions only after the snapshot was applied.
    """

    def __init__(self, kv: CasKv):
        self._kv = kv
        self._key_index = KvKeyIndex(kv)
        self._write_slots = asyncio.Semaphore(32)
        # key -> (revision, lease expiry) as last read for that revision, so
        # scans skip other workers' in-flight users (and quiescence polls skip
        # unchanged unclaimed entries) without a KV read.
        self._claims_seen: dict[str, tuple[int, float]] = {}
        # Returns current payloads for refresh markers. Installed by the
        # application layer; markers stay queued until it succeeds.
        self.refresh_resolver: RefreshResolver | None = None

    async def close(self) -> None:
        await self._key_index.close()

    async def _run_bounded(self, operation, items) -> None:
        async def run(item):
            async with self._write_slots:
                await operation(item)

        items = iter(items)
        while batch := list(islice(items, 32)):
            # Bound both live tasks and concurrent KV operations during full syncs.
            results = await asyncio.gather(*(run(item) for item in batch), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result

    def _pending_prefix(self, node_id: str) -> str:
        return f"p.{node_id}."

    def _legacy_claimed_prefix(self, node_id: str) -> str:
        return f"c.{node_id}."

    def _fence_key(self, node_id: str) -> str:
        return f"f.{node_id}.sync"

    def _pending_key(self, node_id: str, email: str) -> str:
        return f"{self._pending_prefix(node_id)}{_digest(email)}"

    @staticmethod
    def _b64(text: str) -> str:
        return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")

    @staticmethod
    def _unb64(text: str) -> str:
        try:
            return base64.urlsafe_b64decode(text.encode("ascii")).decode("utf-8")
        except ValueError, UnicodeDecodeError:
            return ""

    @classmethod
    def _token(cls, key: str, revision: int, email: str, claim_id: str) -> str:
        # digest.revision.email(base64url).claim_id: opaque to the bridge, and
        # self-describing for acknowledgements, requeues, and claim releases.
        return f"{key.rpartition('.')[2]}.{revision}.{cls._b64(email)}.{claim_id}"

    def _token_parts(self, node_id: str, token: str) -> tuple[str, int, str, str] | None:
        parts = token.split(".")
        if len(parts) != 4 or not parts[0] or not parts[1].isdigit():
            return None
        digest, revision, email, claim_id = parts
        return f"{self._pending_prefix(node_id)}{digest}", int(revision), self._unb64(email), claim_id

    def _ensure_value_size(self, key: str, value: dict[str, Any]) -> None:
        size = len(json.dumps(value, separators=(",", ":")).encode())
        if size > _MAX_USER_SYNC_VALUE_BYTES:
            raise RuntimeError(
                f"user sync KV value for key={key} is {size} bytes; exceeds limit {_MAX_USER_SYNC_VALUE_BYTES}"
            )

    @staticmethod
    def _encode(value: dict[str, Any]) -> bytes:
        return json.dumps(value, separators=(",", ":")).encode()

    # --- enqueue / restore ---------------------------------------------------

    async def _enqueue_one(self, node_id: str, email: str, user: User) -> None:
        key = self._pending_key(node_id, email)
        value = {"email": email, "user": _b64_user(user)}
        self._ensure_value_size(key, value)
        for attempt in range(32):
            doc, rev = await kv_get_json(self._kv, key)
            # Keep an unexpired claim visible: its owner's RPC may still be in
            # flight and a full snapshot must be able to wait for it. The owner
            # releases the claim when its acknowledgement finds a newer payload.
            claim = (doc or {}).get("claim")
            payload = dict(value)
            if isinstance(claim, dict) and float(claim.get("until", 0)) > time.time():
                payload["claim"] = claim
            try:
                revision = (
                    await self._kv.create(key, self._encode(payload))
                    if rev == 0
                    else await self._kv.update(key, self._encode(payload), last=rev)
                )
            except nats.errors.Error as exc:
                logger.debug("Enqueue CAS attempt failed for key=%s revision=%s: %s", key, rev, exc)
                if attempt < 31:
                    await cas_retry_backoff()
                continue
            self._key_index.observe_put(key, revision)
            self._claims_seen[key] = (revision, float(payload["claim"]["until"]) if "claim" in payload else 0.0)
            return
        raise RuntimeError(f"failed to enqueue NATS KV key={key} after CAS retries")

    async def _release_claim(self, key: str, claim_id: str) -> None:
        """Drop exactly our claim from an entry that changed underneath us, so its newer payload is claimable now.

        Ownership is the claim's unique id, not the worker: the same worker may
        already hold a newer claim on this entry after the old lease expired.
        """
        if not claim_id:
            return
        for attempt in range(8):
            doc, rev = await kv_get_json(self._kv, key)
            claim = (doc or {}).get("claim")
            if not isinstance(claim, dict) or claim.get("id") != claim_id:
                return
            released = {field: value for field, value in doc.items() if field != "claim"}
            try:
                revision = await self._kv.update(key, self._encode(released), last=rev)
            except nats.errors.Error:
                if attempt < 7:
                    await cas_retry_backoff()
                continue
            self._key_index.observe_put(key, revision)
            self._claims_seen[key] = (revision, 0.0)
            return

    async def enqueue_users(self, node_id: str, users: list[User]) -> None:
        if not users:
            return
        # Latest payload per email wins (dedupe across the batch first).
        by_email = {user.email: user for user in users}
        await self._run_bounded(lambda user: self._enqueue_one(node_id, user.email, user), by_email.values())

    async def _create_if_absent(self, key: str, value: dict[str, Any]) -> bool:
        """Create-only write. Only a demonstrated CAS conflict counts as "newer present".

        Transport failures propagate so callers never discard work they failed to write.
        """
        self._ensure_value_size(key, value)
        try:
            revision = await self._kv.create(key, self._encode(value))
        except nats_js_errors.KeyWrongLastSequenceError as exc:
            logger.debug("Create skipped for key=%s (newer payload present): %s", key, exc)
            return False
        self._key_index.observe_put(key, revision)
        return True

    async def _restore_one(self, node_id: str, user: User) -> None:
        await self._create_if_absent(
            self._pending_key(node_id, user.email), {"email": user.email, "user": _b64_user(user)}
        )

    async def _request_refresh_one(self, node_id: str, email: str) -> bool:
        """Mark a user for re-derivation unless a payload (or claim) is already queued for it.

        Create-only: an existing entry is either a newer payload that will be
        delivered anyway or an in-flight claim that must stay visible.
        """
        return await self._create_if_absent(self._pending_key(node_id, email), {"email": email, "refresh": True})

    async def request_refresh(self, node_id: str, emails: list[str]) -> None:
        """Durably ask any worker to re-derive these users before the next delivery.

        The marker holds no payload. A claim scan hands its email to the refresh
        resolver and replaces exactly the marker's revision with the result, so
        a newer API enqueue in the meantime is never overwritten. The marker
        survives until that succeeds.
        """
        if not emails:
            return
        await self._run_bounded(lambda email: self._request_refresh_one(node_id, email), dict.fromkeys(emails))

    async def _migrate_legacy_claims(self, node_id: str) -> None:
        """Settle in-flight claims left by pre-upgrade workers under ``c.<node>.*``.

        An unexpired legacy claim may still be delivering, so it is left alone
        (and counts as active for full-sync quiescence). An expired one is
        replaced by a refresh marker rather than its raw payload: a newer state
        may have been delivered since, and the marker re-derives the current
        one from the source of truth.
        """
        legacy = await self._key_index.entries(self._legacy_claimed_prefix(node_id))
        now = time.time()
        for key, indexed_revision in legacy.items():
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None:
                self._key_index.discard(key, indexed_revision)
                continue
            if float(doc.get("expires_at", 0)) > now:
                continue
            email = doc.get("email")
            if isinstance(email, str):
                # Propagates transport failures: the legacy claim is removed
                # only once its user is known to be queued for re-derivation.
                await self._request_refresh_one(node_id, email)
            try:
                await self._kv.delete(key, last=rev)
                self._key_index.discard(key, indexed_revision)
            except Exception as exc:
                logger.debug("Failed to remove legacy claim key=%s: %s", key, exc)

    # --- claim / ack / requeue -----------------------------------------------

    async def _claim_doc(
        self, key: str, doc: dict[str, Any], revision: int, worker_id: str, lease_seconds: float
    ) -> ClaimedUser | None:
        email, user_b64 = doc["email"], doc["user"]
        until = time.time() + lease_seconds
        claim_id = uuid4().hex
        value = {"email": email, "user": user_b64, "claim": {"id": claim_id, "worker": worker_id, "until": until}}
        self._ensure_value_size(key, value)
        try:
            # Revision-guarded so two workers cannot claim the same payload.
            claimed_revision = await self._kv.update(key, self._encode(value), last=revision)
        except nats_js_errors.KeyWrongLastSequenceError as exc:
            # Only a demonstrated CAS conflict is a lost race. Transport
            # failures propagate: the worker keeps its wake signal and retries
            # with backoff instead of idling out on durable pending work.
            logger.debug("Claim race for pending key=%s: %s", key, exc)
            return None
        self._key_index.observe_put(key, claimed_revision)
        self._claims_seen[key] = (claimed_revision, until)
        return ClaimedUser(token=self._token(key, claimed_revision, email, claim_id), user=_user_from_b64(user_b64))

    async def _resolve_refresh_markers(
        self, node_id: str, markers: dict[str, tuple[str, int]], worker_id: str, lease_seconds: float
    ) -> list[ClaimedUser]:
        """Replace refresh markers with current payloads and claim them for delivery."""
        if not markers:
            return []
        if self.refresh_resolver is None:
            logger.warning("No refresh resolver installed; %s user(s) on node %s stay queued", len(markers), node_id)
            return []
        try:
            payloads = {user.email: user for user in await self.refresh_resolver(node_id, list(markers))}
        except Exception as exc:
            logger.warning("Refresh of %s user(s) for node %s failed; retrying later: %s", len(markers), node_id, exc)
            return []
        claimed: list[ClaimedUser] = []
        for email, (key, revision) in markers.items():
            user = payloads.get(email)
            if user is None:
                # Nothing to send for this user; retire the marker unless it changed.
                try:
                    await self._kv.delete(key, last=revision)
                    self._key_index.discard(key, revision)
                except Exception as exc:
                    logger.debug("Refresh marker key=%s changed before retirement: %s", key, exc)
                continue
            # CAS against the marker revision: a payload enqueued after the
            # marker was read (possibly newer than our database read) wins.
            item = await self._claim_doc(
                key, {"email": email, "user": _b64_user(user)}, revision, worker_id, lease_seconds
            )
            if item is not None:
                claimed.append(item)
        return claimed

    async def resolve_refresh_markers(self, node_id: str) -> tuple[int, int]:
        """Replace every refresh marker for a node with its current payload, without claiming it.

        Returns ``(resolved, remaining)``. Used before rolling back to a panel
        version that does not understand markers, so no queued work is stranded.
        """
        if self.refresh_resolver is None:
            raise RuntimeError("no refresh resolver installed")
        markers: dict[str, tuple[str, int]] = {}
        for key in await self._discover_entries(node_id):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None or not doc.get("refresh") or isinstance(doc.get("user"), str):
                continue
            if isinstance(doc.get("email"), str):
                markers[doc["email"]] = (key, rev)
        if not markers:
            return 0, 0
        payloads = {user.email: user for user in await self.refresh_resolver(node_id, list(markers))}
        resolved = 0
        for email, (key, revision) in markers.items():
            user = payloads.get(email)
            try:
                if user is None:
                    await self._kv.delete(key, last=revision)
                    self._key_index.discard(key, revision)
                else:
                    value = {"email": email, "user": _b64_user(user)}
                    self._ensure_value_size(key, value)
                    new_revision = await self._kv.update(key, self._encode(value), last=revision)
                    self._key_index.observe_put(key, new_revision)
                    self._claims_seen[key] = (new_revision, 0.0)
            except nats.errors.Error as exc:
                logger.debug("Refresh marker key=%s changed during resolution: %s", key, exc)
                continue
            resolved += 1
        remaining = 0
        for key in await self._discover_entries(node_id):
            doc, _ = await kv_get_json(self._kv, key)
            if doc is not None and doc.get("refresh") and not isinstance(doc.get("user"), str):
                remaining += 1
        return resolved, remaining

    async def claim_users(self, node_id: str, worker_id: str, limit: int, lease_seconds: float) -> list[ClaimedUser]:
        if limit <= 0:
            return []
        # Apply the same batch budget as direct user updates. Large shared
        # claims can exceed the node RPC deadline and repeatedly requeue work.
        limit = min(limit, max(1, nats_settings.node_update_users_batch_size))
        await self._migrate_legacy_claims(node_id)

        result: list[ClaimedUser] = []
        markers: dict[str, tuple[str, int]] = {}
        entries = await self._key_index.entries(self._pending_prefix(node_id))
        if len(self._claims_seen) > len(entries) + 256:
            self._claims_seen = {key: seen for key, seen in self._claims_seen.items() if key in entries}
        for pending_key, indexed_revision in entries.items():
            if len(result) + len(markers) >= limit:
                break
            now = time.time()
            seen = self._claims_seen.get(pending_key)
            if seen is not None and seen[0] == indexed_revision and seen[1] > now:
                continue
            doc, rev = await kv_get_json(self._kv, pending_key)
            if doc is None:
                self._key_index.discard(pending_key, indexed_revision)
                self._claims_seen.pop(pending_key, None)
                continue
            claim = doc.get("claim")
            if isinstance(claim, dict) and float(claim.get("until", 0)) > now:
                self._claims_seen[pending_key] = (rev, float(claim["until"]))
                continue
            self._claims_seen[pending_key] = (rev, 0.0)
            email = doc.get("email")
            if not isinstance(email, str):
                continue
            if doc.get("refresh") and not isinstance(doc.get("user"), str):
                markers[email] = (pending_key, rev)
                continue
            if not isinstance(doc.get("user"), str):
                continue
            item = await self._claim_doc(pending_key, doc, rev, worker_id, lease_seconds)
            if item is not None:
                result.append(item)
        result.extend(await self._resolve_refresh_markers(node_id, markers, worker_id, lease_seconds))
        return result

    async def _ack_one(self, node_id: str, token: str, unconfirmed: list[str]) -> None:
        parts = self._token_parts(node_id, token)
        if parts is None:
            return
        key, revision, email, claim_id = parts
        try:
            deleted = await self._kv.delete(key, last=revision)
        except Exception as exc:
            logger.debug("Ack CAS failed for key=%s revision=%s: %s", key, revision, exc)
            deleted = False
        if deleted:
            self._key_index.discard(key, revision)
            self._claims_seen.pop(key, None)
            return
        doc, _ = await kv_get_json(self._kv, key)
        if doc is None:
            if email:
                # The payload we delivered was removed by someone else (a newer
                # delivery or a full sync). Our copy may have landed last, so
                # the caller should re-derive the current state.
                unconfirmed.append(email)
            return
        # A newer payload is pending and will be delivered after ours; make it
        # claimable immediately if it still carries our (preserved) claim.
        await self._release_claim(key, claim_id)

    async def ack_users(self, node_id: str, tokens: list[str]) -> list[str]:
        """Acknowledge delivered claims; returns emails whose latest state could not be confirmed."""
        if not tokens:
            return []
        unconfirmed: list[str] = []
        await self._run_bounded(lambda token: self._ack_one(node_id, token, unconfirmed), tokens)
        return unconfirmed

    async def _requeue_one(self, node_id: str, item: ClaimedUser, failed: list[str]) -> None:
        parts = self._token_parts(node_id, item.token)
        if parts is None:
            return
        key, revision, _, claim_id = parts
        value = {"email": item.user.email, "user": _b64_user(item.user)}
        self._ensure_value_size(key, value)
        try:
            new_revision = await self._kv.update(key, self._encode(value), last=revision)
        except Exception as exc:
            # A newer payload replaced our claim, or the work was drained; the
            # stale copy must not come back. Report it so the caller can repair
            # from the source of truth when needed.
            logger.debug("Requeue skipped for key=%s revision=%s: %s", key, revision, exc)
            failed.append(item.user.email)
            await self._release_claim(key, claim_id)
            return
        self._key_index.observe_put(key, new_revision)
        self._claims_seen[key] = (new_revision, 0.0)

    async def requeue_users(self, node_id: str, claimed_users: list[ClaimedUser]) -> list[str]:
        """Return claimed payloads to the queue; returns emails that could not be requeued."""
        if not claimed_users:
            return []
        failed: list[str] = []
        await self._run_bounded(lambda item: self._requeue_one(node_id, item, failed), claimed_users)
        return failed

    async def _refresh_claimed_one(self, node_id: str, item: ClaimedUser) -> None:
        parts = self._token_parts(node_id, item.token)
        if parts is None:
            return
        key, revision, email, claim_id = parts
        marker = {"email": email or item.user.email, "refresh": True}
        try:
            new_revision = await self._kv.update(key, self._encode(marker), last=revision)
        except nats_js_errors.KeyWrongLastSequenceError:
            # Newer payload present (it wins; release our claim on it) or the
            # entry is gone (recreate the marker).
            if not await self._create_if_absent(key, marker):
                await self._release_claim(key, claim_id)
            return
        self._key_index.observe_put(key, new_revision)
        self._claims_seen[key] = (new_revision, 0.0)

    async def refresh_claimed(self, node_id: str, claimed_users: list[ClaimedUser]) -> None:
        """Turn delivered-but-unconfirmable claims into refresh markers.

        Used when a delivery crossed a full snapshot: replaying the delivered
        payload could regress state the snapshot already carried, so the
        current state is re-derived instead. A newer queued payload always wins.
        """
        if not claimed_users:
            return
        await self._run_bounded(lambda item: self._refresh_claimed_one(node_id, item), claimed_users)

    # --- full-snapshot capture / retire / clear --------------------------------

    async def _discover_entries(self, node_id: str) -> dict[str, int]:
        """Keys and newest known revisions for a node, caught up to the current stream end.

        The live index may lag behind other workers' writes, so the tail after
        its checkpoint is replayed in order (deletes included) before the
        result is trusted. Nothing here relies on cached claim state alone.
        """
        prefixes = (self._pending_prefix(node_id), self._legacy_claimed_prefix(node_id))
        if not isinstance(self._kv, KeyValue):
            entries: dict[str, int] = {}
            for prefix in prefixes:
                entries.update(await self._key_index.entries(prefix))
            return entries
        entries, revision = await self._key_index.snapshot_entries(prefixes)
        watcher = await watch_kv(self._kv, f"*.{node_id}.*", snapshot_only=True, start_revision=revision + 1)
        try:
            async for entry in watcher:
                if entry is None:
                    break
                if not entry.key.startswith(prefixes):
                    continue
                if entry.operation in ("DEL", "PURGE"):
                    entries.pop(entry.key, None)
                else:
                    entries[entry.key] = max(entries.get(entry.key, 0), entry.revision)
        finally:
            await watcher.stop()
        return entries

    async def capture_queued(self, node_id: str) -> tuple[dict[str, int], int]:
        """Record the current revision of every unclaimed queued entry for a node.

        Returns ``(captured, active_claims)``. Nothing is deleted. Entries under
        an unexpired claim are counted, not captured: their owner's delivery is
        in flight and, if it crosses a full snapshot, re-derives the current
        state. Entries whose newest revision was already read are not re-read.
        """
        captured: dict[str, int] = {}
        active = 0
        now = time.time()
        known = await self._discover_entries(node_id)

        async def capture(item: tuple[str, int]) -> None:
            nonlocal active
            key, newest = item
            seen = self._claims_seen.get(key)
            if seen is not None and newest > 0 and seen[0] == newest:
                rev, until = seen
            else:
                doc, rev = await kv_get_json(self._kv, key)
                if doc is None:
                    self._claims_seen.pop(key, None)
                    return
                claim = doc.get("claim")
                until = float(claim.get("until", 0)) if isinstance(claim, dict) else 0.0
                # Pre-upgrade claims keep their own lease field.
                until = max(until, float(doc.get("expires_at", 0) or 0))
                self._claims_seen[key] = (rev, until)
            if until > now:
                active += 1
                return
            captured[key] = rev

        await self._run_bounded(capture, known.items())
        return captured, active

    async def retire_captured(self, node_id: str, captured: dict[str, int]) -> int:
        """Delete exactly the captured revisions; anything newer survives for delivery."""
        retired = 0

        async def retire(item: tuple[str, int]) -> None:
            nonlocal retired
            key, revision = item
            try:
                if not await self._kv.delete(key, last=revision):
                    return
            except Exception as exc:
                logger.debug("Captured entry key=%s changed before retirement: %s", key, exc)
                return
            retired += 1
            self._key_index.discard(key, revision)
            self._claims_seen.pop(key, None)

        await self._run_bounded(retire, captured.items())
        return retired

    async def _clear_one(self, key: str) -> None:
        doc, rev = await kv_get_json(self._kv, key)
        if doc is None:
            return
        try:
            await self._kv.delete(key, last=rev)
        except Exception as exc:
            logger.debug("Failed to clear key=%s: %s", key, exc)
            return
        self._claims_seen.pop(key, None)

    async def clear(self, node_id: str) -> None:
        """Drop all queued work for a node (node removal / explicit bridge flush)."""
        await self._run_bounded(self._clear_one, list(await self._discover_entries(node_id)))

    # --- full-sync fence -------------------------------------------------
    #
    # A full snapshot is only coherent if no delta enqueued after the snapshot
    # was read lands on the node before the snapshot does. The fence is a
    # leased marker with a generation that survives release: workers refuse to
    # claim while it is active, and a delivery whose claim observed an older
    # generation is requeued instead of acknowledged, so it is re-applied on
    # top of the snapshot.

    async def begin_full_sync(self, node_id: str, worker_id: str, lease_seconds: float) -> str | None:
        key = self._fence_key(node_id)
        for attempt in range(8):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            if doc is not None and float(doc.get("until", 0)) > now:
                return None
            token = f"{worker_id}:{uuid4()}"
            generation = int((doc or {}).get("generation", 0)) + 1
            value = {
                "generation": generation,
                "token": token,
                "worker": worker_id,
                "started_at": now,
                "until": now + lease_seconds,
            }
            if await kv_cas_json(self._kv, key, value, rev):
                return token
            if attempt < 7:
                await cas_retry_backoff()
        return None

    async def end_full_sync(self, node_id: str, token: str) -> None:
        key = self._fence_key(node_id)
        for attempt in range(8):
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None or doc.get("token") != token:
                return
            doc["until"] = 0
            doc["token"] = None
            if await kv_cas_json(self._kv, key, doc, rev):
                return
            if attempt < 7:
                await cas_retry_backoff()
        logger.warning("Full-sync fence release CAS exhausted for node_id=%s", node_id)

    async def renew_full_sync(self, node_id: str, token: str, lease_seconds: float) -> bool:
        key = self._fence_key(node_id)
        for attempt in range(8):
            now = time.time()
            doc, rev = await kv_get_json(self._kv, key)
            if doc is None or doc.get("token") != token:
                return False
            if float(doc.get("until", 0)) <= now:
                # Expired: siblings may already deliver again. Never resurrect it.
                return False
            doc["until"] = now + lease_seconds
            if await kv_cas_json(self._kv, key, doc, rev):
                return True
            if attempt < 7:
                await cas_retry_backoff()
        return False

    async def fence_state(self, node_id: str) -> tuple[bool, int]:
        """(active, generation) for the node's full-sync fence."""
        doc, _ = await kv_get_json(self._kv, self._fence_key(node_id))
        if doc is None:
            return False, 0
        return float(doc.get("until", 0)) > time.time(), int(doc.get("generation", 0))

    async def full_sync_active(self, node_id: str) -> bool:
        active, _ = await self.fence_state(node_id)
        return active

    async def clear_full_sync(self, node_id: str) -> None:
        key = self._fence_key(node_id)
        doc, rev = await kv_get_json(self._kv, key)
        if doc is None:
            return
        try:
            await self._kv.delete(key, last=rev)
        except Exception as exc:
            logger.debug("Failed to clear full-sync fence key=%s: %s", key, exc)


class NatsNodeLifecycleCoordinator:
    def __init__(self, kv: CasKv):
        self._kv = kv

    def _key(self, node_id: str) -> str:
        return f"lifecycle.{node_id}"

    async def try_acquire(
        self, node_id: str, worker_id: str, operation: LifecycleOperation, lease_seconds: float
    ) -> LifecycleLease | None:
        key = self._key(node_id)
        for attempt in range(32):
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
            if attempt < 31:
                await cas_retry_backoff()
        return None

    async def release(self, lease: LifecycleLease, state_update: NodeLifecycleState | None = None) -> None:
        key = self._key(lease.node_id)
        for attempt in range(32):
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
            if attempt < 31:
                await cas_retry_backoff()
        logger.warning("Lifecycle release CAS exhausted for node_id=%s key=%s", lease.node_id, key)

    async def heartbeat(self, lease: LifecycleLease) -> bool:
        key = self._key(lease.node_id)
        for attempt in range(32):
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
            if attempt < 31:
                await cas_retry_backoff()
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
        for attempt in range(32):
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
            if attempt < 31:
                await cas_retry_backoff()
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
        await store.clear_full_sync(nid)
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
    if _user_sync_store is not None:
        await _user_sync_store.close()
    if _nc is not None:
        await _nc.close()
    _nc = None
    _user_sync_kv = None
    _lifecycle_kv = None
    _user_sync_store = None
    _lifecycle_coordinator = None

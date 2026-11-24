"""Application-side node adapters for the shared user-sync queue.

The bridge package owns transport and the lazy per-node sync worker. These
subclasses keep that worker but change what the panel depends on:

* delivery uses the node's delta endpoint (no core restart) for bounded batches;
* a wake signal is never lost: it is consumed before the queue is read, a full
  batch keeps draining, and a wake that races the worker's idle exit restarts it;
* queued work survives detach/reconnect instead of being cleared;
* a full snapshot is fenced: workers stop claiming while it is captured and
  applied, and a delivery whose claim predates the fence is requeued rather
  than acknowledged, so an older snapshot can never bury a newer delta;
* a large update is queued as bulk entries (one per delivery batch) instead of
  one entry per user, and the worker delivers each one under the same fence.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar

from PasarGuardNodeBridge import Health, NodeAPIError, NodeType, PasarGuardNode
from PasarGuardNodeBridge.common.service_pb2 import User
from PasarGuardNodeBridge.grpclib import Node as GrpcNode
from PasarGuardNodeBridge.rest import Node as RestNode
from PasarGuardNodeBridge.storage import ClaimedUser, LifecycleLease, LifecycleStatus

from config import nats_settings

_queued_sync: ContextVar[bool] = ContextVar("queued_node_user_sync", default=False)

# Lease for one full snapshot (queue drain + database read + node RPC). It is
# renewed while the snapshot is in progress; a crashed holder's fence expires
# after this and deltas resume on their own.
FULL_SYNC_LEASE_SECONDS = 120.0
# Safety margin between the delivery budget and the claim lease itself.
DELIVERY_DEADLINE_MARGIN = 1.0
# Longest a worker round keeps delivering bulk entries before it claims per-user work.
BULK_ROUND_SECONDS = 5.0
# After a failed bulk delivery, bulk entries wait this long (doubling up to the maximum) before the
# next attempt; per-user work keeps flowing meanwhile.
BULK_RETRY_INITIAL_SECONDS = 1.0
BULK_RETRY_MAX_SECONDS = 30.0

RefreshHandler = Callable[[str, list[str]], Awaitable[list[User]]]
_refresh_handler: RefreshHandler | None = None


def register_refresh_handler(handler: RefreshHandler | None) -> None:
    """Install the callback that re-derives users from the database.

    It returns current payloads for refresh markers left when a delivered
    payload could not be confirmed as the latest state for a user. The store
    replaces exactly the marker revision with the result.
    """
    global _refresh_handler
    _refresh_handler = handler


def get_refresh_handler() -> RefreshHandler | None:
    return _refresh_handler


def _has_wireguard_identity(user: User) -> bool:
    wireguard = user.proxies.wireguard
    return bool(wireguard.public_key and wireguard.peer_ips)


def _keep_removal_credentials(fresh: User, queued: User) -> User:
    """Give a removal the queued payload's credentials where its own cannot identify the user.

    Nodes may need them to find what to remove: node v0.5.4's WireGuard
    backend ignores a removal without a public key and peer IPs. A removal
    without credentials (its user is gone) takes all of them; one whose stored
    WireGuard identity is gone or incomplete takes the queued one. Only the
    credentials are kept; the removal still carries no inbounds.
    """
    if fresh.inbounds or not queued.HasField("proxies"):
        return fresh
    if not fresh.HasField("proxies"):
        return User(email=fresh.email, proxies=queued.proxies)
    if _has_wireguard_identity(fresh) or not _has_wireguard_identity(queued):
        return fresh
    kept = User()
    kept.CopyFrom(fresh)
    kept.proxies.wireguard.CopyFrom(queued.proxies.wireguard)
    return kept


class FullSyncConflictError(NodeAPIError):
    """A full snapshot cannot run (or keep its fence) because of other user-sync work.

    Raised before anything reaches the node, so it says nothing about the
    node's health; callers retry instead of flagging the node.
    """


class FenceHold:
    """Ownership of a node's full-sync fence for the duration of one snapshot."""

    def __init__(self, owner: asyncio.Task | None, until: float) -> None:
        self.lost = asyncio.Event()
        self.owner = owner
        # Wall-clock expiry of the last confirmed lease; independent of whether
        # the renewal task has noticed a problem yet.
        self.until = until

    def check(self) -> None:
        if self.lost.is_set() or time.time() >= self.until:
            raise FullSyncConflictError(409, "The full user sync lost its fence lease; nothing was sent or retired")

    def lose(self) -> None:
        if self.lost.is_set():
            return
        self.lost.set()
        if self.owner is not None and self.owner is not asyncio.current_task():
            self.owner.cancel()


class _QueuedBatchSync:
    async def aclose(self) -> None:
        """Retire local tasks and every transport pool without a remote RPC."""
        try:
            await self.disconnect()
        finally:
            close_channel = getattr(self, "_close_chan", None)
            if close_channel is not None:
                close_channel()
            for name in ("_client", "_json_client"):
                client = getattr(self, name, None)
                # gRPC's _client is a service stub; HTTP clients own sessions.
                close = getattr(client, "close", None)
                if close is not None:
                    await close()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Full snapshots in progress on this process for this node object, and
        # a process-local generation for stores without a shared fence.
        self._local_full_syncs = 0
        self._local_fence_generation = 0
        # Wall-clock deadline of the batch currently being delivered: the claim
        # lease measured from before the claim was taken. Nothing is sent past it.
        self._delivery_deadline = 0.0
        # After a failed bulk delivery: when (loop time) bulk entries may be tried again, and the backoff.
        self._bulk_retry_at: float | None = None
        self._bulk_retry_delay = 0.0
        resolver = getattr(self._user_sync_store, "refresh_resolver", None)
        if resolver is None and hasattr(self._user_sync_store, "refresh_resolver"):
            self._user_sync_store.refresh_resolver = _resolve_refresh

    async def set_reported_versions(self, node_version: str, core_version: str) -> None:
        """Refresh versions from Info without restarting the bridge's sync worker."""
        async with self._version_lock:
            self._node_version = node_version
            self._core_version = core_version

    async def _release_lifecycle_lease(
        self,
        lease: LifecycleLease,
        observed: LifecycleStatus | None = None,
        desired: LifecycleStatus | None = None,
        node_version: str = "",
        core_version: str = "",
    ) -> None:
        # Bridge 0.9.4 awaits the cancelled heartbeat directly. If it has not
        # started, its CancelledError masks the RPC error and aborts startup.
        # Gather consumes the child's cancellation while preserving caller cancellation.
        heartbeat = self._lifecycle_heartbeat_tasks.pop(lease.token, None)
        if heartbeat is not None:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        await super()._release_lifecycle_lease(lease, observed, desired, node_version, core_version)

    # ------------------------------------------------------------------ transport
    def _delivery_budget(self) -> float:
        """Seconds left before the current batch's claim may have expired."""
        margin = min(DELIVERY_DEADLINE_MARGIN, self._sync_lease_seconds / 4)
        return self._delivery_deadline - time.time() - margin

    async def _within_delivery_deadline(self, users: list[User], send):
        """Run a queued delivery only while its claim is certainly still owned.

        The claim lease is what lets a full snapshot know a delivery is in
        flight. Waiting for the node lock, a slow stream, or per-user fallbacks
        could otherwise outlive it, and a late send would land after a
        snapshot that already retired the entry. Past the budget nothing is
        sent; the batch is reported failed so the bridge requeues it (a CAS
        no-op if the entry moved on).
        """
        budget = self._delivery_budget()
        if budget <= 0:
            self.logger.warning(f"[{self.name}] Delivery of {len(users)} user(s) skipped: claim lease is over")
            return list(users)
        try:
            return await asyncio.wait_for(send(), timeout=budget)
        except TimeoutError:
            self.logger.warning(f"[{self.name}] Delivery of {len(users)} user(s) cancelled before its claim expired")
            return list(users)

    async def _current_state(self, users: list[User]) -> list[User]:
        """Replace queued payloads with the state committed now, keeping identity and order.

        Two edits of one user can be queued in the opposite order of their
        commits; the queue only marks the user dirty. Reading the source of
        truth after the claim makes the delivered state the latest one. A
        failed read raises, so the bridge requeues the batch instead of
        acknowledging a possibly stale payload.
        """
        handler = _refresh_handler
        if handler is None:
            return users
        fresh = {user.email: user for user in await handler(self.node_id, [user.email for user in users])}
        return [_keep_removal_credentials(fresh[user.email], user) if user.email in fresh else user for user in users]

    async def sync_users_chunked(self, users, chunk_size=100, flush_pending=False, timeout=None):
        if not _queued_sync.get() or not users:
            return await super().sync_users_chunked(users, chunk_size, flush_pending, timeout)

        async def send():
            # The fresh read counts against the same delivery budget as the send.
            current = await self._current_state(users)
            return await super(_QueuedBatchSync, self).sync_users_chunked(current, chunk_size, flush_pending, timeout)

        return await self._within_delivery_deadline(users, send)

    async def _sync_batch_users(self, users: list[User]) -> list[User]:
        # The bridge normally switches to per-user RPCs below 1000 users.
        # Bounded queue claims still need the efficient delta-batch endpoint.
        # Keep explicit per-user fallbacks outside the background worker intact.
        if not _queued_sync.get() or not users:
            return await super()._sync_batch_users(users)
        supported, _ = await self._supports_chunked_sync()
        if supported:
            return await self.sync_users_chunked(
                users, chunk_size=min(100, len(users)), flush_pending=False, timeout=self._internal_timeout
            )

        async def send():
            current = await self._current_state(users)
            return await super(_QueuedBatchSync, self)._sync_batch_users(current)

        return await self._within_delivery_deadline(users, send)

    # ------------------------------------------------------------ worker lifecycle
    async def _sync_worker(self):
        token = _queued_sync.set(True)
        try:
            while True:
                await super()._sync_worker()
                if self.is_shutting_down() or asyncio.current_task().cancelling():
                    return
                if await self.get_health() in (Health.NOT_CONNECTED, Health.INVALID):
                    return
                # An enqueue during the base worker's idle exit can see its
                # still-running task and skip spawning a replacement.
                if not self._work_available.is_set():
                    return
        finally:
            _queued_sync.reset(token)

    async def _deliver_claimed_users(self, claimed_users: list[ClaimedUser]) -> list[User]:
        # The bridge bounds the entire claim-and-delivery operation by the
        # lease. Keep the adapter's smaller transport budget within it.
        self._delivery_deadline = time.time() + self._sync_lease_seconds
        return await super()._deliver_claimed_users(claimed_users)

    # ------------------------------------------------------------ bulk entries
    async def update_users(self, users: list[User]) -> None:
        """Queue users; an update of many users goes into bulk entries instead of one entry per user.

        One entry per user costs several KV round trips per user and node, so
        a single large update (an admin's users after a limit change) could
        saturate the worker and NATS for every node at once.
        """
        enqueue_bulk = getattr(self._user_sync_store, "enqueue_bulk", None)
        threshold = nats_settings.node_bulk_sync_min_users
        if not callable(enqueue_bulk) or threshold <= 0 or len(users) < threshold:
            await super().update_users(users)
            return
        if self._sync_retries:
            for user in users:
                # A newer change replaces any rejected payload held for retry.
                self._sync_retries.pop(user.email, None)
        await enqueue_bulk(self.node_id, users, batch_size=max(1, nats_settings.node_update_users_batch_size))
        self._work_available.set()
        await self._ensure_sync_worker_running()

    async def _claim_pending_users(self, limit: int | None = None) -> list[ClaimedUser]:
        """Deliver bulk entries first, then claim per-user work as the bridge does."""
        bulk_entries = getattr(self._user_sync_store, "bulk_entries", None)
        if not callable(bulk_entries):
            return await super()._claim_pending_users(limit)
        await self._deliver_bulk_entries()
        claimed = await super()._claim_pending_users(limit)
        # The bridge consumed the wake signal before it read per-user work; bulk
        # entries still queued (or added since) must keep this worker running.
        # While a failed entry backs off, _next_retry_at wakes it at the retry time instead.
        if not await bulk_entries(self.node_id):
            self._bulk_retry_at = None
        elif self._bulk_retry_at is None:
            self._work_available.set()
        return claimed

    def _next_retry_at(self) -> float:
        """Also wake at a failed bulk entry's retry time, so the worker never idles out on queued bulk work."""
        bulk_retry_at = math.inf if self._bulk_retry_at is None else self._bulk_retry_at
        return min(super()._next_retry_at(), bulk_retry_at)

    async def _deliver_bulk_entries(self) -> None:
        """Deliver bulk entries oldest first until per-user work is waiting or the round's bulk budget is spent.

        A failed entry stays queued and is tried again after a backoff. The
        failure does not leave this method, so the per-user claim of the same
        round (a new user, an edit) still runs.
        """
        store = self._user_sync_store
        loop = asyncio.get_running_loop()
        if self._bulk_retry_at is not None and loop.time() < self._bulk_retry_at:
            return
        stop_at = loop.time() + min(BULK_ROUND_SECONDS, self._sync_lease_seconds / 4)
        while entries := await store.bulk_entries(self.node_id):
            key, indexed_revision = entries[0]
            try:
                await self._deliver_bulk_entry(key, indexed_revision)
            except FullSyncConflictError as exc:
                # Another snapshot or bulk delivery holds this node's fence; nothing was retired.
                self.logger.debug(f"[{self.name}] Bulk user delivery deferred: {exc.detail}")
                return
            except Exception as exc:
                self._bulk_retry_delay = min(
                    max(BULK_RETRY_INITIAL_SECONDS, 2 * self._bulk_retry_delay), BULK_RETRY_MAX_SECONDS
                )
                self._bulk_retry_at = loop.time() + self._bulk_retry_delay
                self.logger.warning(
                    f"[{self.name}] Bulk user delivery failed; retrying in {self._bulk_retry_delay:.0f}s: "
                    f"{type(exc).__name__}: {exc!s}"
                )
                await self._increment_user_sync_failure()
                return
            if self._bulk_retry_at is not None:
                # The node takes deltas again: forget the failures, as a delivered per-user batch does.
                await self._reset_user_sync_failure_count()
            self._bulk_retry_delay = 0.0
            self._bulk_retry_at = None
            if loop.time() >= stop_at or await store.has_pending(self.node_id):
                # Let per-user work (a new user, an edit) through between bulk entries.
                return

    async def _deliver_bulk_entry(self, key: str, indexed_revision: int) -> None:
        """Send one bulk entry's users as they are now in the source of truth, then retire the entry.

        The node's full-sync fence keeps every other delivery for this node out
        (on any worker) while the users are read and sent, and a delivery that
        was already in flight when it began is re-derived afterwards, exactly as
        around a full snapshot. Nothing is retired unless the fence is still held.
        """
        store = self._user_sync_store
        async with self.full_sync_fence(self._sync_lease_seconds) as held:
            entry = await store.read_bulk(key, indexed_revision)
            if entry is None:
                return  # retired by a full snapshot, or delivered by another worker
            users, revision = entry
            if users:
                supported, _ = await self._supports_chunked_sync()
                if supported:
                    current = await self._current_state(users)
                    held.check()
                    failed = await super().sync_users_chunked(
                        current,
                        chunk_size=max(1, min(self._sync_chunk_size, len(current))),
                        flush_pending=False,
                        timeout=self._internal_timeout,
                    )
                    if failed and not getattr(failed, "rejected", False):
                        detail = getattr(failed, "detail", "") or "transport error"
                        raise NodeAPIError(-1, f"Bulk delivery of {len(current)} user(s) failed: {detail}")
                    if failed:
                        # The node's backend refused the batch (one user it cannot apply fails all
                        # of it): the per-user path isolates that user and delivers the others.
                        held.check()
                        await store.enqueue_missing(self.node_id, users)
                else:
                    # Nodes without the chunked delta endpoint keep their per-user protocol.
                    held.check()
                    await store.enqueue_missing(self.node_id, users)
            held.check()
            await store.retire_bulk(key, revision)

    async def _cleanup_sync_worker(self):
        # Stop only this process's worker. Queued work is shared with sibling
        # workers and remains valid for whichever attachment comes next; a
        # later Start sends a fresh snapshot, so leftover deltas are harmless.
        async with self._sync_worker_lock:
            task = self._sync_worker_task
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=2.0)
            self._sync_worker_task = None

    async def flush_pending_users(self):
        # Never clear the wake signal here: an update enqueued during the
        # flush must still start a worker.
        await self._user_sync_store.clear(self.node_id)

    async def connect(self, node_version: str, core_version: str, tasks: list | None = None):
        await super().connect(node_version, core_version, tasks)
        # Work may have queued while this object was detached (or was left by
        # a sibling). An empty poll is index-only and lets the worker idle out.
        await self.wake_sync_worker()

    async def wake_sync_worker(self) -> None:
        self._work_available.set()
        await self._ensure_sync_worker_running()

    # ------------------------------------------------------------ full-sync fence
    async def _fence_state(self) -> tuple[bool, int]:
        active = self._local_full_syncs > 0
        generation = self._local_fence_generation
        state = getattr(self._user_sync_store, "fence_state", None)
        if callable(state):
            shared_active, shared_generation = await state(self.node_id)
            active = active or shared_active
            generation += shared_generation
        return active, generation

    async def full_sync_in_progress(self) -> bool:
        active, _ = await self._fence_state()
        return active

    async def _renew_full_sync(self, token: str, lease_seconds: float, held: FenceHold) -> None:
        renew = getattr(self._user_sync_store, "renew_full_sync", None)
        interval = max(lease_seconds / 3, 0.05)
        while True:
            await asyncio.sleep(interval)
            attempt_started = time.time()
            try:
                renewed = await renew(self.node_id, token, lease_seconds)
            except Exception as exc:
                self.logger.debug(f"[{self.name}] Full-sync fence renewal failed: {exc!s}")
                renewed = None
            if renewed:
                held.until = attempt_started + lease_seconds
                continue
            if renewed is False or time.time() >= held.until:
                # Ownership is gone (or cannot be proven any more): another
                # worker may already hold the fence, so this snapshot must not
                # be sent or retire anything. Abort the owning operation.
                self.logger.warning(f"[{self.name}] Full-sync fence lease was lost while the snapshot was in progress")
                held.lose()
                return

    @contextlib.asynccontextmanager
    async def full_sync_fence(self, lease_seconds: float | None = None) -> AsyncIterator[FenceHold]:
        """Stop every worker's delta delivery while a full snapshot is read and applied.

        Yields a hold whose ``check()`` raises once the lease has been lost, so
        the caller can refuse to send or retire anything on a fence it no longer
        owns. Raises FullSyncConflictError(409) when another snapshot is already in flight.
        """
        if lease_seconds is None:
            lease_seconds = FULL_SYNC_LEASE_SECONDS
        store = self._user_sync_store
        begin = getattr(store, "begin_full_sync", None)
        token = None
        renewal: asyncio.Task | None = None
        if callable(begin):
            started = time.time()
            token = await begin(self.node_id, self.worker_id, lease_seconds)
            if token is None:
                raise FullSyncConflictError(409, "A full user sync is already in progress for this node")
            held = FenceHold(asyncio.current_task(), started + lease_seconds)
            renewal = asyncio.create_task(self._renew_full_sync(token, lease_seconds, held))
        elif self._local_full_syncs:
            raise FullSyncConflictError(409, "A full user sync is already in progress for this node")
        else:
            held = FenceHold(None, float("inf"))
        self._local_full_syncs += 1
        self._local_fence_generation += 1
        try:
            yield held
        except asyncio.CancelledError:
            if not held.lost.is_set():
                raise
            # Cancelled by our own lease loss: surface it as an error, not as a
            # cancellation of the caller.
            current = asyncio.current_task()
            if current is not None:
                current.uncancel()
            raise FullSyncConflictError(
                409, "The full user sync lost its fence lease; nothing was sent or retired"
            ) from None
        finally:
            self._local_full_syncs -= 1
            if renewal is not None:
                renewal.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await renewal
            if token is not None:
                with contextlib.suppress(Exception):
                    await store.end_full_sync(self.node_id, token)
            # Deltas queued (or requeued) during the fence apply after the snapshot.
            with contextlib.suppress(Exception):
                await self.wake_sync_worker()

    async def capture_queued_work(self, *, quiesce: bool = True) -> dict[str, int] | list[ClaimedUser]:
        """Record the queued work an imminent full snapshot covers, without deleting it.

        With ``quiesce`` the call also waits, bounded by the claim lease, until
        no delivery is in flight for this node on any worker, so nothing sent
        before the snapshot can land after it without a durable record.
        """
        store = self._user_sync_store
        capture = getattr(store, "capture_queued", None)
        if callable(capture):
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._sync_lease_seconds + 5.0
            delay = 0.2
            while True:
                captured, active = await capture(self.node_id)
                if not active or not quiesce:
                    return captured
                if loop.time() >= deadline:
                    # Claim leases expire on their own, so this means the queue
                    # state cannot be trusted right now. Fail closed: nothing is
                    # sent or retired, and the queued work stays where it is.
                    raise FullSyncConflictError(
                        503, f"{active} user delivery claim(s) still in flight after the lease; full sync not started"
                    )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 2.0)
        # The bridge's in-memory store cannot record revisions; hold its
        # entries as claims instead and settle them after the snapshot.
        claimed: list[ClaimedUser] = []
        while batch := await store.claim_users(self.node_id, self.worker_id, limit=1_000_000, lease_seconds=600):
            claimed.extend(batch)
        return claimed

    async def retire_queued_work(self, captured: dict[str, int] | list[ClaimedUser]) -> None:
        """Retire captured work once the snapshot that covers it has been applied."""
        if not captured:
            return
        if isinstance(captured, dict):
            await self._user_sync_store.retire_captured(self.node_id, captured)
        else:
            await self._user_sync_store.ack_users(self.node_id, [item.token for item in captured])

    async def release_queued_work(self, captured: dict[str, int] | list[ClaimedUser]) -> None:
        """Give captured work back after a failed snapshot (nothing to undo for revision captures)."""
        if isinstance(captured, list) and captured:
            await self._user_sync_store.requeue_users(self.node_id, captured)
            await self.wake_sync_worker()

    async def request_refresh(self, users: list[User]) -> None:
        """Ask the queue to re-derive these users from the source of truth before delivery."""
        if not users:
            return
        request = getattr(self._user_sync_store, "request_refresh", None)
        if callable(request):
            await request(self.node_id, [user.email for user in users])
            await self.wake_sync_worker()
        else:
            await self.update_users(users)


async def _resolve_refresh(node_id: str, emails: list[str]) -> list[User]:
    handler = _refresh_handler
    if handler is None:
        raise RuntimeError("no refresh handler registered")
    return await handler(node_id, emails)


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

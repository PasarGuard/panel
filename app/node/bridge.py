"""Application-side node adapters for the shared user-sync queue.

The bridge package owns transport and the lazy per-node sync worker. These
subclasses keep that worker but change what the panel depends on:

* delivery uses the node's delta endpoint (no core restart) for bounded batches;
* a wake signal is never lost: it is consumed before the queue is read, a full
  batch keeps draining, and a wake that races the worker's idle exit restarts it;
* queued work survives detach/reconnect instead of being cleared;
* a full snapshot is fenced: workers stop claiming while it is captured and
  applied, and a delivery whose claim predates the fence is requeued rather
  than acknowledged, so an older snapshot can never bury a newer delta.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar

from PasarGuardNodeBridge import Health, NodeAPIError, NodeType, PasarGuardNode
from PasarGuardNodeBridge.common.service_pb2 import User
from PasarGuardNodeBridge.grpclib import Node as GrpcNode
from PasarGuardNodeBridge.rest import Node as RestNode
from PasarGuardNodeBridge.storage import ClaimedUser

_queued_sync: ContextVar[bool] = ContextVar("queued_node_user_sync", default=False)

# Lease for one full snapshot (queue drain + database read + node RPC). It is
# renewed while the snapshot is in progress; a crashed holder's fence expires
# after this and deltas resume on their own.
FULL_SYNC_LEASE_SECONDS = 120.0
# Safety margin between the delivery budget and the claim lease itself.
DELIVERY_DEADLINE_MARGIN = 1.0

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
            raise NodeAPIError(409, "The full user sync lost its fence lease; nothing was sent or retired")

    def lose(self) -> None:
        if self.lost.is_set():
            return
        self.lost.set()
        if self.owner is not None and self.owner is not asyncio.current_task():
            self.owner.cancel()


class _QueuedBatchSync:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Full snapshots in progress on this process for this node object, and
        # a process-local generation for stores without a shared fence.
        self._local_full_syncs = 0
        self._local_fence_generation = 0
        # Wall-clock deadline of the batch currently being delivered: the claim
        # lease measured from before the claim was taken. Nothing is sent past it.
        self._delivery_deadline = 0.0
        resolver = getattr(self._user_sync_store, "refresh_resolver", None)
        if resolver is None and hasattr(self._user_sync_store, "refresh_resolver"):
            self._user_sync_store.refresh_resolver = _resolve_refresh

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
        return [fresh.get(user.email, user) for user in users]

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
        owns. Raises NodeAPIError(409) when another snapshot is already in flight.
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
                raise NodeAPIError(409, "A full user sync is already in progress for this node")
            held = FenceHold(asyncio.current_task(), started + lease_seconds)
            renewal = asyncio.create_task(self._renew_full_sync(token, lease_seconds, held))
        elif self._local_full_syncs:
            raise NodeAPIError(409, "A full user sync is already in progress for this node")
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
            raise NodeAPIError(409, "The full user sync lost its fence lease; nothing was sent or retired") from None
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
                    raise NodeAPIError(
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

"""Bring the users each node carries back in line with the database, without restarting its core.

A node only has the users it was sent. An update that never arrived (a queue lost on
a panel restart, a Start the node ignored because its core was already running) leaves
it out of step until that user is edited again. This job re-sends, node by node:

* every pass (``JOB_NODE_USER_RECONCILE_INTERVAL``, every 30 minutes by default): every
  active and on-hold user, plus every user whose status or settings changed since the
  node's previous pass (never more than the last 24 hours, and all 24 on the first pass
  after the node was attached or started), so a lost removal of an expired or disabled
  user is repaired too;
* once per ``JOB_NODE_USER_REMOVAL_SWEEP_INTERVAL`` (a day by default): a removal for
  every inactive user and for every id no user has any more (deleted users), up to
  ``MAX_SWEEP_IDS_ABOVE_EXISTING`` ids above the highest existing one; at most
  ``MAX_SWEEP_GAP_IDS`` of those ids per sweep, the next sweep going on from there (from a
  random id once the panel restarted, so restarts cannot keep it from reaching the rest).

Everything goes through the delta endpoint (``SyncUsersChunked``), never the full
snapshot ``SyncUsers``, which restarts the core and drops every client connection. A
node at v0.5.5 or later leaves users whose state did not change untouched. Chunks of
500 users are read fresh from the database under the node's full-sync fence, so queued
updates wait and land after the chunk; the queue is given back, never cleared. The job
never changes a node's status.

The Sync button runs the same pass with a removal sweep at once (``reconcile_node_now``).
"""

import asyncio
import math
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import chain, islice

from PasarGuardNodeBridge import Health, PasarGuardNode
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser
from sqlalchemy import or_, select, text
from sqlalchemy.exc import DBAPIError

from app import on_shutdown, scheduler
from app.core.manager import core_manager
from app.db import GetDB
from app.db.models import Node, NodeStatus, User, UserStatus
from app.models.core import CoreType
from app.nats.leader import is_job_leader
from app.node import UserReconcileError, UserSyncPreemptedError, node_manager
from app.node.bridge import FullSyncConflictError
from app.node.nats_memory import get_bridge_memory
from app.node.sync import refresh_node_users
from app.operation.node import NodeOperation
from app.utils.logger import get_logger
from config import job_settings, runtime_settings

logger = get_logger("node-user-reconcile")

TICK_SECONDS = 30.0
# A just attached or started node is reconciled this long after it came up.
CONNECT_DELAY = 60.0
RECENT_MARGIN = timedelta(minutes=5)
FIRST_PASS_WINDOW = timedelta(hours=24)
# After an attach or Start a node also gets a removal sweep, unless it had one this recently.
SWEEP_AFTER_CONNECT_MIN_AGE = 6 * 3600.0
CHUNK_SIZE = 500
BATCH_SIZE = 100
BATCH_PAUSE = 0.2
# Well below the fence lease (120 s), so a chunk never outlives the fence it holds.
CHUNK_TIMEOUT = 30.0
CHUNK_GAP_MIN = 1.0
CHUNK_GAP_MAX = 5.0
# A manual pass waits between chunks only while updates are queued, and at most this long.
MANUAL_CHUNK_GAP_MAX = 1.5
FAILURE_RETRY = 300.0
MAX_PENDING_DEFERRALS = 3
MIN_NODE_VERSION = "0.5.5"
# The sweep covers ids no user has only up to this far above the highest existing id: an id
# counter pushed far ahead (a bulk import, a sequence reset) must not make it walk millions.
MAX_SWEEP_IDS_ABOVE_EXISTING = 20_000
# A sweep sends removals for at most this many ids no user has (deleted users) and the next
# sweep goes on from there, so a sparse id range costs a bounded pass, not one per missing id.
MAX_SWEEP_GAP_IDS = 20_000
# Passes skipped in a row (fence or lock busy, a Start, a preemption) before a warning, then hourly.
SKIP_WARN_AFTER = 10
SKIP_WARN_EVERY = 3600.0
# A user whose state cannot be read is warned about once a day per node, not on every pass.
MAX_READS_PER_CHUNK = 64
UNREADABLE_WARN_EVERY = 86400.0
# The database itself failed (connection, time limit): reading user by user would only repeat it.
_DATABASE_UNAVAILABLE = (DBAPIError, OSError, TimeoutError)
_ACTIVE_STATUSES = (UserStatus.active, UserStatus.on_hold)


@dataclass
class _NodeState:
    next_due: float  # monotonic time from which a pass may start
    connected_at: float = 0.0  # last attach or Start seen (monotonic)
    after_connect: bool = False  # the next pass is the first since that attach or Start
    sweep_after_connect: bool = False
    # Wall clock from which changes are covered: when the last successful pass started, or,
    # if that pass had to skip users it could not read, the start of the window it covered.
    last_success_at: datetime | None = None
    last_sweep_at: float | None = None
    sweep_gap_from: int | None = None  # the next sweep's removals of ids no user has start here (None: anywhere)
    deferrals: int = 0
    failed: bool = False  # the last pass was interrupted with a warning
    skips: int = 0  # passes skipped in a row since the last one that ran to an end
    skip_warned_at: float | None = None
    version_warned_for: PasarGuardNode | None = None
    unreadable_warned_at: dict[str, float] = field(default_factory=dict)  # per user (monotonic)


class _PassStopped(Exception):
    """The pass stopped between chunks; it starts over at a later tick."""


class UserSyncIncompleteError(RuntimeError):
    """A manual pass sent the users, but the node rejected some of them or some could not be read."""

    def __init__(self, node_id: int, rejected: int, unreadable: int):
        self.rejected = rejected
        self.unreadable = unreadable
        parts = []
        if rejected:
            parts.append(f"node {node_id} rejected {rejected} user(s)")
        if unreadable:
            parts.append(f"{unreadable} user(s) could not be read")
        super().__init__(
            f"{' and '.join(parts).capitalize()}; the other users were sent. Retry, or run a full sync "
            "(full=true), which restarts the node's core and drops its connections"
        )


_states: dict[int, _NodeState] = {}
_running: dict[int, asyncio.Task] = {}
# Nodes with a manual pass (the Sync button) in progress on this process.
_manual: set[int] = set()
_sweep_node: int | None = None
_last_regular_start = -math.inf
_last_sweep_start = -math.inf
# Highest user id seen; covers a deleted last user where the id counter cannot be read.
_highest_user_id_seen = 0
_stopping = False


def _may_run() -> bool:
    return runtime_settings.role.runs_node and is_job_leader() and not _stopping


def _describe(emails: list[str]) -> str:
    shown = ", ".join(emails[:20])
    return f"{shown} (+{len(emails) - 20} more)" if len(emails) > 20 else shown


def _chunks(ids: list[int]) -> list[list[int]]:
    return [ids[start : start + CHUNK_SIZE] for start in range(0, len(ids), CHUNK_SIZE)]


def _note_skip(node_id: int, state: _NodeState, reason: str) -> None:
    state.skips += 1
    now = time.monotonic()
    if state.skips < SKIP_WARN_AFTER:
        return
    if state.skip_warned_at is not None and now - state.skip_warned_at < SKIP_WARN_EVERY:
        return
    state.skip_warned_at = now
    logger.warning(
        "User reconciliation of node %s was skipped %d times in a row; last reason: %s", node_id, state.skips, reason
    )


def _note_connected(node_id: int, at: float) -> None:
    state = _states.setdefault(node_id, _NodeState(next_due=at + CONNECT_DELAY))
    state.next_due = at + CONNECT_DELAY
    state.connected_at = at
    state.after_connect = state.sweep_after_connect = True
    state.deferrals = 0
    state.version_warned_for = None


# ---------------------------------------------------------------- database reads
async def _db_nodes(node_ids: list[int]) -> dict[int, tuple[NodeStatus, int | None]]:
    async with GetDB() as db:
        stmt = select(Node.id, Node.status, Node.core_config_id).where(Node.id.in_(node_ids))
        return {row.id: (row.status, row.core_config_id) for row in (await db.execute(stmt)).all()}


async def _is_mtproto(core_config_id: int | None) -> bool:
    core = await core_manager.get_core(core_config_id or 1)
    return getattr(core, "type", None) == CoreType.mtproto


async def _ids_to_reconcile(since: datetime) -> list[int]:
    """Users a node must carry (as for delivery: active or on hold), plus every user changed since ``since``."""
    global _highest_user_id_seen
    stmt = (
        select(User.id)
        .where(or_(User.status.in_(_ACTIVE_STATUSES), User.last_status_change >= since, User.edit_at >= since))
        .order_by(User.id)
    )
    async with GetDB() as db:
        ids = list((await db.execute(stmt)).scalars().all())
    if ids:
        _highest_user_id_seen = max(_highest_user_id_seen, ids[-1])
    return ids


async def _last_issued_user_id() -> int | None:
    """The id counter of the users table, so a deleted user with the highest id is still covered."""
    table = User.__tablename__
    try:
        async with GetDB() as db:
            dialect = db.bind.dialect.name
            if dialect == "postgresql":
                stmt = text("SELECT pg_sequence_last_value(CAST(pg_get_serial_sequence(:table, 'id') AS regclass))")
            elif dialect in ("mysql", "mariadb"):
                stmt = text(
                    "SELECT AUTO_INCREMENT - 1 FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table"
                )
            elif dialect == "sqlite":
                stmt = text("SELECT seq FROM sqlite_sequence WHERE name = :table")
            else:
                return None
            value = (await db.execute(stmt, {"table": table})).scalar()
    except Exception as exc:
        logger.debug("User id counter unavailable, using the highest id seen: %s", exc)
        return None
    return int(value) if value is not None else None


async def _removal_sweep_ids(
    exclude: set[int], node_id: int | None = None, gap_from: int | None = None
) -> tuple[list[int], int, int]:
    """Ids of every inactive user and of ids up to the last one issued that no user has.

    Ids above the highest existing one are covered only up to ``MAX_SWEEP_IDS_ABOVE_EXISTING``.
    Ids no user has are taken from ``gap_from`` on, wrapping around, at most ``MAX_SWEEP_GAP_IDS``
    of them; returns the ids, the ``gap_from`` used and the one of the next sweep. Without a valid ``gap_from``
    (a node state just created, e.g. after a panel restart, or none at all) they start at a random
    id, so sweeps that never get to go on from a previous one still reach every id in time.
    """
    global _highest_user_id_seen
    async with GetDB() as db:
        rows = (await db.execute(select(User.id, User.status))).all()
    counter = await _last_issued_user_id()
    existing = {row.id for row in rows}
    highest_existing = max(existing, default=0)
    upper = max(highest_existing, counter or 0, _highest_user_id_seen)
    _highest_user_id_seen = upper
    if upper > (ceiling := highest_existing + MAX_SWEEP_IDS_ABOVE_EXISTING):
        logger.warning(
            "User removal sweep of node %s stops at id %d: the user id counter is at %s and the highest id "
            "seen is %d, but the highest existing user id is %d; %d id(s) above %d are not swept",
            node_id,
            ceiling,
            counter,
            upper,
            highest_existing,
            upper - ceiling,
            ceiling,
        )
        upper = ceiling
    removals = {row.id for row in rows if row.status not in _ACTIVE_STATUSES}
    if gap_from is None or not 1 <= gap_from <= upper:
        gap_from = random.randint(1, max(upper, 1))
    candidates = chain(range(gap_from, upper + 1), range(1, gap_from))
    gaps = list(islice((user_id for user_id in candidates if user_id not in existing), MAX_SWEEP_GAP_IDS))
    removals.update(gaps)
    next_from = 1
    if len(gaps) == MAX_SWEEP_GAP_IDS:
        next_from = gaps[-1] + 1 if gaps[-1] < upper else 1
        logger.info(
            "User removal sweep of node %s covers %d id(s) no user has from id %d; %d more are left to "
            "the next sweep, which goes on from id %d",
            node_id,
            len(gaps),
            gap_from,
            upper - len(existing) - len(gaps),
            next_from,
        )
    return sorted(removals - exclude), gap_from, next_from


# -------------------------------------------------------------------- node checks
def _connect_in_flight(node_id: int) -> str | None:
    if node_id in NodeOperation._in_flight_connects:
        return "the node is being connected or started"
    return None


async def _read_users(
    node_id: int,
    emails: list[str],
    *,
    skipped: list[str] | None = None,
    warned_at: dict[str, float] | None = None,
) -> list[ProtoUser]:
    """The current state of ``emails``; a user whose state cannot be read is skipped, found by halving.

    The skipped users are added to ``skipped``. Halving stops after ``MAX_READS_PER_CHUNK``
    reads: what is still unread then is skipped too, so a failure that is not one user's
    costs a bounded number of reads, not one per user. The first error is raised instead
    when the database itself fails (a connection error or a time limit, not split at all)
    or when nothing of several users could be read. A skipped user is warned about at most
    once per ``UNREADABLE_WARN_EVERY``, tracked in ``warned_at``.
    """
    unreadable: list[tuple[str, Exception]] = []
    unread: list[str] = []
    reads = 0
    first_error: Exception | None = None

    async def read(part: list[str]) -> list[ProtoUser]:
        nonlocal reads, first_error
        if reads >= MAX_READS_PER_CHUNK:
            unread.extend(part)
            return []
        reads += 1
        try:
            return await refresh_node_users(str(node_id), part)
        except _DATABASE_UNAVAILABLE:
            raise
        except Exception as exc:
            first_error = first_error or exc
            if len(part) == 1:
                unreadable.append((part[0], exc))
                return []
            half = len(part) // 2
            return await read(part[:half]) + await read(part[half:])

    users = await read(emails)
    if first_error is not None and len(unreadable) + len(unread) == len(emails) > 1:
        raise first_error
    if skipped is not None:
        skipped.extend(email for email, _ in unreadable)
        skipped.extend(unread)
    now = time.monotonic()
    if unread:
        key = f"unread:{unread[0]}"
        if warned_at is None or now - warned_at.get(key, -UNREADABLE_WARN_EVERY) >= UNREADABLE_WARN_EVERY:
            if warned_at is not None:
                warned_at[key] = now
            logger.warning(
                "Too many users could not be read for node %s; %d more are skipped in this reconciliation pass: %s",
                node_id,
                len(unread),
                _describe(unread),
            )
    if warned_at is not None:
        for email in [email for email, at in warned_at.items() if now - at >= UNREADABLE_WARN_EVERY]:
            del warned_at[email]
    for email, exc in unreadable:
        if warned_at is not None:
            if email in warned_at:
                continue
            warned_at[email] = now
        logger.warning(
            "User %s could not be read for node %s; it is skipped in this reconciliation pass: %s: %s",
            email,
            node_id,
            type(exc).__name__,
            exc,
        )
    return users


async def _lifecycle_busy(node_id: int, node: PasarGuardNode) -> bool:
    """A Start, Stop or core/node update of the node is in progress."""
    if _connect_in_flight(node_id):
        return True
    _, coordinator, _ = get_bridge_memory()
    try:
        if coordinator is not None:
            # A shared state can outlive a crashed holder; its lease cannot.
            return await coordinator.has_active_lease(str(node_id))
        state = await node.get_lifecycle_state()
    except Exception:
        return False
    return state is not None and state.operation is not None


async def _stop_reason(node_id: int, node: PasarGuardNode, *, leader_only: bool = True) -> str | None:
    if _stopping:
        return "the panel is shutting down"
    if leader_only and not is_job_leader():
        return "this worker is no longer the job leader"
    if await node_manager.get_node(node_id) is not node:
        return "the node connection changed"
    if await node.get_health() is not Health.HEALTHY:
        return "the node is not healthy"
    if await _lifecycle_busy(node_id, node):
        return "a Start or an update of the node is in progress"
    return None


async def _pause_between_chunks(
    node: PasarGuardNode, *, min_gap: float | None = None, max_gap: float | None = None
) -> None:
    """Let deliveries queued behind the last chunk go out before the next one takes the fence."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    min_gap = CHUNK_GAP_MIN if min_gap is None else min_gap
    max_gap = CHUNK_GAP_MAX if max_gap is None else max_gap
    if min_gap > 0:
        await asyncio.sleep(min_gap)
    while loop.time() - started < max_gap and await node.has_queued_users():
        await asyncio.sleep(0.2)


async def _ready(
    node_id: int,
    node: PasarGuardNode,
    db_node: tuple[NodeStatus, int | None] | None,
    state: _NodeState,
    now: float,
    interval: float,
) -> bool:
    if db_node is None:
        return False
    status, core_config_id = db_node
    if status in (NodeStatus.disabled, NodeStatus.limited):
        # Not served at all; enabling it again reconnects it, which plans a pass.
        state.after_connect = state.sweep_after_connect = False
        state.deferrals = 0
        state.next_due = now + interval
        return False
    if await _is_mtproto(core_config_id):
        state.next_due = now + interval
        return False
    if status != NodeStatus.connected or await node.get_health() is not Health.HEALTHY:
        return False  # keeps its plan for when it is healthy again
    version = await node.node_version()
    if not node._is_version_at_least(version, MIN_NODE_VERSION):
        if state.version_warned_for is not node:
            state.version_warned_for = node
            known = node._parse_version(version) is not None
            logger.warning(
                "Node %s runs %s; its users are not reconciled (needs node v%s or later, "
                "where a delta sync leaves unchanged users alone)",
                node_id,
                f"node v{version}" if known else f"an unrecognized node version {version!r}",
                MIN_NODE_VERSION,
            )
        state.next_due = now + interval
        return False
    if await _lifecycle_busy(node_id, node):
        _note_skip(node_id, state, "a Start or an update of the node is in progress")
        return False
    if await node.full_sync_in_progress():
        _note_skip(node_id, state, "a full user sync of the node is in progress")
        return False
    if await node.has_queued_users() and state.deferrals < MAX_PENDING_DEFERRALS:
        state.deferrals += 1
        return False
    state.deferrals = 0
    return True


def _sweep_due(state: _NodeState, now: float, node_count: int) -> bool:
    sweep_interval = job_settings.node_user_removal_sweep_interval
    if sweep_interval <= 0 or _sweep_node is not None:
        return False
    # One node at a time, spread over the interval.
    if now - _last_sweep_start < max(TICK_SECONDS, sweep_interval / max(1, node_count)):
        return False
    age = math.inf if state.last_sweep_at is None else now - state.last_sweep_at
    return age >= sweep_interval or (state.sweep_after_connect and age >= SWEEP_AFTER_CONNECT_MIN_AGE)


# --------------------------------------------------------------------------- pass
async def _reconcile_node(
    node_id: int,
    node: PasarGuardNode,
    since: datetime,
    sweep: bool,
    state: _NodeState | None = None,
    *,
    manual: bool = False,
) -> dict:
    """One pass over the node; a ``manual`` one (the Sync button) runs without pauses on any worker."""
    started = time.monotonic()
    ids = await _ids_to_reconcile(since)
    removals: list[int] = []
    if sweep:
        gap_from = state.sweep_gap_from if state is not None else None
        removals, gap_from, gap_next = await _removal_sweep_ids(set(ids), node_id=node_id, gap_from=gap_from)
        if state is not None:
            # Kept before the first chunk is sent: a sweep that picked a random start and is then
            # interrupted starts over at the same id instead of picking another one.
            state.sweep_gap_from = gap_from
    chunks = _chunks(ids) + _chunks(removals)
    skipped: list[str] = []
    warned_at = state.unreadable_warned_at if state is not None else None

    async def read(emails: list[str]):
        return await _read_users(node_id, emails, skipped=skipped, warned_at=warned_at)

    rejected_total = 0
    for index, chunk in enumerate(chunks):
        if index and manual:
            # No fixed gap, but edits queued meanwhile (a purchase, a renewal) go out first.
            await _pause_between_chunks(node, min_gap=0.0, max_gap=MANUAL_CHUNK_GAP_MAX)
        elif index:
            await _pause_between_chunks(node)
        if reason := await _stop_reason(node_id, node, leader_only=not manual):
            raise _PassStopped(reason)
        rejected = await node_manager.reconcile_user_chunk(
            node_id,
            node,
            [str(user_id) for user_id in chunk],
            read,
            batch_size=BATCH_SIZE,
            pause=0.0 if manual else BATCH_PAUSE,
            timeout=CHUNK_TIMEOUT,
            abort=lambda: _connect_in_flight(node_id),
        )
        for emails, detail in rejected:
            rejected_total += len(emails)
            logger.warning(
                "Node %s rejected a batch of %d user(s) during user reconciliation: %s | Error: %s",
                node_id,
                len(emails),
                _describe(emails),
                detail,
            )
    if sweep and state is not None:
        state.sweep_gap_from = gap_next  # only after every chunk was sent; an interrupted sweep starts over
    took = time.monotonic() - started
    logger.debug(
        "Reconciled users of node %s: active=%d removals=%d chunks=%d rejected=%d unreadable=%d took=%.1fs",
        node_id,
        len(ids),
        len(removals),
        len(chunks),
        rejected_total,
        len(skipped),
        took,
    )
    return {
        "active": len(ids),
        "removals": len(removals),
        "chunks": len(chunks),
        "rejected": rejected_total,
        "unreadable": len(skipped),
    }


async def _run_pass(node_id: int, node: PasarGuardNode, state: _NodeState, sweep: bool) -> None:
    global _sweep_node
    connected_at = state.connected_at
    started_wall = datetime.now(UTC)
    started = time.monotonic()
    since = started_wall - FIRST_PASS_WINDOW
    if not state.after_connect and state.last_success_at is not None:
        # At most a day back: older changes of users that are not active are the sweep's.
        since = max(since, state.last_success_at - RECENT_MARGIN)
    try:
        summary = await node_manager.run_user_reconcile(node_id, _reconcile_node(node_id, node, since, sweep, state))
    except (FullSyncConflictError, UserSyncPreemptedError, _PassStopped) as exc:
        # Nothing wrong with the node: another sync holds it, or it changed. Try again at a later tick.
        logger.debug("User reconciliation of node %s stopped: %s", node_id, exc)
        _note_skip(node_id, state, str(exc))
        return
    except Exception as exc:
        state.skips = 0
        state.failed = True
        state.next_due = time.monotonic() + FAILURE_RETRY
        reason = str(exc) if isinstance(exc, UserReconcileError) else f"{type(exc).__name__}: {exc}"
        logger.warning(
            "User reconciliation of node %s was interrupted, retrying in %d minutes: %s",
            node_id,
            FAILURE_RETRY // 60,
            reason,
        )
        return
    finally:
        if sweep and _sweep_node == node_id:
            _sweep_node = None
    if summary is None:
        return  # a pass of this node was already running
    # A user that could not be read, or that the node rejected, is taken again by the next
    # pass: the window stays where it was instead of moving past the change that was missed.
    missed = summary.get("unreadable") or summary.get("rejected")
    _note_pass_done(node_id, state, since + RECENT_MARGIN if missed else started_wall, started, connected_at, sweep)


def _note_pass_done(
    node_id: int, state: _NodeState, covered_from: datetime, started: float, connected_at: float, sweep: bool
) -> None:
    state.next_due = time.monotonic() + max(TICK_SECONDS, job_settings.node_user_reconcile_interval)
    state.last_success_at = covered_from
    state.skips = 0
    if state.connected_at == connected_at:
        state.after_connect = False
    if sweep:
        state.last_sweep_at = started
        state.sweep_after_connect = False
    if state.failed:
        state.failed = False
        logger.info("Users of node %s are reconciled again after an interrupted pass", node_id)


def _start_pass(node_id: int, node: PasarGuardNode, state: _NodeState, now: float, node_count: int) -> asyncio.Task:
    global _last_regular_start, _last_sweep_start, _sweep_node
    sweep = _sweep_due(state, now, node_count)
    if not state.after_connect:
        _last_regular_start = now
    if sweep:
        _sweep_node = node_id
        _last_sweep_start = now
    task = asyncio.create_task(_run_pass(node_id, node, state, sweep), name=f"node-{node_id}-user-reconcile-pass")
    _running[node_id] = task

    def done(finished: asyncio.Task) -> None:
        if _running.get(node_id) is finished:
            del _running[node_id]

    task.add_done_callback(done)
    return task


async def reconcile_node_users() -> asyncio.Task | None:
    """One tick: start a pass for at most one node whose pass is due; returns its task."""
    interval = job_settings.node_user_reconcile_interval
    if interval <= 0 or not _may_run():
        return None
    now = time.monotonic()
    nodes = dict(await node_manager.get_nodes())
    for node_id, at in node_manager.take_user_reconcile_requests().items():
        if node_id in nodes:
            _note_connected(node_id, at)
    for node_id in [node_id for node_id in _states if node_id not in nodes]:
        del _states[node_id]
    for node_id in nodes:
        if node_id not in _states:
            _note_connected(node_id, now)

    due = sorted(
        (state.next_due, node_id)
        for node_id, state in _states.items()
        if state.next_due <= now and node_id not in _running and not node_manager.user_reconcile_running(node_id)
    )
    if not due:
        return None
    db_nodes = await _db_nodes([node_id for _, node_id in due])
    pace = max(TICK_SECONDS, interval / max(1, len(nodes)))
    for _, node_id in due:
        state = _states[node_id]
        if not state.after_connect and now - _last_regular_start < pace:
            continue
        node = nodes[node_id]
        if await _ready(node_id, node, db_nodes.get(node_id), state, now, interval):
            return _start_pass(node_id, node, state, now, len(nodes))
    return None


# ------------------------------------------------------------------ manual pass
async def can_reconcile_now(node: PasarGuardNode, core_config_id: int | None) -> bool:
    """The node can be brought in line through deltas; otherwise only a full snapshot does it."""
    if not node_manager._supports_shared_sync(node) or await node.get_health() is not Health.HEALTHY:
        return False
    if not node._is_version_at_least(await node.node_version(), MIN_NODE_VERSION):
        return False
    return not await _is_mtproto(core_config_id)


async def reconcile_node_now(node_id: int, node: PasarGuardNode) -> dict:
    """One pass for the Sync button: every active user, the last day's changes and a removal sweep.

    Runs without the background pauses and on any worker; the background pass of the node
    gives way. Raises ``FullSyncConflictError`` (409) when another manual pass of the node
    runs or the pass had to stop, and ``UserSyncIncompleteError`` when the node rejected
    users or some could not be read; the other users are sent either way.
    """
    if node_id in _manual:
        raise FullSyncConflictError(409, f"A user sync of node {node_id} is already in progress")
    _manual.add(node_id)
    try:
        await node_manager.cancel_user_reconcile(node_id)
        state = _states.get(node_id)
        connected_at = state.connected_at if state is not None else 0.0
        started_wall = datetime.now(UTC)
        started = time.monotonic()
        try:
            summary = await node_manager.run_user_reconcile(
                node_id,
                _reconcile_node(node_id, node, started_wall - FIRST_PASS_WINDOW, True, state, manual=True),
            )
        except _PassStopped as exc:
            raise FullSyncConflictError(409, f"User sync of node {node_id} stopped: {exc}; retry") from None
    finally:
        _manual.discard(node_id)
    if summary is None:
        raise FullSyncConflictError(409, f"A user reconciliation of node {node_id} is still running; retry")
    if summary["rejected"] or summary["unreadable"]:
        # The window of the background pass stays where it was, so it takes the missed users again.
        raise UserSyncIncompleteError(node_id, summary["rejected"], summary["unreadable"])
    # Only a node the background job already tracks: a new entry would skip its pass after connect.
    if (state := _states.get(node_id)) is not None:
        _note_pass_done(node_id, state, started_wall, started, connected_at, sweep=True)
    return summary


async def stop_node_user_reconcile() -> None:
    """Cancel running passes; a cancelled chunk lifts its fence and gives the queue back."""
    global _stopping
    _stopping = True
    tasks = [task for task in _running.values() if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await node_manager.stop_lingering_reconcile_chunks()


def register_node_user_reconcile(target_scheduler=scheduler) -> bool:
    """Schedule the job in a process that holds node connections, unless it is turned off."""
    if not runtime_settings.role.runs_node or job_settings.node_user_reconcile_interval <= 0:
        return False
    target_scheduler.add_job(
        reconcile_node_users,
        "interval",
        seconds=TICK_SECONDS,
        coalesce=True,
        max_instances=1,
        id="node_user_reconcile",
        replace_existing=True,
    )
    on_shutdown(stop_node_user_reconcile)
    return True


register_node_user_reconcile()

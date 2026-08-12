"""In-memory per-node online user tracking (2-minute window).

Local dict always updated. When NATS multi-worker sync is enabled, marks are
published on worker_sync so sibling processes keep the same window.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock

from app.nats.message import MessageTopic
from app.nats.router import router
from app.node.nats_memory import WORKER_ID
from app.utils.logger import get_logger

logger = get_logger("node-online-users")

_ONLINE_USERS_WINDOW = timedelta(minutes=2)
_PUBLISH_CHUNK_SIZE = 5_000

# (node_id, user_id) -> last seen (UTC)
_last_seen: dict[tuple[int, int], datetime] = {}
_lock = Lock()


def mark_users_online(entries: list[tuple[int, int]], *, at: datetime | None = None) -> None:
    """Mark users as online on nodes. Each entry is (node_id, user_id)."""
    if not entries:
        return
    now = at or datetime.now(UTC)
    with _lock:
        for node_id, user_id in entries:
            _last_seen[(node_id, user_id)] = now


def get_online_counts(
    node_ids: list[int] | None = None,
    *,
    time_delta: timedelta = _ONLINE_USERS_WINDOW,
) -> dict[int, int]:
    """Count users online per node within the time window. Prunes stale entries."""
    cutoff = datetime.now(UTC) - time_delta
    wanted = set(node_ids) if node_ids is not None else None
    counts: dict[int, int] = {}

    with _lock:
        stale = [key for key, seen_at in _last_seen.items() if seen_at < cutoff]
        for key in stale:
            del _last_seen[key]

        for (node_id, _user_id), seen_at in _last_seen.items():
            if seen_at < cutoff:
                continue
            if wanted is not None and node_id not in wanted:
                continue
            counts[node_id] = counts.get(node_id, 0) + 1

    if wanted is not None:
        for node_id in wanted:
            counts.setdefault(node_id, 0)

    return counts


async def publish_users_online(entries: list[tuple[int, int]], *, at: datetime | None = None) -> None:
    """Broadcast online marks to sibling workers (no-op when NATS router is off)."""
    if not entries:
        return

    seen_at = at or datetime.now(UTC)
    ts = seen_at.timestamp()
    for offset in range(0, len(entries), _PUBLISH_CHUNK_SIZE):
        chunk = entries[offset : offset + _PUBLISH_CHUNK_SIZE]
        try:
            await router.publish(
                MessageTopic.NODE_ONLINE,
                {
                    "origin": WORKER_ID,
                    "at": ts,
                    "entries": [[node_id, user_id] for node_id, user_id in chunk],
                },
            )
        except Exception as exc:
            logger.warning("Failed to publish node online sync: %s", exc)
            return


async def handle_node_online_message(data: dict) -> None:
    if data.get("origin") == WORKER_ID:
        return

    raw_entries = data.get("entries") or []
    if not raw_entries:
        return

    entries: list[tuple[int, int]] = []
    for item in raw_entries:
        try:
            node_id, user_id = item
            entries.append((int(node_id), int(user_id)))
        except (TypeError, ValueError):
            continue

    at = None
    raw_at = data.get("at")
    if raw_at is not None:
        try:
            at = datetime.fromtimestamp(float(raw_at), tz=UTC)
        except (TypeError, ValueError, OSError):
            at = None

    mark_users_online(entries, at=at)


def register_node_online_sync_handler() -> None:
    router.register_handler(MessageTopic.NODE_ONLINE, handle_node_online_message)

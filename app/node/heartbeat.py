"""Keep-alive heartbeat: one cheap request per node, independent of the batch jobs.

pg-node stops its core once no request has succeeded for ``keep_alive`` seconds, and
it never starts it again by itself. The health and usage jobs refresh that timer only
as a side effect, at the pace of their slowest node, and the usage jobs skip nodes the
bridge marks BROKEN, so on a lossy link the timer can run out while the panel is up.
"""

import asyncio
import itertools
import time

from PasarGuardNodeBridge import Health, PasarGuardNode

from app.nats.leader import (
    DEFAULT_LEASE_SECONDS,
    HEARTBEAT_INTERVAL as LEADER_RETRY_SECONDS,
    is_job_leader,
    needs_job_leader,
)
from app.node import NodeManager, node_manager
from app.utils.logger import get_logger

logger = get_logger("node-heartbeat")

MIN_INTERVAL = 5.0
MAX_INTERVAL = 15.0
# Two beats in a row may be lost: the third starts three intervals after the last
# success and may take its whole timeout (one interval) to finish.
SAFE_BEATS = 4
# With several workers only the job leader beats. When it dies, nobody beats until its
# lease runs out and another worker takes it over on its next try.
LEADER_HANDOVER = DEFAULT_LEASE_SECONDS + LEADER_RETRY_SECONDS
_TICK_SECONDS = 1.0


def heartbeat_interval(keep_alive: int) -> float:
    return min(max(keep_alive / 4, MIN_INTERVAL), MAX_INTERVAL)


def _longest_silence(keep_alive: int) -> float:
    interval = heartbeat_interval(keep_alive)
    silence = SAFE_BEATS * interval
    if needs_job_leader():
        # The leader dies just before a beat, and the new leader's first beat may
        # take its whole timeout.
        silence = max(silence, 2 * interval + LEADER_HANDOVER)
    return silence


def keep_alive_too_short(keep_alive: int) -> bool:
    return 0 < keep_alive < _longest_silence(keep_alive)


def shortest_safe_keep_alive() -> int:
    # Ends: the silence stops growing once the interval reaches MAX_INTERVAL.
    return next(value for value in itertools.count(1) if not keep_alive_too_short(value))


class NodeHeartbeat:
    def __init__(self, manager: NodeManager = node_manager):
        self._manager = manager
        self._due: dict[int, float] = {}
        self._beats: dict[int, asyncio.Task] = {}
        self._answers: dict[int, tuple[PasarGuardNode, float]] = {}
        self._loop: asyncio.Task | None = None

    def start(self) -> None:
        if self._loop is None or self._loop.done():
            self._loop = asyncio.create_task(self._run(), name="node_keepalive_heartbeat")

    async def stop(self) -> None:
        tasks = [task for task in (self._loop, *self._beats.values()) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._loop = None
        self._beats.clear()
        self._due.clear()
        self._answers.clear()

    def answered_since(self, node_id: int, node: PasarGuardNode, since: float) -> bool:
        """Whether this connection object got a beat answered after ``since`` (``time.monotonic()``)."""
        answer = self._answers.get(node_id)
        return answer is not None and answer[0] is node and answer[1] > since

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as exc:
                logger.error("Keep-alive heartbeat failed: %s", exc)
            await asyncio.sleep(_TICK_SECONDS)

    async def tick(self) -> None:
        # Any worker's request refreshes the node, and the job leader owns node health.
        if needs_job_leader() and not is_job_leader():
            return

        now = time.monotonic()
        live = set()
        for node_id, node, keep_alive in await self._manager.get_keep_alive_nodes():
            live.add(node_id)
            beat = self._beats.get(node_id)
            if (beat is not None and not beat.done()) or now < self._due.get(node_id, 0.0):
                continue
            interval = heartbeat_interval(keep_alive)
            self._due[node_id] = now + interval
            self._beats[node_id] = asyncio.create_task(self._beat(node_id, node, interval))

        for node_id in self._due.keys() - live:
            self._due.pop(node_id, None)
            self._answers.pop(node_id, None)
            beat = self._beats.pop(node_id, None)
            if beat is not None:
                beat.cancel()

    async def _beat(self, node_id: int, node: PasarGuardNode, interval: float) -> None:
        if await node.get_health() is Health.INVALID:
            return
        try:
            # GetBaseInfo does not touch the core: the cheapest request that succeeds,
            # and so refreshes keep-alive, on pg-node v0.5.4 and later. Its timeout
            # keeps a slow node to one beat in flight.
            await node.info(timeout=interval)
        except Exception as exc:
            logger.debug("[%s] Keep-alive heartbeat failed: %s", node.name, exc)
            return
        # The health check reads this to stop backing off a node it could not reach.
        self._answers[node_id] = (node, time.monotonic())


node_heartbeat = NodeHeartbeat()

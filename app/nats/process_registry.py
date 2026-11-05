"""Live process registry in NATS KV that stops conflicting panel processes.

Every process writes ``process.<instance id>`` with its role and panel version and renews it
like a lease. A process stops itself when another live process already covers its node or
scheduler work (a deprecated ROLE=node/scheduler next to an all-in-one panel), or when it runs
an older panel version than another live process. Two processes polling the same nodes with
reset bill usage twice and fight over the node config, so failing loudly is safer.

Who stops is decided by rule: the deprecated role loses to all-in-one, and the older version
loses to the newer one. Two separate all-in-one containers are only safe when both run
UVICORN_WORKERS>1 (both then join leader election); otherwise the one started later stops.
The winner waits for the loser to go away before its own node and scheduler work starts.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

import nats
from packaging.version import InvalidVersion, Version

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_jetstream_context, get_or_create_kv_bucket
from app.nats.kv_cas import CasKv, kv_get_json, kv_list_keys, kv_put_json
from app.utils.logger import get_logger
from app.version import __version__
from config import nats_settings, runtime_settings, server_settings
from role import Role

logger = get_logger("process-registry")

KEY_PREFIX = "process."
LEASE_SECONDS = 15.0
HEARTBEAT_INTERVAL = 5.0
WAIT_POLL_INTERVAL = 1.0
# A loser exits within one heartbeat; past this the winner stops waiting and starts anyway.
MAX_WAIT_SECONDS = 2 * LEASE_SECONDS

INSTANCE_ID = uuid4().hex
# Set by main.py before uvicorn forks, so every worker of one container shares it:
# "<start time>:<random id>". Processes started another way form a group of their own.
PROCESS_GROUP_ENV = "PASARGUARD_PROCESS_GROUP"


def new_process_group() -> str:
    return f"{time.time():.6f}:{uuid4().hex}"


def _process_group() -> tuple[str, float]:
    group = os.environ.get(PROCESS_GROUP_ENV) or f"{time.time():.6f}:{INSTANCE_ID}"
    try:
        started_at = float(group.split(":", 1)[0])
    except ValueError:
        started_at = time.time()
    return group, started_at


class RoleConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessInfo:
    instance_id: str
    role: str
    version: str
    host: str
    expires_at: float
    group: str = ""
    workers: int = 1
    started_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcessInfo:
        return cls(
            instance_id=str(data.get("instance_id", "")),
            role=str(data.get("role", "")),
            version=str(data.get("version", "")),
            host=str(data.get("host", "")),
            expires_at=float(data.get("expires_at", 0)),
            group=str(data.get("group") or data.get("instance_id", "")),
            workers=int(data.get("workers", 1)),
            started_at=float(data.get("started_at", 0)),
        )


@dataclass(frozen=True)
class Conflict:
    other: ProcessInfo
    reason: str  # "role", "duplicate" or "version"
    self_loses: bool


def _roles_overlap(a: Role, b: Role) -> bool:
    if a == b:
        return False
    return (a.runs_node and b.runs_node) or (a.runs_scheduler and b.runs_scheduler)


def _duplicate_panels(me: ProcessInfo, other: ProcessInfo) -> bool:
    """Two all-in-one containers where at least one skips leader election (one worker)."""
    if me.role != Role.ALL_IN_ONE.value or other.role != Role.ALL_IN_ONE.value or me.group == other.group:
        return False
    return me.workers <= 1 or other.workers <= 1


def _is_older(version: str, other: str) -> bool:
    try:
        return Version(version) < Version(other)
    except InvalidVersion:
        return version < other


def find_conflicts(me: ProcessInfo, others: list[ProcessInfo], now: float) -> list[Conflict]:
    conflicts: list[Conflict] = []
    my_role = Role(me.role)
    for other in others:
        if other.instance_id == me.instance_id or other.expires_at <= now:
            continue
        try:
            other_role = Role(other.role)
        except ValueError:
            other_role = None
        if other_role is not None and _roles_overlap(my_role, other_role):
            conflicts.append(Conflict(other=other, reason="role", self_loses=my_role.is_deprecated))
        if _duplicate_panels(me, other):
            later = (me.started_at, me.group) > (other.started_at, other.group)
            conflicts.append(Conflict(other=other, reason="duplicate", self_loses=later))
        if other.version != me.version:
            conflicts.append(Conflict(other=other, reason="version", self_loses=_is_older(me.version, other.version)))
    return conflicts


def conflict_message(me: ProcessInfo, conflict: Conflict) -> str:
    other = conflict.other
    where = f"ROLE={other.role} on host {other.host}, v{other.version}"
    if conflict.reason == "role":
        deprecated, panel = (me, other) if conflict.self_loses else (other, me)
        work = "node polling" if Role(deprecated.role).runs_node else "scheduler jobs"
        return (
            f"ROLE={deprecated.role} (host {deprecated.host}) overlaps with an all-in-one panel "
            f"(host {panel.host}): both would run {work}, which bills usage twice. "
            f"Set ROLE=backend on the all-in-one panel container to keep the split setup, "
            f"or remove the ROLE={deprecated.role} container."
        )
    if conflict.reason == "duplicate":
        if not conflict.self_loses:
            return f"A second all-in-one panel container (host {other.host}) started and is expected to stop."
        return (
            f"Another all-in-one panel container is already running (host {other.host}). Two panel "
            f"containers poll every node twice unless both run UVICORN_WORKERS>1 with NATS. Run one panel "
            f"container and raise UVICORN_WORKERS for more capacity, or remove this container."
        )
    if conflict.self_loses:
        return (
            f"This process runs PasarGuard v{me.version} but another live process ({where}) runs a newer "
            f"version. Update this container's image so every panel process runs the same version."
        )
    return f"Another live process ({where}) runs an older version and is expected to stop."


class ProcessRegistry:
    def __init__(
        self,
        kv: CasKv,
        *,
        role: str,
        version: str,
        host: str,
        instance_id: str,
        group: str,
        workers: int,
        started_at: float,
        on_lose: Callable[[str], Awaitable[None]],
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._kv = kv
        self._role = role
        self._version = version
        self._host = host
        self._instance_id = instance_id
        self._group = group
        self._workers = workers
        self._started_at = started_at
        self._on_lose = on_lose
        self._clock = clock
        self._sleep = sleep

    @property
    def _key(self) -> str:
        return f"{KEY_PREFIX}{self._instance_id}"

    def _me(self) -> ProcessInfo:
        return ProcessInfo(
            instance_id=self._instance_id,
            role=self._role,
            version=self._version,
            host=self._host,
            expires_at=self._clock() + LEASE_SECONDS,
            group=self._group,
            workers=self._workers,
            started_at=self._started_at,
        )

    async def register(self) -> ProcessInfo:
        me = self._me()
        await kv_put_json(self._kv, self._key, me.to_dict())
        return me

    async def deregister(self) -> None:
        with contextlib.suppress(Exception):
            await self._kv.delete(self._key)

    async def list_live(self) -> list[ProcessInfo]:
        now = self._clock()
        live: list[ProcessInfo] = []
        for key in await kv_list_keys(self._kv, KEY_PREFIX):
            data, _ = await kv_get_json(self._kv, key)
            if not data:
                continue
            info = ProcessInfo.from_dict(data)
            if info.expires_at > now:
                live.append(info)
        return live

    async def _conflicts(self, me: ProcessInfo) -> list[Conflict]:
        return find_conflicts(me, await self.list_live(), self._clock())

    async def _wait_until_gone(self, instance_ids: set[str], timeout: float) -> bool:
        """Keep our entry fresh and poll until none of ``instance_ids`` is live; False on timeout."""
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            await self._sleep(WAIT_POLL_INTERVAL)
            await self.register()
            live = {info.instance_id for info in await self.list_live()}
            if not instance_ids & live:
                return True
        return False

    async def check_startup(self) -> None:
        """Register; raise RoleConflictError if this process must stop, else wait for the losers to leave."""
        me = await self.register()
        conflicts = await self._conflicts(me)
        losing = [c for c in conflicts if c.self_loses]
        # After a crash and quick restart, the "other" panel may be this container's own
        # previous life: its entry stops being renewed and expires within one lease.
        only_duplicates = bool(losing) and all(c.reason == "duplicate" for c in losing)
        if only_duplicates and await self._wait_until_gone(
            {c.other.instance_id for c in losing}, LEASE_SECONDS + HEARTBEAT_INTERVAL
        ):
            me = await self.register()
            conflicts = await self._conflicts(me)
            losing = [c for c in conflicts if c.self_loses]
        if losing:
            await self.deregister()
            raise RoleConflictError(conflict_message(me, losing[0]))
        if not conflicts:
            return

        for conflict in conflicts:
            logger.warning("Waiting before starting jobs: %s", conflict_message(me, conflict))
        if await self._wait_until_gone({c.other.instance_id for c in conflicts}, MAX_WAIT_SECONDS):
            logger.info("Conflicting process stopped; starting jobs")
            return
        logger.warning("Conflicting process did not stop within %ss; starting jobs anyway", int(MAX_WAIT_SECONDS))

    async def heartbeat_once(self) -> bool:
        """Renew the entry; on a lost conflict remove it, call on_lose and return False."""
        me = await self.register()
        losing = [c for c in await self._conflicts(me) if c.self_loses]
        if not losing:
            return True
        await self.deregister()
        await self._on_lose(conflict_message(me, losing[0]))
        return False

    async def run_heartbeat(self) -> None:
        while True:
            await self._sleep(HEARTBEAT_INTERVAL)
            try:
                if not await self.heartbeat_once():
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Process registry heartbeat failed: %s", exc)


_nc: nats.NATS | None = None
_registry: ProcessRegistry | None = None
_heartbeat_task: asyncio.Task | None = None


async def _stop_this_process(message: str) -> None:
    """Runtime loss: pause local jobs at once, then shut down through the normal SIGTERM path."""
    global _heartbeat_task
    logger.error(message)
    if runtime_settings.role.runs_node or runtime_settings.role.runs_scheduler:
        from app.scheduler import scheduler

        if scheduler.running:
            scheduler.pause()
    _heartbeat_task = None
    os.kill(os.getpid(), signal.SIGTERM)


async def start_process_guard() -> None:
    global _nc, _registry, _heartbeat_task
    if not is_nats_enabled():
        return
    try:
        _nc = await create_nats_client()
        if _nc is None:
            return
        js = await get_jetstream_context(_nc)
        kv = await get_or_create_kv_bucket(js, nats_settings.scheduler_leader_kv_bucket)
        if kv is None:
            return
        group, started_at = _process_group()
        registry = ProcessRegistry(
            kv,
            role=runtime_settings.role.value,
            version=__version__,
            host=socket.gethostname(),
            instance_id=INSTANCE_ID,
            group=group,
            workers=server_settings.workers or 1,
            started_at=started_at,
            on_lose=_stop_this_process,
        )
        await registry.check_startup()
    except RoleConflictError as exc:
        logger.error(str(exc))
        await _close_nats()
        raise
    except Exception as exc:
        logger.warning("Process registry unavailable, skipping role/version conflict check: %s", exc)
        await _close_nats()
        return

    _registry = registry
    _heartbeat_task = asyncio.create_task(registry.run_heartbeat())


async def stop_process_guard() -> None:
    global _registry, _heartbeat_task
    task, _heartbeat_task = _heartbeat_task, None
    if task is not None and task is not asyncio.current_task():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if _registry is not None:
        await _registry.deregister()
        _registry = None
    await _close_nats()


async def _close_nats() -> None:
    global _nc
    nc, _nc = _nc, None
    if nc is not None:
        with contextlib.suppress(Exception):
            await nc.close()

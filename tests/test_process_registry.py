import json

import pytest

from app.nats.kv_cas import MemoryCasKv
from app.nats.process_registry import (
    KEY_PREFIX,
    LEASE_SECONDS,
    ProcessInfo,
    ProcessRegistry,
    RoleConflictError,
    find_conflicts,
)

NOW = 1_000.0


def _info(instance_id: str, role: str = "all-in-one", version: str = "5.6.0", expires_at: float = NOW + 10):
    return ProcessInfo(
        instance_id=instance_id, role=role, version=version, host=f"host-{instance_id}", expires_at=expires_at
    )


@pytest.mark.parametrize(
    ("me_role", "other_role", "self_loses"),
    [
        ("node", "all-in-one", True),
        ("all-in-one", "node", False),
        ("scheduler", "all-in-one", True),
        ("all-in-one", "scheduler", False),
    ],
)
def test_overlapping_roles_deprecated_role_loses(me_role, other_role, self_loses):
    conflicts = find_conflicts(_info("me", me_role), [_info("other", other_role)], NOW)
    assert len(conflicts) == 1
    assert conflicts[0].reason == "role"
    assert conflicts[0].self_loses is self_loses


@pytest.mark.parametrize(
    ("me_role", "other_role"),
    [
        ("all-in-one", "all-in-one"),
        ("node", "node"),
        ("backend", "all-in-one"),
        ("backend", "node"),
        ("node", "scheduler"),
    ],
)
def test_non_overlapping_roles_are_fine(me_role, other_role):
    assert find_conflicts(_info("me", me_role), [_info("other", other_role)], NOW) == []


def test_older_version_loses():
    conflicts = find_conflicts(_info("me", version="5.5.0"), [_info("other", version="5.6.0")], NOW)
    assert [(c.reason, c.self_loses) for c in conflicts] == [("version", True)]

    conflicts = find_conflicts(_info("me", version="5.10.0"), [_info("other", version="5.9.1")], NOW)
    assert [(c.reason, c.self_loses) for c in conflicts] == [("version", False)]


def test_unparsable_version_does_not_crash():
    conflicts = find_conflicts(_info("me", version="dev-abc"), [_info("other", version="5.6.0")], NOW)
    assert [c.reason for c in conflicts] == ["version"]


def test_expired_self_and_unknown_role_entries_are_ignored():
    others = [
        _info("me", "node"),
        _info("dead", "all-in-one", expires_at=NOW - 1),
        _info("odd", "something-else"),
    ]
    assert find_conflicts(_info("me", "node"), others, NOW) == []


class FakeTime:
    def __init__(self, kv: MemoryCasKv, on_sleep=None):
        self.now = NOW
        self.kv = kv
        self.on_sleep = on_sleep
        self.sleeps = 0

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps += 1
        self.now += seconds
        if self.on_sleep:
            await self.on_sleep(self)


async def _put(kv: MemoryCasKv, info: ProcessInfo) -> None:
    await kv.create(f"{KEY_PREFIX}{info.instance_id}", json.dumps(info.to_dict()).encode())


def _registry(kv, fake: FakeTime, role: str = "all-in-one", version: str = "5.6.0", on_lose=None):
    async def _default_on_lose(message: str) -> None:
        raise AssertionError(f"unexpected runtime loss: {message}")

    return ProcessRegistry(
        kv,
        role=role,
        version=version,
        host="me-host",
        instance_id="me",
        clock=fake.clock,
        sleep=fake.sleep,
        on_lose=on_lose or _default_on_lose,
    )


@pytest.mark.asyncio
async def test_startup_without_conflicts_registers_and_does_not_wait():
    kv = MemoryCasKv()
    fake = FakeTime(kv)
    await _put(kv, _info("sibling"))
    registry = _registry(kv, fake)

    await registry.check_startup()

    assert fake.sleeps == 0
    assert f"{KEY_PREFIX}me" in await kv.keys()


@pytest.mark.asyncio
async def test_startup_loser_raises_and_removes_its_entry():
    kv = MemoryCasKv()
    fake = FakeTime(kv)
    await _put(kv, _info("panel", "all-in-one"))
    registry = _registry(kv, fake, role="node")

    with pytest.raises(RoleConflictError, match="ROLE=backend"):
        await registry.check_startup()

    assert await kv.keys() == [f"{KEY_PREFIX}panel"]


@pytest.mark.asyncio
async def test_startup_winner_waits_until_loser_entry_is_gone():
    kv = MemoryCasKv()

    async def _loser_leaves_on_second_poll(fake: FakeTime):
        if fake.sleeps == 2:
            await kv.delete(f"{KEY_PREFIX}worker")

    fake = FakeTime(kv, on_sleep=_loser_leaves_on_second_poll)
    await _put(kv, _info("worker", "node", expires_at=NOW + LEASE_SECONDS))
    registry = _registry(kv, fake)

    await registry.check_startup()

    assert fake.sleeps == 2


@pytest.mark.asyncio
async def test_startup_winner_waits_out_old_version_during_rolling_update():
    kv = MemoryCasKv()
    fake = FakeTime(kv)
    await _put(kv, _info("old", "all-in-one", version="5.5.0", expires_at=NOW + 3))
    registry = _registry(kv, fake)

    await registry.check_startup()

    assert NOW + 3 <= fake.now < NOW + 2 * LEASE_SECONDS


@pytest.mark.asyncio
async def test_startup_winner_gives_up_waiting_on_a_stuck_loser():
    kv = MemoryCasKv()

    async def _stuck_loser_keeps_renewing(fake: FakeTime):
        info = _info("worker", "node", expires_at=fake.now + LEASE_SECONDS)
        await kv.update(f"{KEY_PREFIX}worker", json.dumps(info.to_dict()).encode())

    fake = FakeTime(kv, on_sleep=_stuck_loser_keeps_renewing)
    await _put(kv, _info("worker", "node"))
    registry = _registry(kv, fake)

    await registry.check_startup()

    assert fake.now >= NOW + 2 * LEASE_SECONDS


@pytest.mark.asyncio
async def test_heartbeat_loser_at_runtime_removes_entry_and_calls_on_lose():
    kv = MemoryCasKv()
    fake = FakeTime(kv)
    lost: list[str] = []

    async def _on_lose(message: str) -> None:
        lost.append(message)

    registry = _registry(kv, fake, role="node", on_lose=_on_lose)
    await registry.check_startup()
    await _put(kv, _info("panel", "all-in-one"))

    await registry.heartbeat_once()

    assert len(lost) == 1 and "all-in-one" in lost[0]
    assert await kv.keys() == [f"{KEY_PREFIX}panel"]


@pytest.mark.asyncio
async def test_deregister_removes_entry():
    kv = MemoryCasKv()
    fake = FakeTime(kv)
    registry = _registry(kv, fake)
    await registry.check_startup()

    await registry.deregister()

    assert await registry.list_live() == []

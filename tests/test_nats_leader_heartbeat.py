import asyncio
import contextlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.nats import leader


@pytest.fixture(autouse=True)
def _reset_leader_state():
    leader._is_leader = False
    leader._token = "token-a"
    leader._kv = None
    leader._on_leadership_lost = None
    if leader._heartbeat_task is not None and not leader._heartbeat_task.done():
        leader._heartbeat_task.cancel()
    leader._heartbeat_task = None
    yield
    leader._is_leader = False
    leader._token = None
    leader._kv = None
    leader._on_leadership_lost = None
    if leader._heartbeat_task is not None and not leader._heartbeat_task.done():
        leader._heartbeat_task.cancel()
    leader._heartbeat_task = None


@pytest.mark.asyncio
async def test_heartbeat_concedes_immediately_on_token_mismatch():
    lost = AsyncMock()
    leader.set_on_leadership_lost(lost)
    leader._is_leader = True

    kv = MagicMock()
    entry = MagicMock()
    entry.value = json.dumps({"token": "other", "expires_at": 9999999999}).encode()
    entry.revision = 1
    kv.get = AsyncMock(return_value=entry)
    kv.update = AsyncMock()
    leader._kv = kv

    with patch.object(leader, "HEARTBEAT_INTERVAL", 0):
        await leader._heartbeat_loop()

    assert leader.is_job_leader() is False
    lost.assert_awaited_once()
    kv.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_retries_then_concedes_on_renewal_exhaustion():
    lost = AsyncMock()
    leader.set_on_leadership_lost(lost)
    leader._is_leader = True

    kv = MagicMock()
    entry = MagicMock()
    entry.value = json.dumps({"token": "token-a", "expires_at": 9999999999}).encode()
    entry.revision = 1
    kv.get = AsyncMock(return_value=entry)
    kv.update = AsyncMock(side_effect=RuntimeError("nats down"))
    leader._kv = kv

    with (
        patch.object(leader, "HEARTBEAT_INTERVAL", 0),
        patch.object(leader, "HEARTBEAT_RETRY_DELAY", 0),
        patch.object(leader, "HEARTBEAT_MAX_RETRIES", 2),
    ):
        await leader._heartbeat_loop()

    assert leader.is_job_leader() is False
    lost.assert_awaited_once()
    assert kv.update.await_count == 2


@pytest.mark.asyncio
async def test_start_job_leader_restarts_heartbeat_after_done_task():
    async def _noop_loop(*_a, **_k):
        await asyncio.sleep(3600)

    with (
        patch.object(leader, "needs_job_leader", return_value=True),
        patch.object(leader, "try_become_leader", AsyncMock(return_value=True)),
        patch.object(leader, "_heartbeat_loop", _noop_loop),
    ):
        assert await leader.start_job_leader() is True
        first_task = leader._heartbeat_task
        assert first_task is not None and not first_task.done()

        first_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await first_task

        assert await leader.start_job_leader() is True
        assert leader._heartbeat_task is not None
        assert leader._heartbeat_task is not first_task
        assert not leader._heartbeat_task.done()

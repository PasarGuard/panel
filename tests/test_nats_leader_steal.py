import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.nats import leader


@pytest.mark.asyncio
async def test_try_become_leader_falls_through_to_steal_after_generic_create_error():
    kv = MagicMock()
    kv.create = AsyncMock(side_effect=RuntimeError("boom"))
    entry = MagicMock()
    entry.value = json.dumps({"token": "old", "expires_at": 0}).encode()
    entry.revision = 3
    kv.get = AsyncMock(return_value=entry)
    kv.update = AsyncMock(return_value=4)

    with (
        patch.object(leader, "needs_job_leader", return_value=True),
        patch.object(leader, "_ensure_kv", AsyncMock(return_value=kv)),
    ):
        leader._is_leader = False
        leader._token = None
        won = await leader.try_become_leader()

    assert won is True
    assert leader.is_job_leader() is True
    kv.update.assert_awaited()

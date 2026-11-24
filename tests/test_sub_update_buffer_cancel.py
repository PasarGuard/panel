import asyncio
import contextlib

import pytest
from sqlalchemy import func, select

from app.db.models import UserSubscriptionUpdate
from app.subscription import sub_update_buffer
from tests.test_sub_update_buffer import buffer_db  # noqa: F401


@pytest.mark.asyncio
async def test_a_flush_cancelled_mid_write_keeps_every_row_for_the_final_flush(
    buffer_db,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
):
    session, user_id = buffer_db
    for index in range(3):
        await sub_update_buffer.queue_user_sub_update(user_id, f"client/{index}")
    await session.commit()

    real_get_db = sub_update_buffer.GetDB
    writing = asyncio.Event()

    class StuckGetDB(real_get_db):
        async def __aenter__(self):
            db = await super().__aenter__()

            async def stuck_scalars(*args, **kwargs):
                writing.set()
                await asyncio.Event().wait()

            db.scalars = stuck_scalars
            return db

    monkeypatch.setattr(sub_update_buffer, "GetDB", StuckGetDB)
    flush = asyncio.create_task(sub_update_buffer.flush_user_sub_updates())
    await asyncio.wait_for(writing.wait(), timeout=2.0)
    flush.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await flush

    assert sub_update_buffer.pending_count() == 3, "the batch taken for the cancelled write was dropped"

    monkeypatch.setattr(sub_update_buffer, "GetDB", real_get_db)
    assert await sub_update_buffer.flush_user_sub_updates() == 3
    stored = (await session.execute(select(func.count()).select_from(UserSubscriptionUpdate))).scalar()
    assert stored == 3


@pytest.mark.asyncio
async def test_a_size_triggered_flush_is_held_until_it_finishes_and_its_failure_is_consumed(
    buffer_db,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
):
    _session, user_id = buffer_db
    release = asyncio.Event()

    class SlowFailingGetDB:
        async def __aenter__(self):
            await release.wait()
            raise RuntimeError("database gone")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(sub_update_buffer, "GetDB", SlowFailingGetDB)
    for index in range(sub_update_buffer.FLUSH_BATCH_SIZE):
        await sub_update_buffer.queue_user_sub_update(user_id, f"client/{index}")
    await asyncio.sleep(0)

    running = set(sub_update_buffer._background_flushes)
    assert len(running) == 1, "the size-triggered flush task is not held, so nothing retrieves its failure"

    release.set()
    await asyncio.wait(running, timeout=2.0)

    assert sub_update_buffer._background_flushes == set()
    assert sub_update_buffer.pending_count() == sub_update_buffer.FLUSH_BATCH_SIZE


@pytest.mark.asyncio
async def test_a_flush_cancelled_after_its_commit_does_not_write_the_batch_twice(
    buffer_db,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
):
    session, user_id = buffer_db
    for index in range(3):
        await sub_update_buffer.queue_user_sub_update(user_id, f"client/{index}")
    await session.commit()

    real_get_db = sub_update_buffer.GetDB
    closing = asyncio.Event()

    class StuckOnCloseGetDB(real_get_db):
        async def __aexit__(self, *exc):
            result = await super().__aexit__(*exc)
            closing.set()
            await asyncio.Event().wait()
            return result

    monkeypatch.setattr(sub_update_buffer, "GetDB", StuckOnCloseGetDB)
    flush = asyncio.create_task(sub_update_buffer.flush_user_sub_updates())
    await asyncio.wait_for(closing.wait(), timeout=2.0)
    flush.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await flush

    assert sub_update_buffer.pending_count() == 0, "a committed batch was queued again"

    monkeypatch.setattr(sub_update_buffer, "GetDB", real_get_db)
    assert await sub_update_buffer.flush_user_sub_updates() == 0
    stored = (await session.execute(select(func.count()).select_from(UserSubscriptionUpdate))).scalar()
    assert stored == 3

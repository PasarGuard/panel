from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.db.crud.user import (
    get_users_sub_update_list,
    get_users_subscription_agent_counts,
    get_users_subscription_agent_stats,
)
from app.db.models import User, UserSubscriptionUpdate
from app.models.stats import Period
from app.subscription import sub_update_buffer
from tests.api import TestSession, engine
from tests.api.helpers import unique_name


@pytest.mark.asyncio
@pytest.mark.parametrize("reader", ["list", "counts", "stats"])
@pytest.mark.parametrize("already_flushed", [False, True])
async def test_subscription_reads_see_updates_after_request_snapshot(reader, already_flushed):
    async with TestSession() as setup:
        user = User(username=unique_name("sub_snapshot"))
        setup.add(user)
        await setup.commit()
        user_id = user.id

    try:
        async with TestSession() as request:
            if engine.dialect.name in {"mysql", "mariadb", "postgresql"}:
                await request.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            # Authorization/user lookup establishes the request's read snapshot.
            db_user = await request.scalar(select(User).where(User.id == user_id))
            db_user.note = "uncommitted caller change"
            await sub_update_buffer.queue_user_sub_update(user_id, "snapshot-client")
            if already_flushed:
                await sub_update_buffer.flush_user_sub_updates()

            start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
            end = start + timedelta(hours=3)
            if reader == "list":
                rows, count = await get_users_sub_update_list(request, user_id)
                assert count == 1
                assert [row.user_agent for row in rows] == ["snapshot-client"]
            elif reader == "counts":
                counts = await get_users_subscription_agent_counts(request, user_id=user_id, start=start, end=end)
                assert counts == [("snapshot-client", 1)]
            else:
                stats = await get_users_subscription_agent_stats(request, start, end, Period.hour, user_id=user_id)
                assert [(row["agent"], row["count"]) for row in stats] == [("snapshot-client", 1)]

            assert request.in_transaction()
            assert db_user in request.dirty
            assert db_user.note == "uncommitted caller change"

        async with TestSession() as check:
            assert await check.scalar(select(User.note).where(User.id == user_id)) is None
    finally:
        await sub_update_buffer.flush_user_sub_updates()
        async with TestSession() as cleanup:
            # The API SQLite test engine does not enable foreign-key cascades.
            await cleanup.execute(delete(UserSubscriptionUpdate).where(UserSubscriptionUpdate.user_id == user_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()

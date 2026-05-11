from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.crud.user import get_users_to_reset_data_usage
from app.db.models import (
    Admin,
    DataLimitResetStrategy,
    User,
    UserUsageResetLogs,
    UserUsageResetSource,
)
from app.models.proxy import ProxyTable
from tests.api import TestSession


@pytest.mark.asyncio
async def test_manual_reset_does_not_delay_periodic_data_usage_reset():
    now = datetime.now(timezone.utc)

    async with TestSession() as session:
        admin = Admin(username=f"admin_reset_cycle_{uuid4().hex[:8]}", hashed_password="secret")
        session.add(admin)
        await session.flush()

        manual_reset_user = User(
            username=f"manual_reset_cycle_{uuid4().hex[:8]}",
            admin_id=admin.id,
            data_limit_reset_strategy=DataLimitResetStrategy.month,
            proxy_settings=ProxyTable().dict(no_obj=True),
        )
        manual_reset_user.created_at = now - timedelta(days=31)

        scheduled_reset_user = User(
            username=f"scheduled_reset_cycle_{uuid4().hex[:8]}",
            admin_id=admin.id,
            data_limit_reset_strategy=DataLimitResetStrategy.month,
            proxy_settings=ProxyTable().dict(no_obj=True),
        )
        scheduled_reset_user.created_at = now - timedelta(days=31)

        session.add_all([manual_reset_user, scheduled_reset_user])
        await session.flush()
        await session.execute(
            delete(UserUsageResetLogs).where(
                UserUsageResetLogs.user_id.in_([manual_reset_user.id, scheduled_reset_user.id])
            )
        )

        manual_log = UserUsageResetLogs(
            user_id=manual_reset_user.id,
            used_traffic_at_reset=1024,
            reset_source=UserUsageResetSource.manual.value,
        )
        manual_log.reset_at = now - timedelta(days=1)

        scheduled_log = UserUsageResetLogs(
            user_id=scheduled_reset_user.id,
            used_traffic_at_reset=2048,
            reset_source=UserUsageResetSource.scheduled.value,
        )
        scheduled_log.reset_at = now - timedelta(days=1)

        session.add_all([manual_log, scheduled_log])
        await session.commit()

        users_to_reset = await get_users_to_reset_data_usage(session)
        user_ids_to_reset = {user.id for user in users_to_reset}

        assert manual_reset_user.id in user_ids_to_reset
        assert scheduled_reset_user.id not in user_ids_to_reset

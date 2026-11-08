"""Chat reminders and webhooks have separate thresholds, so neither may mark the other as already sent."""

import pytest
from sqlalchemy import select, update

from app.db.crud.user import (
    bulk_create_notification_reminders,
    delete_user_passed_notification_reminders,
    get_usage_percentage_reached_users,
)
from app.db.models import NotificationReminder, ReminderType, User
from tests.api import TestSession
from tests.api.helpers import create_user, delete_user


def _reminder(user_id: int, threshold: int, for_chat: bool) -> dict:
    return {
        "user_id": user_id,
        "type": ReminderType.data_usage,
        "threshold": threshold,
        "expires_at": None,
        "for_chat": for_chat,
    }


async def _ids_at(db, percent: int, for_chat: bool) -> set[int]:
    return {user.id for user in await get_usage_percentage_reached_users(db, percent, for_chat=for_chat)}


@pytest.mark.asyncio
async def test_chat_and_webhook_reminders_are_recorded_separately(access_token):
    created = create_user(access_token)
    user_id = created["id"]
    try:
        async with TestSession() as db:
            await db.execute(update(User).where(User.id == user_id).values(used_traffic=created["data_limit"]))
            await db.commit()

            assert user_id in await _ids_at(db, 80, for_chat=False)
            assert user_id in await _ids_at(db, 80, for_chat=True)

            await bulk_create_notification_reminders(db, [_reminder(user_id, 80, for_chat=False)])
            assert user_id not in await _ids_at(db, 80, for_chat=False)
            assert user_id in await _ids_at(db, 80, for_chat=True)

            await bulk_create_notification_reminders(db, [_reminder(user_id, 80, for_chat=True)])
            assert user_id not in await _ids_at(db, 80, for_chat=True)

            # A usage reset re-arms both kinds.
            await delete_user_passed_notification_reminders(db, user_id, ReminderType.data_usage, 0)
            await db.commit()
            rows = await db.scalars(select(NotificationReminder).where(NotificationReminder.user_id == user_id))
            assert rows.all() == []
    finally:
        delete_user(access_token, created["username"])

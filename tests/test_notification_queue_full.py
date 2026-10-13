"""A full notification queue drops the new notification instead of failing the caller."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from nats.js.errors import NotFoundError, ServiceUnavailableError

from app.jobs import review_users
from app.models.settings import Webhook, WebhookInfo
from app.notification import queue_manager, webhook as webhook_notification
from app.notification.nats_queue import InMemoryNotificationQueue, NatsNotificationQueue

STREAM_FULL = ServiceUnavailableError(code=503, err_code=10077, description="maximum messages exceeded")
BYTES_FULL = ServiceUnavailableError(code=503, err_code=10077, description="maximum bytes exceeded")


@pytest.fixture
def full_queues(monkeypatch: pytest.MonkeyPatch):
    """Both notification queues accept a single item; later enqueues find them full."""
    queues = SimpleNamespace(main=InMemoryNotificationQueue(maxsize=1), webhook=InMemoryNotificationQueue(maxsize=1))
    monkeypatch.setattr(queue_manager, "queue_instance", queues.main)
    monkeypatch.setattr(queue_manager, "webhook_queue_instance", queues.webhook)
    logger = MagicMock()
    monkeypatch.setattr(queue_manager, "logger", logger)
    queues.logger = logger
    return queues


def _nats_queue(publish_error) -> NatsNotificationQueue:
    queue = NatsNotificationQueue(stream_name="WEBHOOKS", subject="webhooks.queue")
    queue._js = SimpleNamespace(publish=AsyncMock(side_effect=publish_error))
    return queue


@pytest.mark.parametrize("error", [STREAM_FULL, BYTES_FULL], ids=["max-msgs", "max-bytes"])
async def test_nats_enqueue_reports_a_full_stream_as_queue_full(error):
    with pytest.raises(asyncio.QueueFull):
        await _nats_queue(error).enqueue({"id": 1})


@pytest.mark.parametrize(
    "error",
    [
        ServiceUnavailableError(code=503, err_code=10077, description="store closed"),
        NotFoundError(code=404, err_code=10059, description="stream not found"),
    ],
    ids=["other-store-failure", "missing-stream"],
)
async def test_nats_enqueue_keeps_other_publish_errors(error):
    with pytest.raises(type(error)):
        await _nats_queue(error).enqueue({"id": 1})


async def test_enqueue_helpers_drop_and_log_when_the_queue_is_full(full_queues):
    await queue_manager.enqueue_webhook({"id": 1})
    await queue_manager.enqueue_telegram("first", chat_id=1)

    await queue_manager.enqueue_webhook({"id": 2})
    await queue_manager.enqueue_telegram("second", chat_id=1)
    await queue_manager.enqueue_discord({"content": "third"}, "https://discord.invalid/hook")

    assert full_queues.webhook._count == 1
    assert full_queues.main._count == 1
    dropped = [call.args[1] for call in full_queues.logger.warning.call_args_list]
    assert dropped == ["webhook", "telegram", "discord"]


async def test_enqueue_helper_drops_when_the_nats_stream_is_full(full_queues, monkeypatch):
    queue = _nats_queue(STREAM_FULL)
    monkeypatch.setattr(queue_manager, "webhook_queue_instance", queue)
    await queue_manager.enqueue_webhook({"id": 1})
    queue._js.publish.assert_awaited_once()
    full_queues.logger.warning.assert_called_once()


async def test_enqueue_helpers_still_raise_unexpected_errors(monkeypatch):
    monkeypatch.setattr(queue_manager, "webhook_queue_instance", _nats_queue(RuntimeError("broken")))
    with pytest.raises(RuntimeError, match="broken"):
        await queue_manager.enqueue_webhook({"id": 1})


async def test_bulk_notify_survives_a_full_webhook_queue(full_queues, monkeypatch):
    settings = Webhook(
        enable=True, webhooks=[WebhookInfo(url="http://127.0.0.1:9/h", secret="")], timeout=1, recurrent=1
    )
    monkeypatch.setattr(webhook_notification, "webhook_settings", AsyncMock(return_value=settings))

    await webhook_notification.bulk_notify([{"id": i} for i in range(5)])

    assert full_queues.webhook._count == 1
    assert full_queues.logger.warning.call_count == 4


async def test_days_left_job_records_every_threshold_when_the_queue_is_full(full_queues, monkeypatch):
    """review_users enqueues right after recording reminders; a full queue must not abort the job."""
    settings = Webhook(
        enable=True,
        webhooks=[WebhookInfo(url="http://127.0.0.1:9/h", secret="")],
        days_left=[3, 1],
        timeout=1,
        recurrent=1,
    )
    monkeypatch.setattr(review_users, "webhook_settings", AsyncMock(return_value=settings))
    monkeypatch.setattr(webhook_notification, "webhook_settings", AsyncMock(return_value=settings))

    @asynccontextmanager
    async def fake_db():
        yield AsyncMock()

    users = {
        3: [SimpleNamespace(id=1, days_left=3, expire=None), SimpleNamespace(id=2, days_left=3, expire=None)],
        1: [SimpleNamespace(id=3, days_left=1, expire=None)],
    }
    monkeypatch.setattr(review_users, "GetDB", fake_db)
    monkeypatch.setattr(
        review_users, "get_days_left_reached_users", AsyncMock(side_effect=lambda db, days: users[days])
    )
    monkeypatch.setattr(
        review_users,
        "UserNotificationResponse",
        SimpleNamespace(model_validate=lambda user: SimpleNamespace(username=f"user{user.id}")),
    )
    monkeypatch.setattr(review_users.notification.wh, "ReachedDaysLeft", lambda **kwargs: {"user": kwargs["username"]})
    record_reminders = AsyncMock()
    monkeypatch.setattr(review_users, "bulk_create_notification_reminders", record_reminders)

    await review_users.days_left_notification_job()

    assert [[row["user_id"] for row in call.args[1]] for call in record_reminders.await_args_list] == [[1, 2], [3]]
    assert full_queues.webhook._count == 1
    assert full_queues.logger.warning.call_count == 2

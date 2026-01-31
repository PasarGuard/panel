from app import on_shutdown, scheduler
from app.notification.client import process_notification
from app.notification.queue_manager import get_queue
from app.utils.logger import get_logger
from config import IS_NODE_WORKER, JOB_SEND_NOTIFICATIONS_INTERVAL, RUN_SCHEDULER

logger = get_logger("process-notification-queues")


async def process_all_notification_queues():
    """
    Drain queued notifications and process them.
    """
    if IS_NODE_WORKER:
        return

    logger.debug("Processing notification queues")

    queue = get_queue()
    while True:
        item = await queue.dequeue(timeout=0.1)
        if not item:
            break
        await process_notification(item)


async def send_pending_notifications_before_shutdown():
    logger.info("Notification final flush before shutdown")
    await process_all_notification_queues()


# Schedule the job to run at the same interval as webhook notifications
if RUN_SCHEDULER and not IS_NODE_WORKER:
    scheduler.add_job(
        process_all_notification_queues,
        "interval",
        seconds=JOB_SEND_NOTIFICATIONS_INTERVAL,
        max_instances=1,
        coalesce=True,
        id="process_notification_queues",
        replace_existing=True,
    )

    on_shutdown(send_pending_notifications_before_shutdown)

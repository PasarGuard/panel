from app.utils.logger import get_logger

logger = get_logger("process-notification-queues")
logger.debug("Notification queues are dispatched by scheduler_worker.run_notification_dispatcher.")

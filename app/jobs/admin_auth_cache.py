from datetime import datetime, timezone

from app import scheduler
from app.nats.admin_auth_cache import admin_auth_cache_service
from app.utils.logger import get_logger
from config import ADMIN_AUTH_CACHE_REFRESH_INTERVAL_SECONDS, ROLE


logger = get_logger("jobs")


async def refresh_admin_auth_cache():
    try:
        await admin_auth_cache_service.refresh_now()
    except Exception as exc:
        logger.warning(f"admin auth cache refresh failed: {exc}")


if ROLE.runs_scheduler:
    scheduler.add_job(
        refresh_admin_auth_cache,
        "interval",
        seconds=max(1, ADMIN_AUTH_CACHE_REFRESH_INTERVAL_SECONDS),
        coalesce=True,
        max_instances=1,
        id="refresh_admin_auth_cache",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )

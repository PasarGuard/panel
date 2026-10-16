"""Compact completed node-sync work on the scheduler leader only."""

import asyncio

from app import scheduler
from app.nats import is_nats_enabled, needs_shared_bridge_memory
from app.nats.client import create_nats_client, get_jetstream_context
from app.nats.kv_cleanup import compact_deleted_keys
from app.nats.leader import is_job_leader
from app.notification.dedup import cleanup_legacy_notification_claims
from app.utils.logger import get_logger
from config import nats_settings, runtime_settings

logger = get_logger("jobs")


async def cleanup_node_sync():
    if not is_job_leader():
        return
    nc = await create_nats_client()
    if nc is None:
        return
    try:
        async with asyncio.timeout(240):
            js = await get_jetstream_context(nc)
            count = await cleanup_legacy_notification_claims(js)
            if needs_shared_bridge_memory():
                count += await compact_deleted_keys(js, nats_settings.node_user_sync_kv_bucket)
        if count:
            logger.info("Compacted %s completed node-sync keys", count)
    except TimeoutError:
        logger.warning("node-sync key compaction timed out; retrying on the next interval")
    finally:
        await nc.close()


if (runtime_settings.role.runs_node or runtime_settings.role.runs_scheduler) and is_nats_enabled():
    scheduler.add_job(
        cleanup_node_sync,
        "interval",
        seconds=300,
        max_instances=1,
        coalesce=True,
        id="cleanup_node_sync",
        replace_existing=True,
    )

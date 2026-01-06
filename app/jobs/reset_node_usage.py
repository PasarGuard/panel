import asyncio
from datetime import datetime as dt, timedelta as td, timezone as tz

from app import scheduler
from app.db import GetDB
from app.db.models import NodeStatus
from app.db.crud.node import get_nodes_to_reset_usage, bulk_reset_node_usage
from app.models.node import NodeResponse
from app import notification
from app.jobs.dependencies import SYSTEM_ADMIN
from app.utils.logger import get_logger
from config import IS_NODE_WORKER, JOB_RESET_NODE_USAGE_INTERVAL

logger = get_logger("jobs")


async def reset_node_data_usage():
    async with GetDB() as db:
        nodes = await get_nodes_to_reset_usage(db)
        old_statuses = {node.id: node.status for node in nodes}

        updated_nodes = await bulk_reset_node_usage(db, nodes)

        for db_node in updated_nodes:
            node = NodeResponse.model_validate(db_node)
            old_uplink = 0  # Already reset, so old values were in the log
            old_downlink = 0

            # Get the latest log to find actual old values
            if db_node.usage_logs:
                latest_log = max(db_node.usage_logs, key=lambda log: log.created_at)
                old_uplink = latest_log.uplink
                old_downlink = latest_log.downlink

            asyncio.create_task(notification.reset_node_usage(node, SYSTEM_ADMIN.username, old_uplink, old_downlink))

            if old_statuses.get(node.id) == NodeStatus.limited and node.status != NodeStatus.limited:
                # Node was limited but now reset - could send status change notification if needed
                pass

            logger.info(f'Node data usage reset for Node "{node.name}" (ID: {node.id})')


if IS_NODE_WORKER:
    scheduler.add_job(
        reset_node_data_usage,
        "interval",
        seconds=JOB_RESET_NODE_USAGE_INTERVAL,
        coalesce=True,
        start_date=dt.now(tz.utc) + td(minutes=1),
        max_instances=1,
        id="reset_node_usage",
        replace_existing=True,
    )

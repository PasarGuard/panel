import asyncio
from datetime import UTC, datetime as dt, timedelta as td

from app import notification, scheduler
from app.db import GetDB
from app.db.crud.node import bulk_reset_node_usage, get_nodes_to_reset_usage
from app.db.models import NodeStatus
from app.jobs.dependencies import SYSTEM_ADMIN
from app.models.node import NodeResponse
from app.operation import OperatorType
from app.operation.node import NodeOperation
from app.utils.logger import get_logger
from config import job_settings, runtime_settings

logger = get_logger("jobs")
node_operator = NodeOperation(operator_type=OperatorType.SYSTEM)


async def reset_node_data_usage():
    async with GetDB() as db:
        nodes = await get_nodes_to_reset_usage(db)
        limited_node_ids = {node.id for node in nodes if node.status == NodeStatus.limited}

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

            if db_node.id in limited_node_ids:
                await node_operator.connect_single_node(db, db_node.id)

            logger.info(f'Node data usage reset for Node "{node.name}" (ID: {node.id})')


if runtime_settings.role.runs_scheduler:
    scheduler.add_job(
        reset_node_data_usage,
        "interval",
        seconds=job_settings.reset_node_usage_interval,
        coalesce=True,
        start_date=dt.now(UTC) + td(minutes=1),
        max_instances=1,
        id="reset_node_usage",
        replace_existing=True,
    )

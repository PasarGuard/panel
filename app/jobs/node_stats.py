import asyncio

from PasarGuardNodeBridge import PasarGuardNode

from app import scheduler
from app.db import GetDB
from app.db.models import NodeStat
from app.node import node_manager
from app.settings import general_settings
from app.utils.logger import get_logger
from config import database_settings, job_settings, runtime_settings

logger = get_logger("jobs")


async def get_stat(id: int, node: PasarGuardNode) -> NodeStat:
    try:
        stats = await node.get_system_stats()
    except Exception:
        return

    if not stats:
        return

    return NodeStat(
        node_id=id,
        mem_total=stats.mem_total,
        mem_used=stats.mem_used,
        cpu_cores=stats.cpu_cores,
        cpu_usage=stats.cpu_usage,
        incoming_bandwidth_speed=stats.incoming_bandwidth_speed,
        outgoing_bandwidth_speed=stats.outgoing_bandwidth_speed,
    )


async def gather_nodes_stats():
    # Node stats are stored on PostgreSQL only
    if not database_settings.is_postgresql or not (await general_settings()).usage.record_node_stats:
        return

    nodes = await node_manager.get_healthy_nodes()

    stats_list = await asyncio.gather(*[get_stat(id, node) for id, node in nodes])

    valid_stats = [stat for stat in stats_list if stat is not None]

    if valid_stats:
        async with GetDB() as db:
            db.add_all(valid_stats)
            await db.commit()


if runtime_settings.role.runs_node:
    scheduler.add_job(
        gather_nodes_stats,
        "interval",
        seconds=job_settings.gather_nodes_stats_interval,
        coalesce=True,
        max_instances=1,
        id="gather_nodes_stats",
        replace_existing=True,
    )

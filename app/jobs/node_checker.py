import asyncio

from PasarGuardNodeBridge import NodeAPIError, PasarGuardNode, Health

from app import on_shutdown, on_startup, scheduler
from app.db import GetDB
from app.db.models import Node, NodeStatus
from app.db.crud.node import get_nodes
from app.node import node_manager
from app.utils.logger import get_logger
from app.operation.node import NodeOperation
from app.operation import OperatorType

from config import JOB_CORE_HEALTH_CHECK_INTERVAL


node_operator = NodeOperation(operator_type=OperatorType.SYSTEM)
logger = get_logger("node-checker")


async def node_health_check():
    async def check_node(id: int, node: PasarGuardNode):
        try:
            await node.get_backend_stats(timeout=8)

            await node_operator.update_node_status(
                id, NodeStatus.connected, await node.core_version(), await node.node_version()
            )
        except NodeAPIError as e:
            if e.code > -3:
                await node_operator.update_node_status(id, NodeStatus.error, err=e.detail)
            if e.code > 0:
                await node_operator.connect_node(node_id=id)

    async def check_health(db_node: Node, node: PasarGuardNode):
        if node is None:
            return
        try:
            health = await asyncio.wait_for(node.get_health(), timeout=10)
        except (asyncio.TimeoutError, NodeAPIError):
            await node_operator.update_node_status(db_node.id, NodeStatus.error, err="Get health timeout")

        if db_node.status in (NodeStatus.connecting, NodeStatus.error) and health is Health.HEALTHY:
            await node_operator.update_node_status(db_node.id, NodeStatus.connected)

        elif db_node.status in (NodeStatus.connecting, NodeStatus.error) and health in (
            Health.NOT_CONNECTED,
            Health.BROKEN,
        ):
            await node_operator.connect_node(node_id=db_node.id)

        elif db_node.status == NodeStatus.connected and health is not Health.HEALTHY:
            await check_node(db_node.id, node)

    async with GetDB() as db:
        db_nodes = await get_nodes(db=db, enabled=True)
        dict_nodes = await node_manager.get_nodes()

        check_tasks = [check_health(db_node, dict_nodes[db_node.id]) for db_node in db_nodes]
        await asyncio.gather(*check_tasks, return_exceptions=True)


@on_startup
async def initialize_nodes():
    logger.info("Starting main and nodes' cores...")

    async with GetDB() as db:
        db_nodes = await get_nodes(db=db, enabled=True)

        async def start_node(node: Node):
            try:
                await node_manager.update_node(node)
            except NodeAPIError as e:
                await node_operator.update_node_status(node.id, NodeStatus.error, err=e.detail)
                return

            await node_operator.connect_node(node_id=node.id)

        start_tasks = [start_node(node=db_node) for db_node in db_nodes]

        await asyncio.gather(*start_tasks)

    logger.info("All nodes' cores have been started.")

    scheduler.add_job(
        node_health_check, "interval", seconds=JOB_CORE_HEALTH_CHECK_INTERVAL, coalesce=True, max_instances=1
    )


@on_shutdown
async def shutdown_nodes():
    logger.info("Stopping nodes' cores...")

    nodes: dict[int, PasarGuardNode] = await node_manager.get_nodes()

    stop_tasks = [node.stop() for node in nodes.values()]

    # Run all tasks concurrently and wait for them to complete
    await asyncio.gather(*stop_tasks, return_exceptions=True)

    logger.info("All nodes' cores have been stopped.")

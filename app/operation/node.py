import asyncio
from datetime import datetime as dt
from typing import AsyncIterator, Callable

from PasarGuardNodeBridge import PasarGuardNode, NodeAPIError
from sqlalchemy.exc import IntegrityError

from app import notification
from app.core.manager import core_manager
from app.db import AsyncSession
from app.db.crud.node import (
    bulk_update_node_status,
    clear_usage_data,
    create_node,
    get_node_by_id,
    get_node_stats,
    get_nodes,
    get_nodes_usage,
    modify_node,
    remove_node,
    update_node_status,
)
from app.db.crud.user import get_user
from app.db.models import Node, NodeStatus
from app.models.admin import AdminDetails
from app.models.node import NodeCreate, NodeModify, NodeNotification, NodeResponse, UsageTable
from app.models.stats import NodeRealtimeStats, NodeStatsList, NodeUsageStatsList, Period
from app.node import core_users, node_manager
from app.operation import BaseOperation
from app.utils.logger import get_logger

MAX_MESSAGE_LENGTH = 128

logger = get_logger("node-operation")


class NodeOperation(BaseOperation):
    async def get_db_nodes(
        self,
        db: AsyncSession,
        core_id: int | None = None,
        offset: int | None = None,
        limit: int | None = None,
        enable: bool = False,
    ) -> list[Node]:
        return await get_nodes(db=db, core_id=core_id, offset=offset, limit=limit, enable=enable)

    @staticmethod
    async def _update_single_node_status(
        db: AsyncSession,
        node_id: int,
        status: NodeStatus,
        message: str = "",
        xray_version: str = "",
        node_version: str = "",
        send_notification: bool = True,
    ):
        """
        Update single node status with optional notification.

        Args:
            db (AsyncSession): Database session to use.
            node_id (int): ID of the node to update.
            status (NodeStatus): New status.
            message (str): Status message (e.g., error details).
            xray_version (str): Xray version.
            node_version (str): Node version.
            send_notification (bool): Whether to send notification.
        """
        db_node = await get_node_by_id(db, node_id)
        if not db_node:
            return

        old_status = db_node.status

        if status == NodeStatus.error:
            logger.error(f"Failed to connect node {db_node.name} with id {db_node.id}, Error: {message}")

        await update_node_status(
            db=db,
            db_node=db_node,
            status=status,
            message=message,
            xray_version=xray_version,
            node_version=node_version,
        )

        if not send_notification:
            return

        if status == NodeStatus.connected:
            node_notif = NodeNotification(
                id=db_node.id,
                name=db_node.name,
                xray_version=xray_version,
                node_version=node_version,
            )
            asyncio.create_task(notification.connect_node(node_notif))
        elif status == NodeStatus.error and old_status != NodeStatus.error:
            truncated_message = (
                message[: MAX_MESSAGE_LENGTH - 3] + "..." if len(message) > MAX_MESSAGE_LENGTH else message
            )
            node_notif = NodeNotification(
                id=db_node.id,
                name=db_node.name,
                message=truncated_message,
            )
            asyncio.create_task(notification.error_node(node_notif))

    @staticmethod
    async def connect_node(db_node: Node, users: list) -> dict | None:
        """
        Connect to a node and return status result (does NOT update database).

        Args:
            db_node (Node): Node object from database.
            users (list): Pre-fetched core users list.

        Returns:
            dict: {node_id, status, message, xray_version, node_version, old_status}
            None: if connection should be skipped
        """
        pg_node: PasarGuardNode | None = await node_manager.get_node(db_node.id)
        if pg_node is None:
            return None

        old_status = db_node.status
        logger.info(f'Connecting to "{db_node.name}" node')

        core = await core_manager.get_core(db_node.core_config_id if db_node.core_config_id else 1)

        try:
            info = await pg_node.start(
                config=core.to_str(),
                backend_type=0,
                users=users,
                keep_alive=db_node.keep_alive,
                exclude_inbounds=core.exclude_inbound_tags,
                timeout=10,
            )
            logger.info(f'Connected to "{db_node.name}" node v{info.node_version}, xray run on v{info.core_version}')

            return {
                "node_id": db_node.id,
                "status": NodeStatus.connected,
                "message": "",
                "xray_version": info.core_version,
                "node_version": info.node_version,
                "old_status": old_status,
            }
        except NodeAPIError as e:
            if e.code == -4:
                return None

            detail = e.detail[:1020] + "..." if len(e.detail) > 1024 else e.detail

            logger.error(f"Failed to connect node {db_node.name} with id {db_node.id}, Error: {detail}")

            return {
                "node_id": db_node.id,
                "status": NodeStatus.error,
                "message": detail,
                "xray_version": "",
                "node_version": "",
                "old_status": old_status,
            }

    async def create_node(self, db: AsyncSession, new_node: NodeCreate, admin: AdminDetails) -> NodeResponse:
        await self.get_validated_core_config(db, new_node.core_config_id)
        try:
            db_node = await create_node(db, new_node)
        except IntegrityError:
            await self.raise_error(message=f'Node "{new_node.name}" already exists', code=409, db=db)

        try:
            await node_manager.update_node(db_node)
            asyncio.create_task(self.connect_node_wrapper(db, db_node.id))
        except NodeAPIError as e:
            await self._update_single_node_status(db, db_node.id, NodeStatus.error, message=e.detail)

        logger.info(f'New node "{db_node.name}" with id "{db_node.id}" added by admin "{admin.username}"')

        node = NodeResponse.model_validate(db_node)

        asyncio.create_task(notification.create_node(node, admin.username))

        return node

    async def modify_node(
        self, db: AsyncSession, node_id: Node, modified_node: NodeModify, admin: AdminDetails
    ) -> Node:
        db_node = await self.get_validated_node(db=db, node_id=node_id)
        if modified_node.core_config_id is not None:
            await self.get_validated_core_config(db, modified_node.core_config_id)

        try:
            db_node = await modify_node(db, db_node, modified_node)
        except IntegrityError:
            await self.raise_error(message=f'Node "{db_node.name}" already exists', code=409, db=db)

        if db_node.status is NodeStatus.disabled:
            await node_manager.remove_node(db_node.id)
        else:
            try:
                await node_manager.update_node(db_node)
                asyncio.create_task(self.connect_node_wrapper(db, db_node.id))
            except NodeAPIError as e:
                await self._update_single_node_status(db, db_node.id, NodeStatus.error, message=e.detail)

        logger.info(f'Node "{db_node.name}" with id "{db_node.id}" modified by admin "{admin.username}"')

        node = NodeResponse.model_validate(db_node)

        asyncio.create_task(notification.modify_node(node, admin.username))

        return node

    async def remove_node(self, db: AsyncSession, node_id: Node, admin: AdminDetails) -> None:
        db_node: Node = await self.get_validated_node(db=db, node_id=node_id)

        await node_manager.remove_node(db_node.id)
        await remove_node(db=db, db_node=db_node)

        logger.info(f'Node "{db_node.name}" with id "{db_node.id}" deleted by admin "{admin.username}"')

        asyncio.create_task(notification.remove_node(db_node, admin.username))

    async def connect_nodes_bulk(
        self,
        db: AsyncSession,
        nodes: list[Node],
    ) -> None:
        """
        Connect multiple nodes and bulk update their statuses.

        Args:
            db (AsyncSession): Database session.
            nodes (list[Node]): List of nodes to connect.
        """
        if not nodes:
            return

        # Fetch users ONCE for all nodes
        users = await core_users(db=db)

        async def connect_single(node: Node) -> dict | None:
            try:
                await node_manager.update_node(node)
            except NodeAPIError as e:
                return {
                    "node_id": node.id,
                    "status": NodeStatus.error,
                    "message": e.detail,
                    "xray_version": "",
                    "node_version": "",
                    "old_status": node.status,
                }

            return await self.connect_node(node, users)

        results = await asyncio.gather(*[connect_single(node) for node in nodes])

        # Filter out None results
        valid_results = [r for r in results if r is not None]

        nodes_dict = {node.id: node for node in nodes}

        notifications_to_send = []
        for result in valid_results:
            node = nodes_dict.get(result["node_id"])
            if not node:
                continue

            # Create lightweight notification object
            node_notif = NodeNotification(
                id=result["node_id"],
                name=node.name,
                xray_version=result.get("xray_version"),
                node_version=result.get("node_version"),
                message=result.get("message"),
            )

            notifications_to_send.append(
                {
                    "node": node_notif,
                    "status": result["status"],
                    "old_status": result["old_status"],
                }
            )

        # Bulk update all statuses in ONE query
        await bulk_update_node_status(db, valid_results)

        # Send notifications using pre-built objects
        for notif in notifications_to_send:
            if notif["status"] == NodeStatus.connected:
                asyncio.create_task(notification.connect_node(notif["node"]))
            elif notif["status"] == NodeStatus.error and notif["old_status"] != NodeStatus.error:
                asyncio.create_task(notification.error_node(notif["node"]))

    async def connect_node_wrapper(self, db: AsyncSession, node_id: int) -> None:
        """
        Connect single node by wrapping it in a list for bulk operation.

        Args:
            db (AsyncSession): Database session.
            node_id (int): ID of the node to connect.
        """
        db_node = await get_node_by_id(db, node_id)
        if db_node is None:
            return

        await self.connect_nodes_bulk(db, [db_node])

    async def restart_node(self, db: AsyncSession, node_id: Node, admin: AdminDetails) -> None:
        await self.connect_node_wrapper(db, node_id)
        logger.info(f'Node "{node_id}" restarted by admin "{admin.username}"')

    async def restart_all_node(self, db: AsyncSession, admin: AdminDetails, core_id: int | None = None) -> None:
        nodes: list[Node] = await self.get_db_nodes(db, core_id, enable=True)
        await self.connect_nodes_bulk(db, nodes)
        logger.info(f'All nodes restarted by admin "{admin.username}"')

    async def get_usage(
        self,
        db: AsyncSession,
        start: dt = None,
        end: dt = None,
        period: Period = Period.hour,
        node_id: int | None = None,
        group_by_node: bool = False,
    ) -> NodeUsageStatsList:
        start, end = await self.validate_dates(start, end)
        return await get_nodes_usage(db, start, end, period=period, node_id=node_id, group_by_node=group_by_node)

    async def get_logs(self, node_id: Node) -> Callable[[], AsyncIterator[asyncio.Queue]]:
        node = await node_manager.get_node(node_id)

        if node is None:
            await self.raise_error(message="Node not found", code=404)

        return node.stream_logs

    async def get_node_stats_periodic(
        self, db: AsyncSession, node_id: id, start: dt = None, end: dt = None, period: Period = Period.hour
    ) -> NodeStatsList:
        start, end = await self.validate_dates(start, end)

        return await get_node_stats(db, node_id, start, end, period=period)

    async def get_node_system_stats(self, node_id: Node) -> NodeRealtimeStats:
        node = await node_manager.get_node(node_id)

        if node is None:
            await self.raise_error(message="Node not found", code=404)

        try:
            stats = await node.get_system_stats()
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)

        if stats is None:
            await self.raise_error(message="Stats not found", code=404)

        return NodeRealtimeStats(
            mem_total=stats.mem_total,
            mem_used=stats.mem_used,
            cpu_cores=stats.cpu_cores,
            cpu_usage=stats.cpu_usage,
            incoming_bandwidth_speed=stats.incoming_bandwidth_speed,
            outgoing_bandwidth_speed=stats.outgoing_bandwidth_speed,
        )

    async def get_nodes_system_stats(self) -> dict[int, NodeRealtimeStats | None]:
        nodes = await node_manager.get_healthy_nodes()
        stats_tasks = {id: asyncio.create_task(self._get_node_stats_safe(id)) for id, _ in nodes}

        await asyncio.gather(*stats_tasks.values(), return_exceptions=True)

        results = {}
        for node_id, task in stats_tasks.items():
            if task.exception():
                results[node_id] = None
            else:
                results[node_id] = task.result()

        return results

    async def _get_node_stats_safe(self, node_id: Node) -> NodeRealtimeStats | None:
        """Wrapper method that returns None instead of raising exceptions"""
        try:
            return await self.get_node_system_stats(node_id)
        except Exception as e:
            logger.error(f"Error getting system stats for node {node_id}: {e}")
            return None

    async def get_user_online_stats_by_node(self, db: AsyncSession, node_id: Node, username: str) -> dict[int, int]:
        db_user = await get_user(db, username=username)
        if db_user is None:
            await self.raise_error(message="User not found", code=404)

        node = await node_manager.get_node(node_id)

        if node is None:
            await self.raise_error(message="Node not found", code=404)

        try:
            stats = await node.get_user_online_stats(email=f"{db_user.id}.{db_user.username}")
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)

        if stats is None:
            await self.raise_error(message="Stats not found", code=404)

        return {node_id: stats.value}

    async def get_user_ip_list_by_node(
        self, db: AsyncSession, node_id: Node, username: str
    ) -> dict[int, dict[str, int]]:
        db_user = await get_user(db, username=username)
        if db_user is None:
            await self.raise_error(message="User not found", code=404)

        node = await node_manager.get_node(node_id)

        if node is None:
            await self.raise_error(message="Node not found", code=404)

        try:
            stats = await node.get_user_online_ip_list(email=f"{db_user.id}.{db_user.username}")
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)

        if stats is None:
            await self.raise_error(message="Stats not found", code=404)

        return {node_id: stats.ips}

    async def sync_node_users(self, db: AsyncSession, node_id: int, flush_users: bool = False) -> NodeResponse:
        db_node = await self.get_validated_node(db, node_id=node_id)

        if db_node.status != NodeStatus.connected:
            await self.raise_error(message="Node is not connected", code=406)

        pg_node = await node_manager.get_node(node_id)
        if pg_node is None:
            await self.raise_error(message="Node is not connected", code=409)

        try:
            await pg_node.sync_users(await core_users(db=db), flush_queue=flush_users)
        except NodeAPIError as e:
            await update_node_status(db=db, db_node=db_node, status=NodeStatus.error, message=e.detail)
            await self.raise_error(message=e.detail, code=e.code)

        return NodeResponse.model_validate(db_node)

    async def clear_usage_data(
        self, db: AsyncSession, table: UsageTable, start: dt | None = None, end: dt | None = None
    ):
        if start and end and start >= end:
            await self.raise_error(code=400, message="Start time must be before end time.")

        try:
            await clear_usage_data(db, table, start, end)
            return {"detail": f"All data from '{table}' has been deleted successfully."}
        except Exception as e:
            await self.raise_error(code=400, message=f"Deletion failed due to server error: {str(e)}")

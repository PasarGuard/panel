import asyncio
from datetime import datetime as dt
from typing import AsyncIterator, Callable

from PasarGuardNodeBridge import NodeAPIError, PasarGuardNode
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
    reset_node_usage,
    update_node_status,
)
from app.db.crud.user import get_user, get_users_count_by_status
from app.db.models import Node, NodeStatus, UserStatus
from app.models.admin import AdminDetails
from app.models.node import (
    NodeCoreUpdate,
    NodeCreate,
    NodeGeoFilesUpdate,
    NodeModify,
    NodeNotification,
    NodeResponse,
    NodesResponse,
    UsageTable,
    UserIPList,
    UserIPListAll,
)
from app.models.stats import NodeRealtimeStats, NodeStatsList, NodeUsageStatsList, Period
from app.nats.node_rpc import node_nats_client
from app.node import calculate_max_message_size, core_users, node_manager
from app.operation import BaseOperation, OperatorType
from app.utils.logger import get_logger
from config import IS_NODE_WORKER

MAX_MESSAGE_LENGTH = 128

logger = get_logger("node-operation")


class NodeOperation(BaseOperation):
    def __init__(self, operator_type: OperatorType):
        super().__init__(operator_type)
        if IS_NODE_WORKER:
            self._update_node_impl = self._update_node_local
            self._remove_node_impl = self._remove_node_local
            self._connect_single_impl = self._connect_single_node_local
            self._connect_bulk_impl = self._connect_nodes_bulk_local
            self._disconnect_single_impl = self._disconnect_single_node_local
            self._sync_node_users_impl = self._sync_node_users_local
            self._get_node_stats_impl = self._get_node_system_stats_local
            self._get_nodes_stats_impl = self._get_nodes_system_stats_local
            self._get_user_online_stats_impl = self._get_user_online_stats_local
            self._get_user_ip_list_impl = self._get_user_ip_list_local
            self._get_user_ip_list_all_impl = self._get_user_ip_list_all_local
            self._update_node_api_impl = self._update_node_api_local
            self._update_core_impl = self._update_core_local
            self._update_geofiles_impl = self._update_geofiles_local
            self._get_logs_impl = self._get_logs_local
            self._restart_all_impl = self._restart_all_nodes_local
        else:
            self._update_node_impl = self._update_node_remote
            self._remove_node_impl = self._remove_node_remote
            self._connect_single_impl = self._connect_single_node_remote
            self._connect_bulk_impl = self._connect_nodes_bulk_remote
            self._disconnect_single_impl = self._disconnect_single_node_remote
            self._sync_node_users_impl = self._sync_node_users_remote
            self._get_node_stats_impl = self._get_node_system_stats_remote
            self._get_nodes_stats_impl = self._get_nodes_system_stats_remote
            self._get_user_online_stats_impl = self._get_user_online_stats_remote
            self._get_user_ip_list_impl = self._get_user_ip_list_remote
            self._get_user_ip_list_all_impl = self._get_user_ip_list_all_remote
            self._update_node_api_impl = self._update_node_api_remote
            self._update_core_impl = self._update_core_remote
            self._update_geofiles_impl = self._update_geofiles_remote
            self._get_logs_impl = self._get_logs_remote
            self._restart_all_impl = self._restart_all_nodes_remote

    async def get_db_nodes(
        self,
        db: AsyncSession,
        core_id: int | None = None,
        offset: int | None = None,
        limit: int | None = None,
        enabled: bool = False,
        status: NodeStatus | list[NodeStatus] | None = None,
        ids: list[int] | None = None,
        search: str | None = None,
    ) -> NodesResponse:
        db_nodes, count = await get_nodes(
            db=db,
            core_id=core_id,
            offset=offset,
            limit=limit,
            enabled=enabled,
            status=status,
            ids=ids,
            search=search,
        )
        node_responses = [NodeResponse.model_validate(node) for node in db_nodes]
        return NodesResponse(nodes=node_responses, total=count)

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
            await self._update_node_impl(db_node)
            asyncio.create_task(self._connect_single_impl(db, db_node.id))
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

        if db_node.status in (NodeStatus.disabled, NodeStatus.limited):
            await self.disconnect_single_node(db_node.id)
        else:
            try:
                await self._update_node_impl(db_node)
                asyncio.create_task(self._connect_single_impl(db, db_node.id))
            except NodeAPIError as e:
                await self._update_single_node_status(db, db_node.id, NodeStatus.error, message=e.detail)

        logger.info(f'Node "{db_node.name}" with id "{db_node.id}" modified by admin "{admin.username}"')

        node = NodeResponse.model_validate(db_node)
        asyncio.create_task(notification.modify_node(node, admin.username))

        return node

    async def remove_node(self, db: AsyncSession, node_id: Node, admin: AdminDetails) -> None:
        db_node: Node = await self.get_validated_node(db=db, node_id=node_id)
        node_response = NodeResponse.model_validate(db_node)

        await self._remove_node_impl(db_node.id)
        await remove_node(db=db, db_node=db_node)

        logger.info(f'Node "{node_response.name}" with id "{node_response.id}" deleted by admin "{admin.username}"')

        asyncio.create_task(notification.remove_node(node_response, admin.username))

    async def reset_node_usage(self, db: AsyncSession, node_id: int, admin: AdminDetails) -> NodeResponse:
        """
        Reset a node's traffic usage (uplink and downlink to 0) and create a log entry.

        Args:
            db: Database session
            node_id: ID of the node to reset
            admin: Admin performing the action

        Returns:
            NodeResponse: Updated node object
        """
        db_node = await self.get_validated_node(db=db, node_id=node_id)

        # Store old values for notification
        old_uplink = db_node.uplink
        old_downlink = db_node.downlink

        # Reset usage (creates log entry and sets uplink/downlink to 0)
        db_node = await reset_node_usage(db, db_node)

        # Create response
        node = NodeResponse.model_validate(db_node)

        # Send notification
        asyncio.create_task(notification.reset_node_usage(node, admin.username, old_uplink, old_downlink))

        logger.info(f'Node "{db_node.name}" (ID: {db_node.id}) usage reset by admin "{admin.username}"')

        return node

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
        await self._connect_bulk_impl(db, nodes)

    async def connect_single_node(self, db: AsyncSession, node_id: int) -> None:
        """
        Connect a single node and update its status (optimized for single-node operations).

        Uses simple UPDATE statement instead of bulk update to avoid deadlock risks
        and unnecessary complexity.

        Args:
            db (AsyncSession): Database session.
            node_id (int): ID of the node to connect.
        """
        return await self._connect_single_impl(db, node_id)

    async def _connect_single_node_remote(self, db: AsyncSession, node_id: int) -> None:
        await node_nats_client.publish("connect_node", {"node_id": node_id})

    async def disconnect_single_node(self, node_id: int) -> None:
        """
        Disconnect a single node from the node manager (stop it from running).

        Used when a node needs to be stopped (e.g., when limited or disabled).

        Args:
            node_id (int): ID of the node to disconnect.
        """
        await self._disconnect_single_impl(node_id)
        logger.info(f'Node "{node_id}" disconnected')

    async def restart_node(self, db: AsyncSession, node_id: Node, admin: AdminDetails) -> None:
        await self.connect_single_node(db, node_id)
        logger.info(f'Node "{node_id}" restarted by admin "{admin.username}"')

    async def restart_all_node(self, db: AsyncSession, admin: AdminDetails, core_id: int | None = None) -> None:
        await self._restart_all_impl(db, admin, core_id)
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
        start, end = await self.validate_dates(start, end, True)
        return await get_nodes_usage(db, start, end, period=period, node_id=node_id, group_by_node=group_by_node)

    async def get_logs(self, node_id: Node) -> Callable[[], AsyncIterator[asyncio.Queue]]:
        return await self._get_logs_impl(node_id)

    async def get_node_stats_periodic(
        self, db: AsyncSession, node_id: id, start: dt = None, end: dt = None, period: Period = Period.hour
    ) -> NodeStatsList:
        start, end = await self.validate_dates(start, end, True)

        return await get_node_stats(db, node_id, start, end, period=period)

    async def get_node_system_stats(self, node_id: Node) -> NodeRealtimeStats:
        return await self._get_node_stats_impl(node_id)

    async def get_nodes_system_stats(self) -> dict[int, NodeRealtimeStats | None]:
        return await self._get_nodes_stats_impl()

    async def _get_node_stats_safe(self, node_id: Node) -> NodeRealtimeStats | None:
        """Wrapper method that returns None instead of raising exceptions"""
        try:
            return await self.get_node_system_stats(node_id)
        except Exception as e:
            logger.error(f"Error getting system stats for node {node_id}: {e}")
            return None

    async def get_user_online_stats_by_node(self, db: AsyncSession, node_id: Node, username: str) -> dict[int, int]:
        return await self._get_user_online_stats_impl(db, node_id, username)

    async def get_user_ip_list_by_node(self, db: AsyncSession, node_id: Node, username: str) -> UserIPList:
        return await self._get_user_ip_list_impl(db, node_id, username)

    async def get_user_ip_list_all_nodes(self, db: AsyncSession, username: str) -> UserIPListAll:
        return await self._get_user_ip_list_all_impl(db, username)

    async def _get_node_user_ip_list_safe(self, node_id: int, email: str) -> dict[str, int] | None:
        """Wrapper method that returns None instead of raising exceptions"""
        try:
            node = await node_manager.get_node(node_id)
            if node is None:
                return None

            stats = await node.get_user_online_ip_list(email=email)
            if stats is None:
                return None

            return stats.ips
        except NodeAPIError as e:
            if e.code != 404:
                logger.error(f"Error getting IP list for user {email} on node {node_id}: {e}")
            return None

    async def sync_node_users(self, db: AsyncSession, node_id: int, flush_users: bool = False) -> NodeResponse:
        return await self._sync_node_users_impl(db, node_id, flush_users)

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

    async def update_node(self, db: AsyncSession, node_id: int) -> dict:
        await self.get_validated_node(db, node_id)
        return await self._update_node_api_impl(node_id)

    async def update_core(self, db: AsyncSession, node_id: int, node_core_update: NodeCoreUpdate) -> dict:
        await self.get_validated_node(db, node_id)
        return await self._update_core_impl(node_id, node_core_update)

    async def update_geofiles(self, db: AsyncSession, node_id: int, node_geofiles_update: NodeGeoFilesUpdate) -> dict:
        await self.get_validated_node(db, node_id)
        return await self._update_geofiles_impl(node_id, node_geofiles_update)

    async def _update_node_local(self, db_node: Node) -> None:
        await node_manager.update_node(db_node)

    async def _update_node_remote(self, db_node: Node) -> None:
        await node_nats_client.publish("update_node", {"node_id": db_node.id})

    async def _remove_node_local(self, node_id: int) -> None:
        await node_manager.remove_node(node_id)

    async def _remove_node_remote(self, node_id: int) -> None:
        await node_nats_client.publish("remove_node", {"node_id": node_id})

    async def _connect_nodes_bulk_local(self, db: AsyncSession, nodes: list[Node]) -> None:
        if not nodes:
            return

        # Fetch users ONCE for all nodes
        users = await core_users(db=db)

        # Calculate max_message_size based on active users count (once for all nodes)
        user_counts = await get_users_count_by_status(db, [UserStatus.active])
        active_users_count = user_counts.get(UserStatus.active.value, 0)
        max_message_size = calculate_max_message_size(active_users_count)

        async def connect_single(node: Node) -> dict | None:
            if node is None or node.status in (NodeStatus.disabled, NodeStatus.limited):
                return

            try:
                await node_manager.update_node(node, max_message_size=max_message_size)
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

    async def _connect_nodes_bulk_remote(self, db: AsyncSession, nodes: list[Node]) -> None:
        if not nodes:
            return
        await node_nats_client.publish("connect_nodes_bulk", {"node_ids": [node.id for node in nodes]})

    async def _connect_single_node_local(self, db: AsyncSession, node_id: int) -> None:
        db_node = await get_node_by_id(db, node_id)
        if db_node is None or db_node.status in (NodeStatus.disabled, NodeStatus.limited):
            return

        # Get core users once
        users = await core_users(db=db)

        # Calculate max_message_size based on active users count
        max_message_size = calculate_max_message_size(len(users))

        # Update node manager
        try:
            await node_manager.update_node(db_node, max_message_size=max_message_size)
        except NodeAPIError as e:
            # Update status to error using simple CRUD
            await update_node_status(
                db=db,
                db_node=db_node,
                status=NodeStatus.error,
                message=e.detail,
            )

            # Send error notification
            node_notif = NodeNotification(
                id=db_node.id,
                name=db_node.name,
                message=e.detail,
            )
            asyncio.create_task(notification.error_node(node_notif))
            return

        # Connect the node
        result = await NodeOperation.connect_node(db_node, users)

        if not result:
            return

        # Update status using simple CRUD (NOT bulk!)
        await update_node_status(
            db=db,
            db_node=db_node,
            status=result["status"],
            message=result.get("message", ""),
            xray_version=result.get("xray_version", ""),
            node_version=result.get("node_version", ""),
        )

        # Send appropriate notification
        if result["status"] == NodeStatus.connected:
            node_notif = NodeNotification(
                id=db_node.id,
                name=db_node.name,
                xray_version=result.get("xray_version"),
                node_version=result.get("node_version"),
            )
            asyncio.create_task(notification.connect_node(node_notif))
        elif result["status"] == NodeStatus.error and result["old_status"] != NodeStatus.error:
            node_notif = NodeNotification(
                id=db_node.id,
                name=db_node.name,
                message=result.get("message"),
            )
            asyncio.create_task(notification.error_node(node_notif))

    async def _connect_single_node_remote(self, db: AsyncSession, node_id: int) -> None:
        await node_nats_client.publish("connect_node", {"node_id": node_id})

    async def _disconnect_single_node_local(self, node_id: int) -> None:
        await node_manager.remove_node(node_id)

    async def _disconnect_single_node_remote(self, node_id: int) -> None:
        await node_nats_client.publish("disconnect_node", {"node_id": node_id})

    async def _restart_all_nodes_local(self, db: AsyncSession, admin: AdminDetails, core_id: int | None) -> None:
        nodes, _ = await get_nodes(db, core_id=core_id, enabled=True)
        await self.connect_nodes_bulk(db, nodes)

    async def _restart_all_nodes_remote(self, db: AsyncSession, admin: AdminDetails, core_id: int | None) -> None:
        await node_nats_client.publish("connect_nodes_bulk", {"core_id": core_id})

    async def _get_logs_local(self, node_id: Node) -> Callable[[], AsyncIterator[asyncio.Queue]]:
        node = await node_manager.get_node(node_id)
        if node is None:
            await self.raise_error(message="Node not found", code=404)
        return node.stream_logs

    async def _get_logs_remote(self, node_id: Node) -> Callable[[], AsyncIterator[asyncio.Queue]]:
        await self.raise_error(message="Node logs are only available via node-worker", code=409)

    async def _get_node_system_stats_local(self, node_id: Node) -> NodeRealtimeStats:
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

    async def _get_node_system_stats_remote(self, node_id: Node) -> NodeRealtimeStats:
        data = await node_nats_client.request("get_node_system_stats", {"node_id": node_id})
        return NodeRealtimeStats.model_validate(data)

    async def _get_nodes_system_stats_local(self) -> dict[int, NodeRealtimeStats | None]:
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

    async def _get_nodes_system_stats_remote(self) -> dict[int, NodeRealtimeStats | None]:
        data = await node_nats_client.request("get_nodes_system_stats", {})
        return {int(node_id): (NodeRealtimeStats.model_validate(value) if value else None) for node_id, value in data.items()}

    async def _get_user_online_stats_local(self, db: AsyncSession, node_id: Node, username: str) -> dict[int, int]:
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

    async def _get_user_online_stats_remote(self, db: AsyncSession, node_id: Node, username: str) -> dict[int, int]:
        return await node_nats_client.request("get_user_online_stats", {"node_id": node_id, "username": username})

    async def _get_user_ip_list_local(self, db: AsyncSession, node_id: Node, username: str) -> UserIPList:
        db_user = await get_user(db, username=username)
        if db_user is None:
            await self.raise_error(message="User not found", code=404)

        email = f"{db_user.id}.{db_user.username}"
        ips = await self._get_node_user_ip_list_safe(node_id, email)

        if ips is None:
            await self.raise_error(message="Node unavailable or user not found", code=404)

        return UserIPList(ips=ips)

    async def _get_user_ip_list_remote(self, db: AsyncSession, node_id: Node, username: str) -> UserIPList:
        data = await node_nats_client.request("get_user_ip_list", {"node_id": node_id, "username": username})
        return UserIPList.model_validate(data)

    async def _get_user_ip_list_all_local(self, db: AsyncSession, username: str) -> UserIPListAll:
        db_user = await get_user(db, username=username)
        if db_user is None:
            await self.raise_error(message="User not found", code=404)

        nodes = await node_manager.get_healthy_nodes()
        email = f"{db_user.id}.{db_user.username}"

        ip_list_tasks = {id: asyncio.create_task(self._get_node_user_ip_list_safe(id, email)) for id, _ in nodes}

        await asyncio.gather(*ip_list_tasks.values(), return_exceptions=True)

        results = {}
        for node_id, task in ip_list_tasks.items():
            if task.exception() or task.result() is None:
                continue
            else:
                results[node_id] = UserIPList(ips=task.result())

        return UserIPListAll(nodes=results)

    async def _get_user_ip_list_all_remote(self, db: AsyncSession, username: str) -> UserIPListAll:
        data = await node_nats_client.request("get_user_ip_list_all", {"username": username})
        return UserIPListAll.model_validate(data)

    async def _sync_node_users_local(self, db: AsyncSession, node_id: int, flush_users: bool) -> NodeResponse:
        db_node = await self.get_validated_node(db, node_id=node_id)

        if db_node.status != NodeStatus.connected:
            await self.raise_error(message="Node is not connected", code=406)

        pg_node = await node_manager.get_node(node_id)
        if pg_node is None:
            await self.raise_error(message="Node is not connected", code=409)

        try:
            await pg_node.sync_users(await core_users(db=db), flush_pending=flush_users)
        except NodeAPIError as e:
            await update_node_status(db=db, db_node=db_node, status=NodeStatus.error, message=e.detail)
            await self.raise_error(message=e.detail, code=e.code)

        return NodeResponse.model_validate(db_node)

    async def _sync_node_users_remote(self, db: AsyncSession, node_id: int, flush_users: bool) -> NodeResponse:
        await node_nats_client.publish(
            "sync_node_users",
            {"node_id": node_id, "flush_users": flush_users},
        )
        return NodeResponse.model_validate(await self.get_validated_node(db, node_id))

    async def _update_node_api_local(self, node_id: int) -> dict:
        node = await node_manager.get_node(node_id)
        if node is None:
            await self.raise_error(message="Node not found", code=404)
        try:
            response = await node.update_node()
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)
        return response.json()

    async def _update_node_api_remote(self, node_id: int) -> dict:
        return await node_nats_client.request("update_node_api", {"node_id": node_id})

    async def _update_core_local(self, node_id: int, node_core_update: NodeCoreUpdate) -> dict:
        node = await node_manager.get_node(node_id)
        if node is None:
            await self.raise_error(message="Node not found", code=404)
        try:
            response = await node.update_core(node_core_update.model_dump(mode="json"))
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)
        return response.json()

    async def _update_core_remote(self, node_id: int, node_core_update: NodeCoreUpdate) -> dict:
        return await node_nats_client.request(
            "update_core",
            {"node_id": node_id, "core_update": node_core_update.model_dump(mode="json")},
        )

    async def _update_geofiles_local(self, node_id: int, node_geofiles_update: NodeGeoFilesUpdate) -> dict:
        node = await node_manager.get_node(node_id)
        if node is None:
            await self.raise_error(message="Node not found", code=404)
        try:
            response = await node.update_geofiles(node_geofiles_update.model_dump(mode="json"))
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)
        return response.json()

    async def _update_geofiles_remote(self, node_id: int, node_geofiles_update: NodeGeoFilesUpdate) -> dict:
        return await node_nats_client.request(
            "update_geofiles",
            {"node_id": node_id, "geofiles_update": node_geofiles_update.model_dump(mode="json")},
        )

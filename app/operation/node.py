import asyncio
import json
from copy import deepcopy
from typing import AsyncIterator, Callable

from fastapi import HTTPException
from PasarGuardNodeBridge import NodeAPIError, PasarGuardNode
from PasarGuardNodeBridge.common import service_pb2 as service
from sqlalchemy.exc import IntegrityError

from app import notification
from app.core.manager import core_manager
from app.db import AsyncSession, GetDB
from app.db.crud.node import (
    bulk_reset_node_usage,
    bulk_update_node_status,
    clear_usage_data,
    create_node,
    get_node_by_id,
    get_node_stats,
    get_nodes,
    get_nodes_simple,
    get_nodes_usage,
    modify_node,
    remove_node,
    remove_nodes,
    reset_node_usage,
    update_node_status,
)
from app.db.crud.user import get_user_by_id, get_user_count_metric_stats
from app.db.models import Node, NodeStatus
from app.models.admin import AdminDetails
from app.models.core import CoreType
from app.models.node import (
    BulkNodesActionResponse,
    BulkNodeSelection,
    NodeClearUsageQuery,
    NodeCoreUpdate,
    NodeCreate,
    NodeGeoFilesUpdate,
    NodeListQuery,
    NodeModify,
    NodeNotification,
    NodeResponse,
    NodeSimple,
    NodeSimpleListQuery,
    NodesResponse,
    NodesSimpleResponse,
    NodeStatsPeriodQuery,
    NodeUsageQuery,
    RemoveNodesResponse,
    UsageTable,
    UserIPList,
    UserIPListAll,
)
from app.models.stats import (
    NodeOutboundsLatencyResponse,
    NodeRealtimeStats,
    NodeStatsList,
    NodeUsageStatsList,
    UserCountMetric,
    UserCountMetricStatsList,
    validate_user_count_metric_scope,
)
from app.nats.node_rpc import node_nats_client
from app.node import core_users, node_manager
from app.operation import BaseOperation, OperatorType
from app.utils.logger import get_logger
from config import runtime_settings
from app.core.xray import rename_xhttp_session_keys
from app.subscription.base import is_new_xray

MAX_MESSAGE_LENGTH = 128

logger = get_logger("node-operation")


class NodeOperation(BaseOperation):
    def __init__(self, operator_type: OperatorType):
        super().__init__(operator_type)
        if runtime_settings.role.runs_node:
            self._update_node_impl = self._update_node_local
            self._remove_node_impl = self._remove_node_local
            self._connect_single_impl = self._connect_single_node_local
            self._connect_bulk_impl = self._connect_nodes_bulk_local
            self._disconnect_single_impl = self._disconnect_single_node_local
            self._sync_node_users_impl = self._sync_node_users_local
            self._get_node_stats_impl = self._get_node_system_stats_local
            self._get_nodes_stats_impl = self._get_nodes_system_stats_local
            self._get_outbounds_latency_impl = self._get_outbounds_latency_local
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
            self._get_outbounds_latency_impl = self._get_outbounds_latency_remote
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
        query: NodeListQuery,
    ) -> NodesResponse:
        db_nodes, count = await get_nodes(db=db, query=query)
        node_responses = [NodeResponse.model_validate(node) for node in db_nodes]
        return NodesResponse(nodes=node_responses, total=count)

    async def get_nodes_simple(
        self,
        db: AsyncSession,
        query: NodeSimpleListQuery,
    ) -> NodesSimpleResponse:
        """Get lightweight node list with only id and name"""
        rows, total = await get_nodes_simple(db=db, query=query)

        nodes = [NodeSimple(id=row[0], name=row[1], status=row[2]) for row in rows]

        return NodesSimpleResponse(nodes=nodes, total=total)

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
    async def _get_core_users_map(
        db: AsyncSession, core_ids: set[int]
    ) -> tuple[dict[int, object | None], dict[int, list]]:
        if not core_ids:
            return {}, {}

        resolved_cores = await core_manager.get_cores(core_ids | {1})
        default_core = resolved_cores.get(1)
        cores_by_id: dict[int, object | None] = {}
        users_by_core: dict[int, list] = {}

        for core_id in core_ids:
            core = resolved_cores.get(core_id) or default_core
            cores_by_id[core_id] = core
            if core is None:
                users_by_core[core_id] = []
                continue

            users_by_core[core_id] = await core_users(
                db=db,
                inbound_tags=core.inbounds,
                allowed_protocols=core.protocols,
            )

        return cores_by_id, users_by_core

    @staticmethod
    async def connect_node(db_node: Node, core, users: list) -> dict | None:
        """
        Connect to a node and return status result (does NOT update database).

        Args:
            db_node (Node): Node object from database.
            core: Pre-fetched core config for this node.
            users (list): Pre-fetched core users list.

        Returns:
            dict: {node_id, status, message, xray_version, node_version, old_status}
            None: if connection should be skipped
        """
        pg_node: PasarGuardNode | None = await node_manager.get_node(db_node.id)
        if pg_node is None:
            return None
        if core is None:
            return None
        if core.type == CoreType.xray and (is_new_xray(db_node.xray_version)):
            copied = deepcopy(dict(core))
            rename_xhttp_session_keys(copied)
            config_str = json.dumps(copied)
        else:
            config_str = core.to_str()    
        old_status = db_node.status
        logger.info(f'Connecting to "{db_node.name}" node')
        type = service.BackendType.WIREGUARD if core.type == CoreType.wg else service.BackendType.XRAY

        try:
            start_kwargs = {
                "config": config_str,
                "backend_type": type,
                "users": users,
                "keep_alive": db_node.keep_alive,
            }
            if core.type == CoreType.xray:
                start_kwargs["exclude_inbounds"] = core.exclude_inbound_tags

            info = await pg_node.start(**start_kwargs)
            logger.info(f'Connected to "{db_node.name}" node v{info.node_version}, core run on v{info.core_version}')

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

    async def _connect_single_node_background(self, node_id: int) -> None:
        try:
            async with GetDB() as db:
                await self._connect_single_impl(db, node_id)
        except Exception as exc:
            logger.error(f"Background node connection failed for node {node_id}: {exc}")

    async def create_node(self, db: AsyncSession, new_node: NodeCreate, admin: AdminDetails) -> NodeResponse:
        await self.get_validated_core_config(db, new_node.core_config_id)
        try:
            db_node = await create_node(db, new_node)
        except IntegrityError:
            await self.raise_error(message=f'Node "{new_node.name}" already exists', code=409, db=db)

        try:
            await self._update_node_impl(db_node)
            asyncio.create_task(self._connect_single_node_background(db_node.id))
        except NodeAPIError as e:
            await self._update_single_node_status(db, db_node.id, NodeStatus.error, message=e.detail)

        logger.info(f'New node "{db_node.name}" with id "{db_node.id}" added by admin "{admin.username}"')

        node = NodeResponse.model_validate(db_node)
        asyncio.create_task(notification.create_node(node, admin.username))

        return node

    async def modify_node(self, db: AsyncSession, node_id: int, modified_node: NodeModify, admin: AdminDetails) -> Node:
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
                asyncio.create_task(self._connect_single_node_background(db_node.id))
            except NodeAPIError as e:
                await self._update_single_node_status(db, db_node.id, NodeStatus.error, message=e.detail)

        logger.info(f'Node "{db_node.name}" with id "{db_node.id}" modified by admin "{admin.username}"')

        node = NodeResponse.model_validate(db_node)
        asyncio.create_task(notification.modify_node(node, admin.username))

        return node

    async def remove_node(self, db: AsyncSession, node_id: int, admin: AdminDetails) -> None:
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
        was_limited = db_node.status == NodeStatus.limited

        # Store old values for notification
        old_uplink = db_node.uplink
        old_downlink = db_node.downlink

        # Reset usage (creates log entry and sets uplink/downlink to 0)
        db_node = await reset_node_usage(db, db_node)

        if was_limited:
            await self.connect_single_node(db, db_node.id)
            db_node = await self.get_validated_node(db=db, node_id=node_id)

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

    async def restart_node(self, db: AsyncSession, node_id: int, admin: AdminDetails) -> None:
        await self.connect_single_node(db, node_id)
        logger.info(f'Node "{node_id}" restarted by admin "{admin.username}"')

    async def restart_all_node(self, db: AsyncSession, admin: AdminDetails, core_id: int | None = None) -> None:
        await self._restart_all_impl(db, admin, core_id)
        logger.info(f'All nodes restarted by admin "{admin.username}"')

    async def get_usage(
        self,
        db: AsyncSession,
        query: NodeUsageQuery,
    ) -> NodeUsageStatsList:
        start, end = await self.validate_dates(query.start, query.end, True)
        return await get_nodes_usage(
            db,
            start,
            end,
            period=query.period,
            node_id=query.node_id,
            group_by_node=query.group_by_node,
        )

    async def get_user_count_metric(
        self,
        db: AsyncSession,
        metric: UserCountMetric,
        query: NodeUsageQuery,
    ) -> UserCountMetricStatsList:
        start, end = await self.validate_dates(query.start, query.end, True)
        try:
            validate_user_count_metric_scope(metric, node_id=query.node_id, group_by_node=query.group_by_node)
        except ValueError as exc:
            await self.raise_error(message=str(exc), code=400)

        return await get_user_count_metric_stats(
            db,
            admins=None,
            start=start,
            end=end,
            period=query.period,
            metric=metric,
            node_id=query.node_id,
            group_by_node=query.group_by_node,
        )

    async def get_logs(self, node_id: int) -> Callable[[], AsyncIterator[asyncio.Queue]]:
        return await self._get_logs_impl(node_id)

    async def get_node_stats_periodic(
        self, db: AsyncSession, node_id: int, query: NodeStatsPeriodQuery
    ) -> NodeStatsList:
        start, end = await self.validate_dates(query.start, query.end, True)

        return await get_node_stats(db, node_id, start, end, period=query.period)

    async def get_node_system_stats(self, node_id: int) -> NodeRealtimeStats:
        return await self._get_node_stats_impl(node_id)

    async def get_nodes_system_stats(self) -> dict[int, NodeRealtimeStats | None]:
        return await self._get_nodes_stats_impl()

    async def get_outbounds_latency(
        self, node_id: int, name: str = "", timeout: int | None = None
    ) -> NodeOutboundsLatencyResponse:
        return await self._get_outbounds_latency_impl(node_id, name, timeout)

    async def _get_node_stats_safe(self, node_id: int) -> NodeRealtimeStats | None:
        """Wrapper method that returns None instead of raising exceptions"""
        try:
            return await self.get_node_system_stats(node_id)
        except Exception as e:
            logger.error(f"Error getting system stats for node {node_id}: {e}")
            return None

    async def get_user_online_stats_by_node(self, db: AsyncSession, node_id: int, user_id: int) -> dict[int, int]:
        return await self._get_user_online_stats_impl(db, node_id, user_id)

    async def get_user_ip_list_by_node(self, db: AsyncSession, node_id: int, user_id: int) -> UserIPList:
        return await self._get_user_ip_list_impl(db, node_id, user_id)

    async def get_user_ip_list_all_nodes(self, db: AsyncSession, user_id: int) -> UserIPListAll:
        return await self._get_user_ip_list_all_impl(db, user_id)

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

    async def clear_usage_data(self, db: AsyncSession, table: UsageTable, query: NodeClearUsageQuery):
        if query.start and query.end and query.start >= query.end:
            await self.raise_error(code=400, message="Start time must be before end time.")

        try:
            await clear_usage_data(db, table, query.start, query.end)
            return {"detail": f"All data from '{table}' has been deleted successfully."}
        except Exception as e:
            await self.raise_error(code=400, message=f"Deletion failed due to server error: {str(e)}")

    async def update_node(self, db: AsyncSession, node_id: int) -> dict:
        await self.get_validated_node(db, node_id)
        return await self._update_node_api_impl(node_id)

    async def update_core(self, db: AsyncSession, node_id: int, node_core_update: NodeCoreUpdate) -> dict:
        db_node = await self.get_validated_node(db, node_id)

        current = db_node.xray_version
        target = node_core_update.core_version
        if current and not is_new_xray(current) and is_new_xray(target) and not node_core_update.confirm:
            raise HTTPException(
                status_code=400,
                detail="Upgrading to Xray 26.6.22+ renames xhttp session parameters (breaking change). Set confirm=true to proceed.",
            )

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

        core_ids = {node.core_config_id or 1 for node in nodes}
        cores_by_id, users_by_core = await self._get_core_users_map(db, core_ids)

        async def connect_single(node: Node) -> dict | None:
            if node is None or node.status in (NodeStatus.disabled, NodeStatus.limited):
                return

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

            core_id = node.core_config_id or 1
            return await self.connect_node(node, cores_by_id.get(core_id), users_by_core.get(core_id, []))

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

        core_id = db_node.core_config_id or 1
        cores_by_id, users_by_core = await self._get_core_users_map(db, {core_id})
        core = cores_by_id.get(core_id)
        users = users_by_core.get(core_id, [])

        # Update node manager
        try:
            await node_manager.update_node(db_node)
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
        result = await NodeOperation.connect_node(db_node, core, users)

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
        nodes, _ = await get_nodes(
            db,
            query=NodeListQuery(
                core_id=core_id,
                status=[NodeStatus.connected, NodeStatus.connecting, NodeStatus.error],
            ),
        )
        await self.connect_nodes_bulk(db, nodes)

    async def _restart_all_nodes_remote(self, db: AsyncSession, admin: AdminDetails, core_id: int | None) -> None:
        await node_nats_client.publish("connect_nodes_bulk", {"core_id": core_id})

    async def _get_logs_local(self, node_id: int) -> Callable[[], AsyncIterator[asyncio.Queue]]:
        node = await node_manager.get_node(node_id)
        if node is None:
            await self.raise_error(message="Node not found", code=404)
        return node.stream_logs

    async def _get_logs_remote(self, node_id: int) -> Callable[[], AsyncIterator[asyncio.Queue]]:
        await self.raise_error(message="Node logs are only available via node-worker", code=409)

    async def _get_node_system_stats_local(self, node_id: int) -> NodeRealtimeStats:
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
            uptime=stats.uptime,
        )

    async def _get_node_system_stats_remote(self, node_id: int) -> NodeRealtimeStats:
        try:
            data = await node_nats_client.request("get_node_system_stats", {"node_id": node_id})
            return NodeRealtimeStats.model_validate(data)
        except RuntimeError as exc:
            await self.handle_rpc_error(exc)

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
        try:
            data = await node_nats_client.request("get_nodes_system_stats", {})
            return {
                int(node_id): (NodeRealtimeStats.model_validate(value) if value else None)
                for node_id, value in data.items()
            }
        except RuntimeError as exc:
            await self.handle_rpc_error(exc)

    async def _get_outbounds_latency_local(
        self, node_id: int, name: str = "", timeout: int | None = None
    ) -> NodeOutboundsLatencyResponse:
        node = await node_manager.get_node(node_id)

        if node is None:
            await self.raise_error(message="Node not found", code=404)

        try:
            latency = await node.get_outbounds_latency(name=name, timeout=timeout)
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)

        if latency is None:
            await self.raise_error(message="Latency not found", code=404)

        return NodeOutboundsLatencyResponse(
            latencies=[
                {
                    "name": item.name,
                    "alive": item.alive,
                    "delay": item.delay,
                    "link": item.link,
                    "last_seen_time": item.last_seen_time,
                    "last_try_time": item.last_try_time,
                    "source": item.source,
                }
                for item in latency.latencies
            ]
        )

    async def _get_outbounds_latency_remote(
        self, node_id: int, name: str = "", timeout: int | None = None
    ) -> NodeOutboundsLatencyResponse:
        try:
            data = await node_nats_client.request(
                "get_outbounds_latency",
                {"node_id": node_id, "name": name, "timeout": timeout},
                timeout=timeout,
            )
            return NodeOutboundsLatencyResponse.model_validate(data)
        except RuntimeError as exc:
            await self.handle_rpc_error(exc)

    async def _get_user_online_stats_local(self, db: AsyncSession, node_id: int, user_id: int) -> dict[int, int]:
        db_user = await get_user_by_id(db, user_id)
        if db_user is None:
            await self.raise_error(message="User not found", code=404)

        node = await node_manager.get_node(node_id)

        if node is None:
            await self.raise_error(message="Node not found", code=404)

        try:
            stats = await node.get_user_online_stats(email=f"{db_user.id}")
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)

        if stats is None:
            await self.raise_error(message="Stats not found", code=404)

        return {node_id: stats.value}

    async def _get_user_online_stats_remote(self, db: AsyncSession, node_id: int, user_id: int) -> dict[int, int]:
        try:
            return await node_nats_client.request("get_user_online_stats", {"node_id": node_id, "user_id": user_id})
        except RuntimeError as exc:
            await self.handle_rpc_error(exc)

    async def _get_user_ip_list_local(self, db: AsyncSession, node_id: int, user_id: int) -> UserIPList:
        db_user = await get_user_by_id(db, user_id)
        if db_user is None:
            await self.raise_error(message="User not found", code=404)

        email = f"{db_user.id}"
        ips = await self._get_node_user_ip_list_safe(node_id, email)

        if ips is None:
            await self.raise_error(message="Node unavailable or user not found", code=404)

        return UserIPList(ips=ips)

    async def _get_user_ip_list_remote(self, db: AsyncSession, node_id: int, user_id: int) -> UserIPList:
        try:
            data = await node_nats_client.request("get_user_ip_list", {"node_id": node_id, "user_id": user_id})
            return UserIPList.model_validate(data)
        except RuntimeError as exc:
            await self.handle_rpc_error(exc)

    async def _get_user_ip_list_all_local(self, db: AsyncSession, user_id: int) -> UserIPListAll:
        db_user = await get_user_by_id(db, user_id)
        if db_user is None:
            await self.raise_error(message="User not found", code=404)

        nodes = await node_manager.get_healthy_nodes()
        email = f"{db_user.id}"

        ip_list_tasks = {id: asyncio.create_task(self._get_node_user_ip_list_safe(id, email)) for id, _ in nodes}

        await asyncio.gather(*ip_list_tasks.values(), return_exceptions=True)

        results = {}
        for node_id, task in ip_list_tasks.items():
            if task.exception() or task.result() is None:
                continue
            else:
                results[node_id] = UserIPList(ips=task.result())

        return UserIPListAll(nodes=results)

    async def _get_user_ip_list_all_remote(self, db: AsyncSession, user_id: int) -> UserIPListAll:
        try:
            data = await node_nats_client.request("get_user_ip_list_all", {"user_id": user_id})
            return UserIPListAll.model_validate(data)
        except RuntimeError as exc:
            await self.handle_rpc_error(exc)

    async def _sync_node_users_local(self, db: AsyncSession, node_id: int, flush_users: bool) -> NodeResponse:
        db_node = await self.get_validated_node(db, node_id=node_id)

        if db_node.status != NodeStatus.connected:
            await self.raise_error(message="Node is not connected", code=406)

        pg_node = await node_manager.get_node(node_id)
        if pg_node is None:
            await self.raise_error(message="Node is not connected", code=409)

        try:
            core_id = db_node.core_config_id or 1
            _, users_by_core = await self._get_core_users_map(db, {core_id})
            users = users_by_core.get(core_id, [])
            await pg_node.sync_users(users, flush_pending=flush_users)
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
        try:
            return await node_nats_client.request("update_node_api", {"node_id": node_id})
        except RuntimeError as exc:
            await self.handle_rpc_error(exc)

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

    async def bulk_remove_nodes(
        self, db: AsyncSession, bulk_nodes: BulkNodeSelection, admin: AdminDetails
    ) -> RemoveNodesResponse:
        """Remove multiple nodes by ID"""
        db_nodes = []
        for node_id in bulk_nodes.ids:
            db_node = await self.get_validated_node(db, node_id)
            db_nodes.append(db_node)

        node_ids = [n.id for n in db_nodes]
        node_names = [n.name for n in db_nodes]
        node_responses = [NodeResponse.model_validate(n) for n in db_nodes]

        # Remove nodes from RPC first
        for node_id in node_ids:
            await self._remove_node_impl(node_id)

        # Batch delete using CRUD function
        await remove_nodes(db, node_ids)

        # Notify
        for node_response in node_responses:
            logger.info(f'Node "{node_response.name}" with id "{node_response.id}" deleted by admin "{admin.username}"')
            asyncio.create_task(notification.remove_node(node_response, admin.username))

        return RemoveNodesResponse(nodes=node_names, count=len(db_nodes))

    async def _get_validated_nodes(self, db: AsyncSession, node_ids: list[int] | set[int]) -> list[Node]:
        if not node_ids:
            return []

        ids_list = list(node_ids)
        db_nodes, _ = await get_nodes(db, NodeListQuery(ids=ids_list, limit=len(ids_list)))

        found_ids = {n.id for n in db_nodes}
        missing = set(ids_list) - found_ids
        if missing:
            await self.raise_error(message="Node not found", code=404)

        return list(db_nodes)

    @staticmethod
    def _build_bulk_action_response(nodes: list[Node | NodeResponse]) -> BulkNodesActionResponse:
        names = [node.name for node in nodes]
        return BulkNodesActionResponse(nodes=names, count=len(names))

    @staticmethod
    def _build_node_modify_payload(node: Node) -> NodeModify:
        return NodeModify(
            name=node.name,
            address=node.address,
            port=node.port,
            api_port=node.api_port,
            usage_coefficient=node.usage_coefficient,
            connection_type=node.connection_type,
            server_ca=node.server_ca,
            keep_alive=node.keep_alive,
            core_config_id=node.core_config_id,
            api_key=node.api_key,
            data_limit=node.data_limit,
            data_limit_reset_strategy=node.data_limit_reset_strategy,
            reset_time=node.reset_time,
            default_timeout=node.default_timeout,
            internal_timeout=node.internal_timeout,
        )

    async def bulk_set_nodes_status(
        self,
        db: AsyncSession,
        bulk_nodes: BulkNodeSelection,
        admin: AdminDetails,
        *,
        status: NodeStatus,
    ) -> BulkNodesActionResponse:
        db_nodes = await self._get_validated_nodes(db, bulk_nodes.ids)
        nodes_to_update = [db_node for db_node in db_nodes if db_node.status != status]

        for db_node in nodes_to_update:
            payload = self._build_node_modify_payload(db_node)
            payload.status = status
            await self.modify_node(db, node_id=db_node.id, modified_node=payload, admin=admin)

        action = "enabled" if status != NodeStatus.disabled else "disabled"
        for db_node in nodes_to_update:
            logger.info(f'Node "{db_node.name}" bulk {action} by admin "{admin.username}"')

        return self._build_bulk_action_response(nodes_to_update)

    async def bulk_reset_nodes_usage(
        self, db: AsyncSession, bulk_nodes: BulkNodeSelection, admin: AdminDetails
    ) -> BulkNodesActionResponse:
        db_nodes = await self._get_validated_nodes(db, bulk_nodes.ids)
        old_usages = {node.id: (node.uplink, node.downlink) for node in db_nodes}
        limited_node_ids = {node.id for node in db_nodes if node.status == NodeStatus.limited}

        db_nodes = await bulk_reset_node_usage(db, db_nodes)

        for db_node in db_nodes:
            if db_node.id in limited_node_ids:
                await self.connect_single_node(db, db_node.id)
                db_node = await self.get_validated_node(db=db, node_id=db_node.id)

            node = NodeResponse.model_validate(db_node)
            old_uplink, old_downlink = old_usages[db_node.id]
            asyncio.create_task(notification.reset_node_usage(node, admin.username, old_uplink, old_downlink))
            logger.info(f'Node "{db_node.name}" usage reset by admin "{admin.username}"')

        return self._build_bulk_action_response(db_nodes)

    async def bulk_restart_nodes(
        self, db: AsyncSession, bulk_nodes: BulkNodeSelection, admin: AdminDetails
    ) -> BulkNodesActionResponse:
        db_nodes = await self._get_validated_nodes(db, bulk_nodes.ids)

        await self.connect_nodes_bulk(db, db_nodes)

        for db_node in db_nodes:
            logger.info(f'Node "{db_node.name}" restarted by admin "{admin.username}"')

        return self._build_bulk_action_response(db_nodes)

    async def bulk_update_nodes(
        self, db: AsyncSession, bulk_nodes: BulkNodeSelection, admin: AdminDetails
    ) -> BulkNodesActionResponse:
        db_nodes = await self._get_validated_nodes(db, bulk_nodes.ids)

        updated_nodes = []
        errors = []
        for db_node in db_nodes:
            try:
                await self.update_node(db, db_node.id)
            except HTTPException as exc:
                errors.append(exc)
                logger.warning(f'Node "{db_node.name}" bulk update failed by admin "{admin.username}": {exc}')
                continue

            updated_nodes.append(db_node)
            logger.info(f'Node "{db_node.name}" updated by admin "{admin.username}"')

        if not updated_nodes and errors:
            raise errors[0]

        return self._build_bulk_action_response(updated_nodes)

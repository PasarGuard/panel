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
from app.node import calculate_max_message_size, core_users, node_manager
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
    async def connect_node(
        db_node: Node,
        users: list,
        limit_enforcer_config: dict | None = None,
    ) -> dict | None:
        """
        Connect to a node and return status result (does NOT update database).

        Args:
            db_node (Node): Node object from database.
            users (list): Pre-fetched core users list.
            limit_enforcer_config (dict): Optional config for real-time limit enforcement.
                Keys: panel_api_url, limit_check_interval, limit_refresh_interval

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

        # Prepare limit enforcer parameters
        le_config = limit_enforcer_config or {}
        node_id = db_node.id if le_config.get("enabled") else 0
        panel_api_url = le_config.get("panel_api_url", "") if le_config.get("enabled") else ""
        limit_check_interval = le_config.get("limit_check_interval", 30)
        limit_refresh_interval = le_config.get("limit_refresh_interval", 60)

        try:
            info = await pg_node.start(
                config=core.to_str(),
                backend_type=0,
                users=users,
                keep_alive=db_node.keep_alive,
                exclude_inbounds=core.exclude_inbound_tags,
                node_id=node_id,
                panel_api_url=panel_api_url,
                limit_check_interval=limit_check_interval,
                limit_refresh_interval=limit_refresh_interval,
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

        # Calculate max_message_size based on active users count
        user_counts = await get_users_count_by_status(db, [UserStatus.active])
        active_users_count = user_counts.get(UserStatus.active.value, 0)
        max_message_size = calculate_max_message_size(active_users_count)

        try:
            await node_manager.update_node(db_node, max_message_size=max_message_size)
            asyncio.create_task(self.connect_single_node(db, db_node.id))
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

        # Track if user_data_limit is being changed
        old_user_data_limit = db_node.user_data_limit
        new_user_data_limit = modified_node.user_data_limit

        try:
            db_node = await modify_node(db, db_node, modified_node)
        except IntegrityError:
            await self.raise_error(message=f'Node "{db_node.name}" already exists', code=409, db=db)

        # If user_data_limit changed, update existing users without individual limits
        if new_user_data_limit is not None and new_user_data_limit != old_user_data_limit:
            await self._propagate_user_data_limit_change(
                db, db_node.id, new_user_data_limit,
                db_node.user_data_limit_reset_strategy,
                db_node.user_reset_time
            )
            # Refresh db_node after commit in propagate to avoid MissingGreenlet
            await db.refresh(db_node)

        if db_node.status in (NodeStatus.disabled, NodeStatus.limited):
            await self.disconnect_single_node(db_node.id)
        else:
            # Calculate max_message_size based on active users count
            user_counts = await get_users_count_by_status(db, [UserStatus.active])
            active_users_count = user_counts.get(UserStatus.active.value, 0)
            max_message_size = calculate_max_message_size(active_users_count)

            try:
                await node_manager.update_node(db_node, max_message_size=max_message_size)
                asyncio.create_task(self.connect_single_node(db, db_node.id))
            except NodeAPIError as e:
                await self._update_single_node_status(db, db_node.id, NodeStatus.error, message=e.detail)

        logger.info(f'Node "{db_node.name}" with id "{db_node.id}" modified by admin "{admin.username}"')

        node = NodeResponse.model_validate(db_node)

        asyncio.create_task(notification.modify_node(node, admin.username))

        return node

    async def _propagate_user_data_limit_change(
        self, db: AsyncSession, node_id: int, data_limit: int,
        reset_strategy, reset_time: int
    ):
        """
        Update node_user_limits for users without individual limits when Node.user_data_limit changes.
        Users with individual limits (set via user edit or templates) are not affected.
        """
        from app.db.crud import node_user_limit as node_limit_crud
        from app.db.models import User, NodeUserLimit
        from sqlalchemy import select
        
        # Ensure strategy is string
        if hasattr(reset_strategy, "value"):
            reset_strategy = reset_strategy.value
        
        # Get all active users
        users_stmt = select(User.id)
        users_result = await db.execute(users_stmt)
        all_user_ids = set(row[0] for row in users_result.fetchall())
        
        if not all_user_ids:
            return
        
        # Get users who already have limits for this node
        existing_limits = await node_limit_crud.get_user_limits_for_node(db, node_id)
        users_with_limits = {limit.user_id for limit in existing_limits}
        
        # Users without limits for this node get the new node default
        users_to_update = all_user_ids - users_with_limits
        
        if data_limit > 0:
            # Create new limits for users who don't have one
            for user_id in users_to_update:
                new_limit = NodeUserLimit(
                    user_id=user_id,
                    node_id=node_id,
                    data_limit=data_limit,
                    data_limit_reset_strategy=reset_strategy,
                    reset_time=reset_time
                )
                db.add(new_limit)
            
            await db.commit()
            
            logger.info(
                f"Propagated user_data_limit={data_limit} to {len(users_to_update)} users "
                f"without individual limits on node {node_id}"
            )

    async def remove_node(self, db: AsyncSession, node_id: Node, admin: AdminDetails) -> None:
        db_node: Node = await self.get_validated_node(db=db, node_id=node_id)
        node_response = NodeResponse.model_validate(db_node)

        await node_manager.remove_node(db_node.id)
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
        from app.db.crud.settings import get_settings
        from app.models.settings import General, Subscription

        if not nodes:
            return

        # Fetch users ONCE for all nodes (without node_id filtering, as it's bulk)
        # However, for per-node enforcement, they will be filtered later if needed.
        # But wait, connect_nodes_bulk connects multiple nodes. 
        # If we use a shared users list, we might include users over limit for some nodes but not others.
        # Actually, connect_nodes_bulk is usually for startup.
        # Let's keep it as is for bulk or handle it inside the loop.
        users = await core_users(db=db)

        # Calculate max_message_size based on active users count (once for all nodes)
        user_counts = await get_users_count_by_status(db, [UserStatus.active])
        active_users_count = user_counts.get(UserStatus.active.value, 0)
        max_message_size = calculate_max_message_size(active_users_count)

        # Get limit enforcer config from settings (once for all nodes)
        limit_enforcer_config = None
        try:
            settings = await get_settings(db)
            if settings and settings.general and settings.subscription:
                general = General.model_validate(settings.general)
                subscription = Subscription.model_validate(settings.subscription)
                if general.limit_enforcer_enabled and subscription.url_prefix:
                    limit_enforcer_config = {
                        "enabled": True,
                        "panel_api_url": subscription.url_prefix.rstrip("/"),
                        "limit_check_interval": general.limit_check_interval,
                        "limit_refresh_interval": general.limit_refresh_interval,
                    }
        except Exception as e:
            logger.warning(f"Failed to get limit enforcer config: {e}")

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

            # For bulk, we still want to filter per node
            node_users = await core_users(db=db, node_id=node.id)
            return await self.connect_node(node, node_users, limit_enforcer_config)

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

    async def connect_single_node(self, db: AsyncSession, node_id: int) -> None:
        """
        Connect a single node and update its status (optimized for single-node operations).

        Uses simple UPDATE statement instead of bulk update to avoid deadlock risks
        and unnecessary complexity.

        Args:
            db (AsyncSession): Database session.
            node_id (int): ID of the node to connect.
        """
        from app.db.crud.settings import get_settings
        from app.models.settings import General, Subscription

        db_node = await get_node_by_id(db, node_id)
        if db_node is None or db_node.status in (NodeStatus.disabled, NodeStatus.limited):
            return

        # Get users for this specific node with limit filtering
        users = await core_users(db=db, node_id=node_id)

        # Calculate max_message_size based on active users count
        user_counts = await get_users_count_by_status(db, [UserStatus.active])
        active_users_count = user_counts.get(UserStatus.active.value, 0)
        max_message_size = calculate_max_message_size(active_users_count)

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

        # Get limit enforcer config from settings
        limit_enforcer_config = None
        try:
            settings = await get_settings(db)
            if settings and settings.general and settings.subscription:
                general = General.model_validate(settings.general)
                subscription = Subscription.model_validate(settings.subscription)
                if general.limit_enforcer_enabled and subscription.url_prefix:
                    limit_enforcer_config = {
                        "enabled": True,
                        "panel_api_url": subscription.url_prefix.rstrip("/"),
                        "limit_check_interval": general.limit_check_interval,
                        "limit_refresh_interval": general.limit_refresh_interval,
                    }
        except Exception as e:
            logger.warning(f"Failed to get limit enforcer config: {e}")

        # Connect the node
        result = await NodeOperation.connect_node(db_node, users, limit_enforcer_config)

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

    async def disconnect_single_node(self, node_id: int) -> None:
        """
        Disconnect a single node from the node manager (stop it from running).

        Used when a node needs to be stopped (e.g., when limited or disabled).

        Args:
            node_id (int): ID of the node to disconnect.
        """
        await node_manager.remove_node(node_id)
        logger.info(f'Node "{node_id}" disconnected')

    async def restart_node(self, db: AsyncSession, node_id: Node, admin: AdminDetails) -> None:
        await self.connect_single_node(db, node_id)
        logger.info(f'Node "{node_id}" restarted by admin "{admin.username}"')

    async def restart_all_node(self, db: AsyncSession, admin: AdminDetails, core_id: int | None = None) -> None:
        nodes, _ = await get_nodes(db, core_id=core_id, enabled=True)
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
        start, end = await self.validate_dates(start, end, True)
        return await get_nodes_usage(db, start, end, period=period, node_id=node_id, group_by_node=group_by_node)

    async def get_logs(self, node_id: Node) -> Callable[[], AsyncIterator[asyncio.Queue]]:
        node = await node_manager.get_node(node_id)

        if node is None:
            await self.raise_error(message="Node not found", code=404)

        return node.stream_logs

    async def get_node_stats_periodic(
        self, db: AsyncSession, node_id: id, start: dt = None, end: dt = None, period: Period = Period.hour
    ) -> NodeStatsList:
        start, end = await self.validate_dates(start, end, True)

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

    async def get_user_ip_list_by_node(self, db: AsyncSession, node_id: Node, username: str) -> UserIPList:
        db_user = await get_user(db, username=username)
        if db_user is None:
            await self.raise_error(message="User not found", code=404)

        email = f"{db_user.id}.{db_user.username}"
        ips = await self._get_node_user_ip_list_safe(node_id, email)

        if ips is None:
            await self.raise_error(message="Node unavailable or user not found", code=404)

        return UserIPList(ips=ips)

    async def get_user_ip_list_all_nodes(self, db: AsyncSession, username: str) -> UserIPListAll:
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
        db_node = await self.get_validated_node(db, node_id=node_id)

        if db_node.status != NodeStatus.connected:
            await self.raise_error(message="Node is not connected", code=406)

        pg_node = await node_manager.get_node(node_id)
        if pg_node is None:
            await self.raise_error(message="Node is not connected", code=409)

        try:
            users = await core_users(db=db, node_id=node_id)
            await pg_node.sync_users(users, flush_pending=flush_users)
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

    async def update_node(self, db: AsyncSession, node_id: int) -> dict:
        await self.get_validated_node(db, node_id)
        node = await node_manager.get_node(node_id)
        if node is None:
            await self.raise_error(message="Node not found", code=404)
        try:
            response = await node.update_node()
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)
        return response.json()

    async def update_core(self, db: AsyncSession, node_id: int, node_core_update: NodeCoreUpdate) -> dict:
        await self.get_validated_node(db, node_id)
        node = await node_manager.get_node(node_id)
        if node is None:
            await self.raise_error(message="Node not found", code=404)
        try:
            response = await node.update_core(node_core_update.model_dump(mode="json"))
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)
        return response.json()

    async def update_geofiles(self, db: AsyncSession, node_id: int, node_geofiles_update: NodeGeoFilesUpdate) -> dict:
        await self.get_validated_node(db, node_id)
        node = await node_manager.get_node(node_id)
        if node is None:
            await self.raise_error(message="Node not found", code=404)
        try:
            response = await node.update_geofiles(node_geofiles_update.model_dump(mode="json"))
        except NodeAPIError as e:
            await self.raise_error(message=e.detail, code=e.code)
        return response.json()

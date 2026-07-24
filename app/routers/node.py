import asyncio
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from PasarGuardNodeBridge import NodeAPIError
from sse_starlette.sse import EventSourceResponse

from app.db import AsyncSession, GetDB, get_db
from app.db.models import NodeStatus
from app.models.admin import AdminDetails
from app.models.node import (
    BulkNodesActionResponse,
    BulkNodeSelection,
    NodeClearUsageQuery,
    NodeCoreUpdate,
    NodeCreate,
    NodeGeoFilesUpdate,
    NodeListQuery,
    NodeModify,
    NodeResponse,
    NodeSettings,
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
from app.operation import OperatorType
from app.operation.node import NodeOperation
from app.utils import responses
from app.utils.logger import get_logger
from config import runtime_settings

from .authentication import oauth2_scheme, require_permission, require_permission_for_request
from .dependencies import (
    get_node_clear_usage_query,
    get_node_list_query,
    get_node_simple_list_query,
    get_node_stats_period_query,
    get_node_usage_query,
)

node_operator = NodeOperation(operator_type=OperatorType.API)
logger = get_logger("node-router")
router = APIRouter(tags=["Node"], prefix="/api/node", responses={401: responses._401, 403: responses._403})


async def _node_logs_local(node_id: int, request: Request) -> EventSourceResponse:
    context_manager = await node_operator.get_logs(node_id=node_id)

    async def event_generator() -> AsyncGenerator[str]:
        try:
            async with context_manager() as log_queue:
                while True:
                    if await request.is_disconnected():
                        break

                    item = await log_queue.get()
                    # Check if we received an error
                    if isinstance(item, NodeAPIError):
                        raise item
                    # Process the log message
                    yield f"{item}"
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Failed to stream local node logs", extra={"node_id": node_id})

    return EventSourceResponse(event_generator())


async def _node_logs_remote(node_id: int, request: Request) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[str]:
        sub = None
        stop_subject = None
        nc = await node_nats_client.get_client()
        if not nc:
            yield "Error retrieving logs: NATS not available\n"
            return

        try:
            stream_info = await node_nats_client.request("start_logs", {"node_id": node_id})
            subject = stream_info.get("subject")
            stop_subject = stream_info.get("stop_subject")
            if not subject or not stop_subject:
                yield "Error retrieving logs: invalid stream response\n"
                return

            sub = await nc.subscribe(subject)

            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await sub.next_msg(timeout=1)
                except TimeoutError:
                    continue
                yield msg.data.decode()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Failed to stream remote node logs", extra={"node_id": node_id})
        finally:
            if stop_subject:
                try:
                    await nc.publish(stop_subject, b"stop")
                except Exception:
                    pass
            if sub:
                try:
                    await sub.unsubscribe()
                except Exception:
                    pass

    return EventSourceResponse(event_generator())


_node_logs_handler = _node_logs_local if runtime_settings.role.runs_node else _node_logs_remote


@router.get("/settings", response_model=NodeSettings)
async def get_node_settings(_: AdminDetails = Depends(require_permission("nodes", "read"))):
    """Retrieve the current node settings."""
    return NodeSettings()


@router.get("/usage", response_model=NodeUsageStatsList)
async def get_usage(
    query: Annotated[NodeUsageQuery, Depends(get_node_usage_query)],
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "stats")),
):
    """Retrieve usage statistics for nodes within a specified date range."""
    return await node_operator.get_usage(db=db, query=query)


@router.get("/user_counts/{metric}", response_model=UserCountMetricStatsList)
async def get_user_count_metric(
    metric: UserCountMetric,
    query: Annotated[NodeUsageQuery, Depends(get_node_usage_query)],
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "stats")),
):
    """Retrieve one user activity/status count metric from node user usage rows."""
    try:
        validate_user_count_metric_scope(metric, node_id=query.node_id, group_by_node=query.group_by_node)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return await node_operator.get_user_count_metric(db=db, metric=metric, query=query)


@router.get("s", response_model=NodesResponse)
async def get_nodes(
    query: Annotated[NodeListQuery, Depends(get_node_list_query)],
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "read")),
):
    """Retrieve a list of all nodes. Accessible only to authorized admins."""

    return await node_operator.get_db_nodes(db=db, query=query)


@router.get(
    "s/simple",
    response_model=NodesSimpleResponse,
    summary="Get lightweight node list",
    description="Returns only id and name for nodes. Optimized for dropdowns and autocomplete.",
)
async def get_nodes_simple(
    query: Annotated[NodeSimpleListQuery, Depends(get_node_simple_list_query)],
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "read_simple")),
):
    """Get lightweight node list with only id and name"""
    return await node_operator.get_nodes_simple(db=db, query=query)


@router.post("s/reconnect")
async def reconnect_all_node(
    core_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "reconnect")),
):
    """
    Trigger reconnection for all nodes or a specific core.
    """
    await node_operator.restart_all_node(db=db, admin=admin, core_id=core_id)
    return {}


@router.post(
    "",
    response_model=NodeResponse,
    responses={409: responses._409},
    status_code=status.HTTP_201_CREATED,
)
async def create_node(
    new_node: NodeCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "create")),
):
    """Create a new node to the database."""
    return await node_operator.create_node(db, new_node, admin)


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: int, db: AsyncSession = Depends(get_db), _: AdminDetails = Depends(require_permission("nodes", "read"))
):
    """Retrieve details of a specific node by its ID."""
    return await node_operator.get_validated_node(db=db, node_id=node_id)


@router.post("/{node_id}/update")
async def update_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "update_core")),
):
    return await node_operator.update_node(db=db, node_id=node_id)


@router.post("/{node_id}/core_update")
async def update_core(
    node_id: int,
    node_core_update: NodeCoreUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "update_core")),
):
    return await node_operator.update_core(db=db, node_id=node_id, node_core_update=node_core_update)


@router.post("/{node_id}/geofiles")
async def update_geofiles(
    node_id: int,
    node_geofiles_update: NodeGeoFilesUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "update_core")),
):
    return await node_operator.update_geofiles(db=db, node_id=node_id, node_geofiles_update=node_geofiles_update)


@router.put("/{node_id}", response_model=NodeResponse)
async def modify_node(
    modified_node: NodeModify,
    node_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "update")),
):
    """Modify a node's details. Only accessible to authorized admins."""
    return await node_operator.modify_node(db, node_id=node_id, modified_node=modified_node, admin=admin)


@router.post("/{node_id}/reset", response_model=NodeResponse)
async def reset_node_usage(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "update")),
):
    """
    Reset node traffic usage (uplink and downlink).
    Creates a log entry in node_usage_reset_logs table.
    Only accessible to authorized admins.
    """
    return await node_operator.reset_node_usage(db, node_id=node_id, admin=admin)


@router.post("/{node_id}/reconnect")
async def reconnect_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "reconnect")),
):
    """Trigger a reconnection for the specified node. Only accessible to authorized admins."""
    await node_operator.restart_node(db, node_id, admin)
    return {}


@router.put("/{node_id}/sync")
async def sync_node(
    node_id: int,
    flush_users: bool = True,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "update")),
):
    return await node_operator.sync_node_users(db, node_id=node_id, flush_users=flush_users)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "delete")),
):
    """Remove a node and remove it from xray in the background."""
    await node_operator.remove_node(db=db, node_id=node_id, admin=admin)
    return {}


@router.get("/{node_id}/logs")
async def node_logs(node_id: int, request: Request, token: str | None = Depends(oauth2_scheme)):
    """
    Stream logs for a specific node as Server-Sent Events.
    """
    async with GetDB() as db:
        await require_permission_for_request(request, db, token, "nodes", "logs")

    return await _node_logs_handler(node_id, request)


@router.get("/{node_id}/stats", response_model=NodeStatsList)
async def get_node_stats_periodic(
    node_id: int,
    query: Annotated[NodeStatsPeriodQuery, Depends(get_node_stats_period_query)],
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "stats")),
):
    return await node_operator.get_node_stats_periodic(db, node_id=node_id, query=query)


@router.get("/{node_id}/realtime_stats", response_model=NodeRealtimeStats)
async def realtime_node_stats(node_id: int, _: AdminDetails = Depends(require_permission("nodes", "stats"))):
    """Retrieve node real-time statistics."""
    return await node_operator.get_node_system_stats(node_id=node_id)


@router.get("/{node_id}/outbounds_latency", response_model=NodeOutboundsLatencyResponse)
async def node_outbounds_latency(
    node_id: int,
    name: str = "",
    timeout: int | None = None,
    _: AdminDetails = Depends(require_permission("nodes", "stats")),
):
    """Retrieve outbound latency for one outbound or all outbounds of a node."""
    return await node_operator.get_outbounds_latency(node_id=node_id, name=name, timeout=timeout)


@router.get("s/realtime_stats", response_model=dict[int, NodeRealtimeStats | None])
async def realtime_nodes_stats(_: AdminDetails = Depends(require_permission("nodes", "stats"))):
    """Retrieve nodes real-time statistics."""
    return await node_operator.get_nodes_system_stats()


@router.get("/online_stats/{user_id}/ip", response_model=UserIPListAll)
async def user_online_ip_list_all_nodes(
    user_id: int, db: AsyncSession = Depends(get_db), _: AdminDetails = Depends(require_permission("nodes", "stats"))
):
    """Retrieve user ips from all nodes."""
    return await node_operator.get_user_ip_list_all_nodes(db=db, user_id=user_id)


@router.get("/{node_id}/online_stats/{user_id}", response_model=dict[int, int])
async def user_online_stats(
    node_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "stats")),
):
    """Retrieve user online stats by node."""
    return await node_operator.get_user_online_stats_by_node(db=db, node_id=node_id, user_id=user_id)


@router.get("/{node_id}/online_stats/{user_id}/ip", response_model=UserIPList)
async def user_online_ip_list(
    node_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "stats")),
):
    """Retrieve user ips by node."""
    return await node_operator.get_user_ip_list_by_node(db=db, node_id=node_id, user_id=user_id)


@router.delete(
    "s/clear_usage_data/{table}",
    summary="Clear usage data from a specified table",
)
async def clear_usage_data(
    table: UsageTable,
    query: Annotated[NodeClearUsageQuery, Depends(get_node_clear_usage_query)],
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("nodes", "delete")),
):
    """
    Deletes **all rows** from the selected usage data table. Use with caution.

    Allowed tables:
        - `node_user_usages`: Deletes user-specific node usage traffic records.
        - `node_usages`: Deletes node-level aggregated traffic (uplink/downlink) records.

    **Optional filters:**
        - `start`: ISO 8601 timestamp to filter from (inclusive)
        - `end`: ISO 8601 timestamp to filter to (exclusive)

    ⚠️ This operation is irreversible. Ensure correct usage in production environments.
    """
    return await node_operator.clear_usage_data(db, table, query)


@router.post(
    "s/bulk/delete",
    response_model=RemoveNodesResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_delete_nodes(
    bulk_nodes: BulkNodeSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "delete")),
):
    """Delete selected nodes by ID."""
    return await node_operator.bulk_remove_nodes(db, bulk_nodes, admin)


@router.post(
    "s/bulk/disable",
    response_model=BulkNodesActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_disable_nodes(
    bulk_nodes: BulkNodeSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "update")),
):
    """Disable selected nodes by ID."""
    return await node_operator.bulk_set_nodes_status(db, bulk_nodes, admin, status=NodeStatus.disabled)


@router.post(
    "s/bulk/enable",
    response_model=BulkNodesActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_enable_nodes(
    bulk_nodes: BulkNodeSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "update")),
):
    """Enable selected nodes by ID."""
    return await node_operator.bulk_set_nodes_status(db, bulk_nodes, admin, status=NodeStatus.connected)


@router.post(
    "s/bulk/reset",
    response_model=BulkNodesActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_reset_nodes_usage(
    bulk_nodes: BulkNodeSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "update")),
):
    """Reset usage for selected nodes by ID."""
    return await node_operator.bulk_reset_nodes_usage(db, bulk_nodes, admin)


@router.post(
    "s/bulk/reconnect",
    response_model=BulkNodesActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_reconnect_nodes(
    bulk_nodes: BulkNodeSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "reconnect")),
):
    """Reconnect selected nodes by ID."""
    return await node_operator.bulk_restart_nodes(db, bulk_nodes, admin)


@router.post(
    "s/bulk/update",
    response_model=BulkNodesActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_update_nodes(
    bulk_nodes: BulkNodeSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("nodes", "update_core")),
):
    """Update selected nodes by ID."""
    return await node_operator.bulk_update_nodes(db, bulk_nodes, admin)

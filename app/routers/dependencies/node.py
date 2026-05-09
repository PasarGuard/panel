from datetime import datetime as dt

from fastapi import Query

from app.db.models import NodeStatus
from app.models.node import (
    NodeClearUsageQuery,
    NodeListQuery,
    NodeSimpleListQuery,
    NodeStatsPeriodQuery,
    NodeUsageQuery,
)
from app.models.stats import Period

from ._common import build_query


def get_node_usage_query(
    period: Period = Period.hour,
    node_id: int | None = None,
    group_by_node: bool = False,
    start: dt | None = Query(None, examples=["2024-01-01T00:00:00+03:30"]),
    end: dt | None = Query(None, examples=["2024-01-31T23:59:59+03:30"]),
) -> NodeUsageQuery:
    return build_query(
        NodeUsageQuery, period=period, node_id=node_id, group_by_node=group_by_node, start=start, end=end
    )


def get_node_stats_period_query(
    period: Period = Period.hour,
    start: dt | None = Query(None, examples=["2024-01-01T00:00:00+03:30"]),
    end: dt | None = Query(None, examples=["2024-01-31T23:59:59+03:30"]),
) -> NodeStatsPeriodQuery:
    return build_query(NodeStatsPeriodQuery, period=period, start=start, end=end)


def get_node_clear_usage_query(
    start: dt | None = Query(None),
    end: dt | None = Query(None),
) -> NodeClearUsageQuery:
    return build_query(NodeClearUsageQuery, start=start, end=end)


def get_node_list_query(
    core_id: int | None = None,
    offset: int | None = None,
    limit: int | None = None,
    status: list[NodeStatus] | None = Query(None),
    enabled: bool = False,
    ids: list[int] | None = Query(None),
    search: str | None = None,
) -> NodeListQuery:
    return build_query(
        NodeListQuery,
        core_id=core_id,
        offset=offset,
        limit=limit,
        status=status,
        enabled=enabled,
        ids=ids,
        search=search,
    )


def get_node_simple_list_query(
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: str | None = None,
    all: bool = False,
) -> NodeSimpleListQuery:
    return build_query(NodeSimpleListQuery, offset=offset, limit=limit, search=search, sort=sort, all=all)

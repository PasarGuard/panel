from fastapi import Query

from app.models.node import (
    NodeClearUsageQuery,
    NodeListQuery,
    NodeSimpleListQuery,
    NodeStatsPeriodQuery,
    NodeUsageQuery,
)

from ._common import make_query_dependency, query_param


get_node_usage_query = make_query_dependency(
    NodeUsageQuery,
    field_overrides={
        "start": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "end": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    },
)
get_node_stats_period_query = make_query_dependency(
    NodeStatsPeriodQuery,
    field_overrides={
        "start": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "end": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    },
)
get_node_clear_usage_query = make_query_dependency(NodeClearUsageQuery)
get_node_list_query = make_query_dependency(
    NodeListQuery,
    field_overrides={
        "status": Query(None),
        "ids": Query(None),
    },
)
get_node_simple_list_query = make_query_dependency(
    NodeSimpleListQuery,
    field_overrides={"sort": query_param(str | None, None)},
)

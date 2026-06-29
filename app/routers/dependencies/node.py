from fastapi import Query

from app.models.node import (
    NodeClearUsageQuery,
    NodeListQuery,
    NodeSimpleListQuery,
    NodeStatsPeriodQuery,
    NodeUsageQuery,
)
from app.models.stats import Period

from ._common import make_query_dependency, query_param

get_node_usage_query = make_query_dependency(
    NodeUsageQuery,
    field_overrides={
        "period": Query(Period.hour),
        "node_id": Query(None),
        "start": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "end": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    },
)
get_node_stats_period_query = make_query_dependency(
    NodeStatsPeriodQuery,
    field_overrides={
        "period": Query(Period.hour),
        "start": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "end": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    },
)
get_node_clear_usage_query = make_query_dependency(
    NodeClearUsageQuery,
    field_overrides={
        "start": Query(None),
        "end": Query(None),
    },
)
get_node_list_query = make_query_dependency(
    NodeListQuery,
    field_overrides={
        "core_id": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "ids": Query(None),
        "status": Query(None),
        "enabled": Query(False),
        "search": Query(None),
    },
)
get_node_simple_list_query = make_query_dependency(
    NodeSimpleListQuery,
    field_overrides={
        "ids": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "search": Query(None),
        "sort": query_param(str | None, None),
        "all": Query(False),
    },
)

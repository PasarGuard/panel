from datetime import datetime as dt

from fastapi import Query

from app.models.admin import AdminListQuery, AdminSimpleListQuery, AdminUsageQuery
from app.models.stats import Period

from ._common import build_query


def get_admin_list_query(
    username: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
    sort: str | None = None,
) -> AdminListQuery:
    return build_query(AdminListQuery, username=username, offset=offset, limit=limit, sort=sort)


def get_admin_simple_list_query(
    search: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
    sort: str | None = None,
    all: bool = False,
) -> AdminSimpleListQuery:
    return build_query(AdminSimpleListQuery, search=search, offset=offset, limit=limit, sort=sort, all=all)


def get_admin_usage_query(
    period: Period,
    node_id: int | None = None,
    group_by_node: bool = False,
    start: dt | None = Query(None, examples=["2024-01-01T00:00:00+03:30"]),
    end: dt | None = Query(None, examples=["2024-01-31T23:59:59+03:30"]),
) -> AdminUsageQuery:
    return build_query(
        AdminUsageQuery, period=period, node_id=node_id, group_by_node=group_by_node, start=start, end=end
    )

from datetime import datetime as dt
from typing import Literal

from fastapi import Query

from app.db.models import UserStatus
from app.models.stats import Period
from app.models.user import ExpiredUsersQuery, UserListQuery, UserSimpleListQuery, UsersUsageQuery, UserUsageQuery

from ._common import build_query


def get_user_list_query(
    offset: int | None = None,
    limit: int | None = None,
    username: list[str] = Query(None),
    owner: list[str] | None = Query(None, alias="admin"),
    group_ids: list[int] | None = Query(None, alias="group"),
    search: str | None = None,
    status: UserStatus | None = None,
    sort: str | None = None,
    proxy_id: str | None = None,
    data_limit_min: int | None = Query(None, ge=0),
    data_limit_max: int | None = Query(None, ge=0),
    expire_after: dt | None = Query(None, examples=["2026-01-01T00:00:00+03:30"]),
    expire_before: dt | None = Query(None, examples=["2026-01-31T23:59:59+03:30"]),
    online_after: dt | None = Query(None, examples=["2026-01-01T00:00:00+03:30"]),
    online_before: dt | None = Query(None, examples=["2026-01-31T23:59:59+03:30"]),
    online: bool = False,
    no_data_limit: bool = False,
    no_expire: bool = False,
    load_sub: bool = False,
) -> UserListQuery:
    return build_query(
        UserListQuery,
        offset=offset,
        limit=limit,
        username=username,
        owner=owner,
        group_ids=group_ids,
        search=search,
        status=status,
        sort=sort,
        proxy_id=proxy_id,
        data_limit_min=data_limit_min,
        data_limit_max=data_limit_max,
        expire_after=expire_after,
        expire_before=expire_before,
        online_after=online_after,
        online_before=online_before,
        online=online,
        no_data_limit=no_data_limit,
        no_expire=no_expire,
        load_sub=load_sub,
    )


def get_user_simple_list_query(
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: str | None = None,
    all: bool = False,
) -> UserSimpleListQuery:
    return build_query(UserSimpleListQuery, offset=offset, limit=limit, search=search, sort=sort, all=all)


def get_user_usage_query(
    period: Period,
    node_id: int | None = None,
    group_by_node: bool = False,
    start: dt | None = Query(None, examples=["2024-01-01T00:00:00+03:30"]),
    end: dt | None = Query(None, examples=["2024-01-31T23:59:59+03:30"]),
) -> UserUsageQuery:
    return build_query(
        UserUsageQuery, period=period, node_id=node_id, group_by_node=group_by_node, start=start, end=end
    )


def get_users_usage_query(
    period: Period,
    node_id: int | None = None,
    group_by_node: bool = False,
    start: dt | None = Query(None, examples=["2024-01-01T00:00:00+03:30"]),
    end: dt | None = Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    owner: list[str] | None = Query(None, alias="admin"),
) -> UsersUsageQuery:
    return build_query(
        UsersUsageQuery,
        period=period,
        node_id=node_id,
        group_by_node=group_by_node,
        start=start,
        end=end,
        owner=owner,
    )


def get_expired_users_query(
    admin_username: str | None = None,
    target: Literal["expired", "limited"] = Query("expired"),
    expired_after: dt | None = Query(None, examples=["2024-01-01T00:00:00+03:30"]),
    expired_before: dt | None = Query(None, examples=["2024-01-31T23:59:59+03:30"]),
) -> ExpiredUsersQuery:
    return build_query(
        ExpiredUsersQuery,
        admin_username=admin_username,
        target=target,
        expired_after=expired_after,
        expired_before=expired_before,
    )

from fastapi import Query

from app.models.stats import Period
from app.models.user import ExpiredUsersQuery, UserListQuery, UserSimpleListQuery, UsersUsageQuery, UserUsageQuery

from ._common import make_query_dependency, query_param

get_user_list_query = make_query_dependency(
    UserListQuery,
    field_overrides={
        "offset": Query(None),
        "limit": Query(None),
        "ids": Query(None),
        "username": Query(None),
        "usernames": Query(None),
        "owner": Query(None, alias="admin"),
        "admin_ids": Query(None, alias="admin_ids"),
        "group_ids": Query(None, alias="group"),
        "status": Query(None),
        "sort": query_param(str | None, None),
        "proxy_id": Query(None),
        "data_limit_reset_strategy": Query(None, alias="data_limit_reset_strategy"),
        "data_limit_min": Query(None, ge=0),
        "data_limit_max": Query(None, ge=0),
        "expire_after": Query(None, examples=["2026-01-01T00:00:00+03:30"]),
        "expire_before": Query(None, examples=["2026-01-31T23:59:59+03:30"]),
        "online_after": Query(None, examples=["2026-01-01T00:00:00+03:30"]),
        "online_before": Query(None, examples=["2026-01-31T23:59:59+03:30"]),
        "online": Query(False),
        "no_data_limit": Query(False),
        "no_expire": Query(False),
        "load_sub": Query(False),
    },
)
get_user_simple_list_query = make_query_dependency(
    UserSimpleListQuery,
    field_overrides={
        "ids": Query(None),
        "usernames": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "search": Query(None),
        "sort": query_param(str | None, None),
        "all": Query(False),
    },
)
get_user_usage_query = make_query_dependency(
    UserUsageQuery,
    field_overrides={
        "period": Query(Period.hour),
        "node_id": Query(None),
        "group_by_node": Query(False),
        "start": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "end": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    },
)
get_users_usage_query = make_query_dependency(
    UsersUsageQuery,
    field_overrides={
        "period": Query(Period.hour),
        "node_id": Query(None),
        "group_by_node": Query(False),
        "start": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "end": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
        "owner": Query(None, alias="admin"),
    },
)
get_expired_users_query = make_query_dependency(
    ExpiredUsersQuery,
    field_overrides={
        "admin_username": Query(None),
        "target": Query("expired"),
        "expired_after": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "expired_before": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    },
)

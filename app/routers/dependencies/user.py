from fastapi import Query

from app.models.user import ExpiredUsersQuery, UserListQuery, UserSimpleListQuery, UsersUsageQuery, UserUsageQuery

from ._common import make_query_dependency, query_param


get_user_list_query = make_query_dependency(
    UserListQuery,
    field_overrides={
        "username": Query(None),
        "owner": Query(None, alias="admin"),
        "group_ids": Query(None, alias="group"),
        "data_limit_min": Query(None, ge=0),
        "data_limit_max": Query(None, ge=0),
        "expire_after": Query(None, examples=["2026-01-01T00:00:00+03:30"]),
        "expire_before": Query(None, examples=["2026-01-31T23:59:59+03:30"]),
        "online_after": Query(None, examples=["2026-01-01T00:00:00+03:30"]),
        "online_before": Query(None, examples=["2026-01-31T23:59:59+03:30"]),
    },
)
get_user_simple_list_query = make_query_dependency(
    UserSimpleListQuery,
    field_overrides={"sort": query_param(str | None, None)},
)
get_user_usage_query = make_query_dependency(
    UserUsageQuery,
    field_overrides={
        "start": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "end": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    },
)
get_users_usage_query = make_query_dependency(
    UsersUsageQuery,
    field_overrides={
        "start": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "end": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
        "owner": Query(None, alias="admin"),
    },
)
get_expired_users_query = make_query_dependency(
    ExpiredUsersQuery,
    field_overrides={
        "target": Query("expired"),
        "expired_after": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "expired_before": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    },
)

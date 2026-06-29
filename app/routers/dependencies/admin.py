from fastapi import Query

from app.models.admin import AdminListQuery, AdminSimpleListQuery, AdminUsageQuery

from ._common import make_query_dependency, query_param

get_admin_list_query = make_query_dependency(
    AdminListQuery,
    field_overrides={
        "ids": Query(None),
        "usernames": Query(None),
        "username": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "sort": query_param(str | None, None),
    },
)
get_admin_simple_list_query = make_query_dependency(
    AdminSimpleListQuery,
    field_overrides={
        "ids": Query(None),
        "usernames": Query(None),
        "search": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "sort": query_param(str | None, None),
        "all": Query(False),
    },
)
get_admin_usage_query = make_query_dependency(
    AdminUsageQuery,
    field_overrides={
        "start": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "end": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    },
)

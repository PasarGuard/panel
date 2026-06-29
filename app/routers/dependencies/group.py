from fastapi import Query

from app.models.group import GroupListQuery, GroupSimpleListQuery

from ._common import make_query_dependency, query_param

get_group_list_query = make_query_dependency(
    GroupListQuery,
    field_overrides={
        "ids": Query(None),
        "offset": Query(None),
        "limit": Query(None),
    },
)
get_group_simple_list_query = make_query_dependency(
    GroupSimpleListQuery,
    field_overrides={
        "ids": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "search": Query(None),
        "sort": query_param(str | None, None),
        "all": Query(False),
    },
)

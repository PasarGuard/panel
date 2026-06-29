from fastapi import Query

from app.models.core import CoreListQuery, CoreSimpleListQuery

from ._common import make_query_dependency, query_param

get_core_list_query = make_query_dependency(
    CoreListQuery,
    field_overrides={
        "ids": Query(None),
        "offset": Query(None),
        "limit": Query(None),
    },
)
get_core_simple_list_query = make_query_dependency(
    CoreSimpleListQuery,
    field_overrides={
        "ids": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "search": Query(None),
        "sort": query_param(str | None, None),
        "all": Query(False),
    },
)

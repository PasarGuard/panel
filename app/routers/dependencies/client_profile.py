from fastapi import Query

from app.models.client_profile import ClientProfileListQuery, ClientProfileSimpleListQuery

from ._common import make_query_dependency, query_param

get_client_profile_list_query = make_query_dependency(
    ClientProfileListQuery,
    field_overrides={
        "ids": Query(None),
        "search": Query(None),
        "offset": Query(None),
        "limit": Query(None),
    },
)
get_client_profile_simple_list_query = make_query_dependency(
    ClientProfileSimpleListQuery,
    field_overrides={
        "ids": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "search": Query(None),
        "sort": query_param(str | None, None),
        "all": Query(False),
    },
)

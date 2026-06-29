from fastapi import Query

from app.models.host import HostListQuery

from ._common import make_query_dependency

get_host_list_query = make_query_dependency(
    HostListQuery,
    field_overrides={
        "ids": Query(None),
        "offset": Query(0),
        "limit": Query(0),
    },
)

from fastapi import Query

from app.models.api_key import APIKeysQuery

from ._common import make_query_dependency

get_api_key_list_query = make_query_dependency(
    APIKeysQuery,
    field_overrides={
        "offset": Query(None),
        "limit": Query(None),
        "key_id": Query(None),
        "name": Query(None),
        "status": Query(None),
    },
)

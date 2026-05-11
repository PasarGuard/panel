from fastapi import Query

from app.models.client_template import ClientTemplateListQuery, ClientTemplateSimpleListQuery

from ._common import make_query_dependency, query_param

get_client_template_list_query = make_query_dependency(
    ClientTemplateListQuery,
    field_overrides={
        "ids": Query(None),
        "template_type": Query(None),
        "offset": Query(None),
        "limit": Query(None),
    },
)
get_client_template_simple_list_query = make_query_dependency(
    ClientTemplateSimpleListQuery,
    field_overrides={
        "ids": Query(None),
        "template_type": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "search": Query(None),
        "sort": query_param(str | None, None),
        "all": Query(False),
    },
)

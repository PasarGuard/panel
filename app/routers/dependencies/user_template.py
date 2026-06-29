from fastapi import Query

from app.models.user_template import UserTemplateListQuery, UserTemplateSimpleListQuery

from ._common import make_query_dependency, query_param

get_user_template_list_query = make_query_dependency(
    UserTemplateListQuery,
    field_overrides={
        "ids": Query(None),
        "offset": Query(None),
        "limit": Query(None),
    },
)
get_user_template_simple_list_query = make_query_dependency(
    UserTemplateSimpleListQuery,
    field_overrides={
        "ids": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "search": Query(None),
        "sort": query_param(str | None, None),
        "all": Query(False),
    },
)

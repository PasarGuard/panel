from fastapi import Query

from app.models.admin_role import AdminRoleListQuery

from ._common import make_query_dependency, query_param

get_admin_role_list_query = make_query_dependency(
    AdminRoleListQuery,
    field_overrides={
        "search": Query(None),
        "offset": Query(None),
        "limit": Query(None),
        "sort": query_param(str | None, None),
    },
)

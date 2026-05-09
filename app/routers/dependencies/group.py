from app.models.group import GroupListQuery, GroupSimpleListQuery

from ._common import make_query_dependency, query_param


get_group_list_query = make_query_dependency(GroupListQuery)
get_group_simple_list_query = make_query_dependency(
    GroupSimpleListQuery,
    field_overrides={"sort": query_param(str | None, None)},
)

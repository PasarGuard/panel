from app.models.core import CoreListQuery, CoreSimpleListQuery

from ._common import make_query_dependency, query_param


get_core_list_query = make_query_dependency(CoreListQuery)
get_core_simple_list_query = make_query_dependency(
    CoreSimpleListQuery,
    field_overrides={"sort": query_param(str | None, None)},
)

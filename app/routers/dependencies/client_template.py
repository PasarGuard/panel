from app.models.client_template import ClientTemplateListQuery, ClientTemplateSimpleListQuery

from ._common import make_query_dependency, query_param


get_client_template_list_query = make_query_dependency(ClientTemplateListQuery)
get_client_template_simple_list_query = make_query_dependency(
    ClientTemplateSimpleListQuery,
    field_overrides={"sort": query_param(str | None, None)},
)

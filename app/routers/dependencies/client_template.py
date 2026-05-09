from app.models.client_template import ClientTemplateListQuery, ClientTemplateSimpleListQuery, ClientTemplateType

from ._common import build_query


def get_client_template_list_query(
    template_type: ClientTemplateType | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> ClientTemplateListQuery:
    return build_query(ClientTemplateListQuery, template_type=template_type, offset=offset, limit=limit)


def get_client_template_simple_list_query(
    template_type: ClientTemplateType | None = None,
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: str | None = None,
    all: bool = False,
) -> ClientTemplateSimpleListQuery:
    return build_query(
        ClientTemplateSimpleListQuery,
        template_type=template_type,
        offset=offset,
        limit=limit,
        search=search,
        sort=sort,
        all=all,
    )

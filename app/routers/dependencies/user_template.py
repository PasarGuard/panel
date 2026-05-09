from app.models.user_template import UserTemplateListQuery, UserTemplateSimpleListQuery

from ._common import build_query


def get_user_template_list_query(offset: int | None = None, limit: int | None = None) -> UserTemplateListQuery:
    return build_query(UserTemplateListQuery, offset=offset, limit=limit)


def get_user_template_simple_list_query(
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: str | None = None,
    all: bool = False,
) -> UserTemplateSimpleListQuery:
    return build_query(UserTemplateSimpleListQuery, offset=offset, limit=limit, search=search, sort=sort, all=all)

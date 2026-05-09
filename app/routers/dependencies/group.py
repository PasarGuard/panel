from app.models.group import GroupListQuery, GroupSimpleListQuery

from ._common import build_query


def get_group_list_query(offset: int | None = None, limit: int | None = None) -> GroupListQuery:
    return build_query(GroupListQuery, offset=offset, limit=limit)


def get_group_simple_list_query(
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: str | None = None,
    all: bool = False,
) -> GroupSimpleListQuery:
    return build_query(GroupSimpleListQuery, offset=offset, limit=limit, search=search, sort=sort, all=all)

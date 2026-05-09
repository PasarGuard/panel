from app.models.core import CoreListQuery, CoreSimpleListQuery

from ._common import build_query


def get_core_list_query(offset: int | None = None, limit: int | None = None) -> CoreListQuery:
    return build_query(CoreListQuery, offset=offset, limit=limit)


def get_core_simple_list_query(
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: str | None = None,
    all: bool = False,
) -> CoreSimpleListQuery:
    return build_query(CoreSimpleListQuery, offset=offset, limit=limit, search=search, sort=sort, all=all)

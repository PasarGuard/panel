from app.models.host import HostListQuery

from ._common import build_query


def get_host_list_query(offset: int = 0, limit: int = 0) -> HostListQuery:
    return build_query(HostListQuery, offset=offset, limit=limit)

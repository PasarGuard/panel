from app.models.host import HostListQuery

from ._common import make_query_dependency


get_host_list_query = make_query_dependency(HostListQuery)

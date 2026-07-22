from fastapi import Query

from app.models.stats import Period
from app.models.subscription import SubscriptionHeaders, SubscriptionUsageQuery

from ._common import make_header_dependency, make_query_dependency

get_subscription_usage_query = make_query_dependency(
    SubscriptionUsageQuery,
    field_overrides={
        "period": Query(Period.hour),
        "start": Query(None, examples=["2024-01-01T00:00:00+03:30"]),
        "end": Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    },
)

get_subscription_headers = make_header_dependency(SubscriptionHeaders)

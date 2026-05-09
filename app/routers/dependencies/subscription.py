from datetime import datetime as dt

from fastapi import Query

from app.models.stats import Period
from app.models.subscription import SubscriptionUsageQuery

from ._common import build_query


def get_subscription_usage_query(
    start: dt | None = Query(None, examples=["2024-01-01T00:00:00+03:30"]),
    end: dt | None = Query(None, examples=["2024-01-31T23:59:59+03:30"]),
    period: Period = Period.hour,
) -> SubscriptionUsageQuery:
    return build_query(SubscriptionUsageQuery, start=start, end=end, period=period)

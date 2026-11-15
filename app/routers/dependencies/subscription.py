from fastapi import Query

from app.models.stats import Period
from app.models.subscription import SubscriptionHeaders, SubscriptionUsageQuery
from app.settings import hwid_settings, subscription_settings
from app.subscription.client_templates import subscription_client_templates, subscription_xray_templates
from app.utils.jwt import get_secret_key

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


async def warm_subscription_caches() -> None:
    """Load what /sub reads from cache before the request takes a pooled connection.

    The handlers read these after their first query; a cold-cache load there needs
    a second connection from the same pool while the first is held.
    """
    await subscription_settings()
    await hwid_settings()
    await get_secret_key()
    await subscription_client_templates()
    await subscription_xray_templates()

"""Stats endpoints reject ranges that would return more than MAX_USAGE_BUCKETS period buckets."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status

from app.models.stats import (
    MAX_USAGE_BUCKETS,
    USAGE_RECORD_GRANULARITY,
    Period,
    count_period_buckets,
)
from tests.api import client, engine
from tests.api.helpers import auth_headers, create_admin, create_user, delete_admin, delete_user

# A window far from the rows other tests write, so the passing requests stay cheap
END = datetime(2032, 6, 1, tzinfo=UTC)
TOO_LONG = {"period": "minute", "start": (END - timedelta(days=60)).isoformat(), "end": END.isoformat()}
NORMAL = {"period": "hour", "start": (END - timedelta(days=7)).isoformat(), "end": END.isoformat()}


def test_count_period_buckets_uses_wider_of_period_and_granularity():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=1)
    assert count_period_buckets(start, end, Period.minute) == 1440
    assert count_period_buckets(start, end, Period.minute, USAGE_RECORD_GRANULARITY) == 144
    assert count_period_buckets(start, end, Period.hour, USAGE_RECORD_GRANULARITY) == 24
    assert count_period_buckets(start, end, Period.day) == 1
    assert count_period_buckets(start, start, Period.minute) == 1


def test_count_period_buckets_limit_edge():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    # 10 minute usage rows: 5000 buckets is a little under 35 days
    assert count_period_buckets(start, start + timedelta(days=34), Period.minute, USAGE_RECORD_GRANULARITY) <= (
        MAX_USAGE_BUCKETS
    )
    assert count_period_buckets(start, start + timedelta(days=35), Period.minute, USAGE_RECORD_GRANULARITY) > (
        MAX_USAGE_BUCKETS
    )


def test_day_and_month_buckets_are_not_limited(access_token):
    # The dashboard's "all time" range starts in 2000 and uses day buckets
    all_time = {"start": datetime(2000, 1, 1, tzinfo=UTC).isoformat(), "end": END.isoformat()}
    for period in ("day", "month"):
        response = client.get(
            "/api/node/usage", headers=auth_headers(access_token), params={**all_time, "period": period}
        )
        assert response.status_code == status.HTTP_200_OK, response.text
    # Hour buckets over the same range are rejected
    response = client.get("/api/node/usage", headers=auth_headers(access_token), params={**all_time, "period": "hour"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text


def _assert_rejected(response):
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text
    detail = response.json()["detail"]
    assert "Range too long for period 'minute'" in detail
    assert str(MAX_USAGE_BUCKETS) in detail


ADMIN_PATHS = [
    "/api/node/usage",
    "/api/node/user_counts/online",
    "/api/node/999999/stats",
    "/api/users/usage",
    "/api/users/counts/online",
    "/api/users/sub_update/chart",
]


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_stats_endpoint_rejects_too_many_buckets(access_token, path):
    _assert_rejected(client.get(path, headers=auth_headers(access_token), params=TOO_LONG))


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_stats_endpoint_accepts_normal_range(access_token, path):
    if path.endswith("/stats") and engine.dialect.name in {"mysql", "mariadb"}:
        # Node system stats are only recorded on PostgreSQL, and their query does not run on MySQL
        pytest.skip("node stats are PostgreSQL only")
    response = client.get(path, headers=auth_headers(access_token), params=NORMAL)
    assert response.status_code == status.HTTP_200_OK, response.text


def test_minute_buckets_on_raw_rows_use_one_minute_width(access_token):
    # Node system stats are stored every few seconds, so a week of minute buckets is too many,
    # while usage history (10 minute rows) allows it
    week_of_minutes = {"period": "minute", "start": (END - timedelta(days=7)).isoformat(), "end": END.isoformat()}
    _assert_rejected(client.get("/api/node/999999/stats", headers=auth_headers(access_token), params=week_of_minutes))
    response = client.get("/api/node/usage", headers=auth_headers(access_token), params=week_of_minutes)
    assert response.status_code == status.HTTP_200_OK, response.text


def test_user_usage_bucket_limit(access_token):
    user = create_user(access_token)
    try:
        for path in (f"/api/user/by-id/{user['id']}/usage", f"/api/user/by-username/{user['username']}/usage"):
            _assert_rejected(client.get(path, headers=auth_headers(access_token), params=TOO_LONG))
            response = client.get(path, headers=auth_headers(access_token), params=NORMAL)
            assert response.status_code == status.HTTP_200_OK, response.text

        sub_usage = f"{user['subscription_url']}/usage"
        _assert_rejected(client.get(sub_usage, params=TOO_LONG))
        response = client.get(sub_usage, params=NORMAL)
        assert response.status_code == status.HTTP_200_OK, response.text
    finally:
        delete_user(access_token, user["username"])


def test_admin_usage_bucket_limit(access_token):
    admin = create_admin(access_token)
    try:
        for path in (f"/api/admin/by-id/{admin['id']}/usage", f"/api/admin/{admin['username']}/usage"):
            _assert_rejected(client.get(path, headers=auth_headers(access_token), params=TOO_LONG))
            response = client.get(path, headers=auth_headers(access_token), params=NORMAL)
            assert response.status_code == status.HTTP_200_OK, response.text
    finally:
        delete_admin(access_token, admin["username"])

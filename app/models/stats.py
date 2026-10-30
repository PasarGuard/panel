import math
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from .validators import AwareDatetime, NumericValidatorMixin


class Period(str, Enum):
    minute = "minute"
    hour = "hour"
    day = "day"
    month = "month"


# Upper limit for the number of period buckets one stats request may ask for.
# The dashboard stays far below it (about 500 per series); it only stops
# requests like a year of minute buckets.
MAX_USAGE_BUCKETS = 5000

# Periods the limit applies to. Day and month are not limited: "all time" asks for
# day buckets since 2000, and they can never outnumber the days of stored history.
BUCKET_LIMITED_PERIODS = frozenset({Period.minute, Period.hour})

# Shortest width of each period. Month uses 28 days so the count is an upper bound.
PERIOD_WIDTHS: dict[Period, timedelta] = {
    Period.minute: timedelta(minutes=1),
    Period.hour: timedelta(hours=1),
    Period.day: timedelta(days=1),
    Period.month: timedelta(days=28),
}

# Usage history rows (node usages, node user usages) are written in 10 minute
# buckets (see _get_time_bucket in app/jobs/record_usages.py), so a minute query
# on them returns at most one row per 10 minutes.
USAGE_RECORD_GRANULARITY = timedelta(minutes=10)


def count_period_buckets(
    start: datetime, end: datetime, period: Period, granularity: timedelta = timedelta(minutes=1)
) -> int:
    """Upper bound of the buckets a stats query returns for one series.

    `granularity` is how far apart the stored rows are; buckets narrower than
    that cannot all hold data, so the wider of the two decides the count.
    """
    span = (end - start).total_seconds()
    if span <= 0:
        return 1
    width = max(PERIOD_WIDTHS[period], granularity).total_seconds()
    return math.ceil(span / width)


class StatList(BaseModel):
    period: Period | None = None
    start: AwareDatetime
    end: AwareDatetime


class PeriodStartStat(BaseModel):
    period_start: AwareDatetime


class UserUsageStat(PeriodStartStat):
    total_traffic: int

    @field_validator("total_traffic", mode="before")
    def cast_to_int(cls, v):
        return NumericValidatorMixin.cast_to_int(v)


class UserUsageStatsList(StatList):
    stats: dict[int, list[UserUsageStat]]


class UserCountMetric(str, Enum):
    online = "online"
    expired = "expired"
    limited = "limited"


def validate_user_count_metric_scope(
    metric: UserCountMetric, node_id: int | None = None, group_by_node: bool = False
) -> None:
    if metric != UserCountMetric.online and (node_id is not None or group_by_node):
        raise ValueError("Only online user counts support node_id or group_by_node")


class UserCountMetricStat(PeriodStartStat):
    count: int

    @field_validator("count", mode="before")
    def cast_to_int(cls, v):
        return NumericValidatorMixin.cast_to_int(v)


class UserCountMetricStatsList(StatList):
    metric: UserCountMetric
    count_during_period: int = Field(default=0)
    stats: dict[int, list[UserCountMetricStat]]


class NodeUsageStat(PeriodStartStat):
    uplink: int
    downlink: int

    @field_validator("downlink", "uplink", mode="before")
    def cast_to_int(cls, v):
        return NumericValidatorMixin.cast_to_int(v)


class NodeUsageStatsList(StatList):
    stats: dict[int, list[NodeUsageStat]]


class NodeOutboundUsageStatsList(StatList):
    """Usage per outbound tag; the key is the tag."""

    stats: dict[str, list[NodeUsageStat]]


class NodeRealtimeStats(BaseModel):
    mem_total: int
    mem_used: int
    cpu_cores: int
    cpu_usage: float
    incoming_bandwidth_speed: int
    outgoing_bandwidth_speed: int
    uptime: int


class NodeOutboundLatency(BaseModel):
    name: str
    alive: bool
    delay: int
    link: str
    last_seen_time: int
    last_try_time: int
    source: str


class NodeOutboundsLatencyResponse(BaseModel):
    latencies: list[NodeOutboundLatency]


class NodeStats(PeriodStartStat):
    mem_usage_percentage: float
    cpu_usage_percentage: float
    incoming_bandwidth_speed: float
    outgoing_bandwidth_speed: float

    @field_validator(
        "mem_usage_percentage",
        "cpu_usage_percentage",
        "incoming_bandwidth_speed",
        "outgoing_bandwidth_speed",
        mode="before",
    )
    def cast_to_float(cls, v):
        return NumericValidatorMixin.cast_to_float(v)


class NodeStatsList(StatList):
    stats: list[NodeStats]

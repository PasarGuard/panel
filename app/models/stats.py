from enum import Enum
from datetime import datetime as dt

from pydantic import BaseModel, field_validator

from app.utils.helpers import fix_datetime_timezone
from .validators import NumericValidatorMixin


class Period(str, Enum):
    minute = "minute"
    hour = "hour"
    day = "day"
    month = "month"


class StatList(BaseModel):
    period: Period | None = None
    start: dt
    end: dt

    @field_validator("start", "end", mode="before")
    @classmethod
    def validator_date(cls, v):
        if not v:
            return v
        return fix_datetime_timezone(v)


class UserUsageStat(BaseModel):
    total_traffic: int
    period_start: dt

    @field_validator("total_traffic", mode="before")
    def cast_to_int(cls, v):
        return NumericValidatorMixin.cast_to_int(v)

    @field_validator("period_start", mode="before")
    @classmethod
    def validator_date(cls, v):
        if not v:
            return v
        return fix_datetime_timezone(v)


class UserUsageStatsList(StatList):
    stats: dict[int, list[UserUsageStat]]


class NodeUsageStat(BaseModel):
    uplink: int
    downlink: int
    period_start: dt

    @field_validator("downlink", "uplink", mode="before")
    def cast_to_int(cls, v):
        return NumericValidatorMixin.cast_to_int(v)

    @field_validator("period_start", mode="before")
    @classmethod
    def validator_date(cls, v):
        if not v:
            return v
        return fix_datetime_timezone(v)


class NodeUsageStatsList(StatList):
    stats: dict[int, list[NodeUsageStat]]


class NodeRealtimeStats(BaseModel):
    mem_total: int
    mem_used: int
    cpu_cores: int
    cpu_usage: float
    incoming_bandwidth_speed: int
    outgoing_bandwidth_speed: int


class NodeStats(BaseModel):
    period_start: dt
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

    @field_validator("period_start", mode="before")
    @classmethod
    def validator_date(cls, v):
        if not v:
            return v
        return fix_datetime_timezone(v)


class NodeStatsList(StatList):
    stats: list[NodeStats]

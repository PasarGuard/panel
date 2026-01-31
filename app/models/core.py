from datetime import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.helpers import fix_datetime_timezone
from .validators import StringArrayValidator


class CoreBase(BaseModel):
    name: str
    config: dict
    exclude_inbound_tags: set[str]
    fallbacks_inbound_tags: set[str]

    @property
    def exclude_tags(self) -> str:
        if self.exclude_inbound_tags:
            return ",".join(self.exclude_inbound_tags)
        return ""

    @property
    def fallback_tags(self) -> str:
        if self.fallbacks_inbound_tags:
            return ",".join(self.fallbacks_inbound_tags)
        return ""


class CoreCreate(CoreBase):
    name: str | None = Field(max_length=256, default=None)
    exclude_inbound_tags: set | None = Field(default=None)
    fallbacks_inbound_tags: set | None = Field(default=None)

    @field_validator("config", mode="before")
    def validate_config(cls, v: dict) -> dict:
        if not v:
            raise ValueError("config dictionary cannot be empty")
        return v

    @field_validator("exclude_inbound_tags", "fallbacks_inbound_tags", mode="after")
    def validate_sets(cls, v: set):
        return StringArrayValidator.len_check(v, 2048)


class CoreResponse(CoreBase):
    id: int
    created_at: dt

    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", mode="before")
    @classmethod
    def validator_date(cls, v):
        if not v:
            return v
        return fix_datetime_timezone(v)


class CoreResponseList(BaseModel):
    count: int
    cores: list[CoreResponse] = []

    model_config = ConfigDict(from_attributes=True)

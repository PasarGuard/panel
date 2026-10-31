"""Personal subscription presentation, independent of global host configuration."""

import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MyHostsPolicy(BaseModel):
    enabled: bool = False
    allow_rename: bool = True
    allow_reorder: bool = True
    allow_disable: bool = True


class HostPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remark: str | None = Field(default=None, min_length=1, max_length=256)
    position: int | None = Field(default=None, ge=0, le=1_000_000)
    is_disabled: bool = False

    @field_validator("remark")
    @classmethod
    def validate_remark(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(unicodedata.category(char) == "Cc" for char in value):
            raise ValueError("Host name must contain no control characters")
        value = value.strip()
        if not value:
            raise ValueError("Host name must be nonempty")
        # Personal names are literal labels, not subscription format templates.
        if "{" in value or "}" in value:
            raise ValueError("Personal host names cannot contain formatting braces")
        return value


class MyHostUpdate(HostPreference):
    id: int = Field(gt=0)


class MyHostsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hosts: list[MyHostUpdate] = Field(max_length=10_000)

    @model_validator(mode="after")
    def unique_hosts(self):
        if len({host.id for host in self.hosts}) != len(self.hosts):
            raise ValueError("Duplicate host IDs")
        return self


class MyHost(BaseModel):
    id: int
    default_position: int
    original_remark: str
    inbound_tag: str | None
    remark: str
    is_disabled: bool
    globally_disabled: bool
    preference: HostPreference


class MyHostsResponse(BaseModel):
    policy: MyHostsPolicy
    hosts: list[MyHost]

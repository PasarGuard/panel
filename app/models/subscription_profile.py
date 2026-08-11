"""Validated, machine-readable subscription profile definitions.

Profiles are stored in the existing client-template table.  Keeping the
definition independent from a host avoids turning a display remark into a
configuration key and leaves legacy subscription templates untouched.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$")


class ProfileClient(StrEnum):
    generic = "generic"
    happ = "happ"
    incy = "incy"
    v2rayn = "v2rayn"


class HealthCheckSettings(BaseModel):
    url: str = Field(default="https://www.gstatic.com/generate_204", max_length=2048)
    interval: str = Field(default="3m", pattern=r"^\d+(?:ms|s|m|h)$")
    tolerance: int = Field(default=50, ge=0, le=65535)
    # Sing-box maps this to urltest.idle_timeout, so it must outlive an
    # interval rather than represent a single HTTP request timeout.
    timeout: str = Field(default="30m", pattern=r"^\d+(?:ms|s|m|h)$")

    @model_validator(mode="after")
    def validate_timeout(self):
        multipliers = {"ms": 1, "s": 1_000, "m": 60_000, "h": 3_600_000}

        def milliseconds(value: str) -> int:
            match = re.fullmatch(r"(\d+)(ms|s|m|h)", value)
            assert match is not None  # Field patterns run before this validator.
            return int(match.group(1)) * multipliers[match.group(2)]

        if milliseconds(self.timeout) < milliseconds(self.interval):
            raise ValueError("health_check.timeout must be greater than or equal to health_check.interval")
        return self


class ProfilePool(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    fallback_pool: str | None = Field(default=None, max_length=64)
    enabled: bool = True

    @field_validator("id", "fallback_pool")
    @classmethod
    def validate_machine_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not PROFILE_ID_PATTERN.fullmatch(normalized):
            raise ValueError("profile identifiers must use lowercase letters, digits, '_' or '-'")
        return normalized


class SubscriptionProfile(BaseModel):
    """Shared Xray/Sing-box profile schema stored as JSON template content."""

    schema_version: int = Field(default=1, ge=1, le=1)
    default_pool: str = Field(default="primary", min_length=1, max_length=64)
    pools: list[ProfilePool] = Field(default_factory=lambda: [ProfilePool(id="primary")], min_length=1, max_length=64)
    health_check: HealthCheckSettings = Field(default_factory=HealthCheckSettings)
    routing_rules: list[dict[str, Any]] = Field(default_factory=list, max_length=256)
    client: ProfileClient = ProfileClient.generic
    happ_deeplink: str | None = Field(default=None, max_length=2048)

    @field_validator("happ_deeplink")
    @classmethod
    def validate_happ_deeplink(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not value.startswith(("happ://routing/add/", "happ://routing/onadd/")):
            raise ValueError("happ_deeplink must use the Happ routing add/onadd URL scheme")
        return value

    @field_validator("default_pool")
    @classmethod
    def validate_default_pool(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not PROFILE_ID_PATTERN.fullmatch(normalized):
            raise ValueError("default_pool must be a machine-readable profile identifier")
        return normalized

    @model_validator(mode="after")
    def validate_pool_graph(self):
        pool_ids = [pool.id for pool in self.pools]
        if len(pool_ids) != len(set(pool_ids)):
            raise ValueError("profile pools must have unique ids")
        if self.default_pool not in pool_ids:
            raise ValueError("default_pool must reference a configured pool")
        enabled_pool_ids = {pool.id for pool in self.pools if pool.enabled}
        if self.default_pool not in enabled_pool_ids:
            raise ValueError("default_pool must reference an enabled pool")
        for pool in self.pools:
            if pool.fallback_pool and pool.fallback_pool not in pool_ids:
                raise ValueError(f"fallback_pool '{pool.fallback_pool}' is not configured")
            if pool.fallback_pool == pool.id:
                raise ValueError("a pool cannot fall back to itself")
            if pool.fallback_pool and pool.fallback_pool not in enabled_pool_ids:
                raise ValueError(f"fallback_pool '{pool.fallback_pool}' must reference an enabled pool")
        if self.happ_deeplink and self.client != ProfileClient.happ:
            raise ValueError("happ_deeplink is only supported for Happ profiles")
        return self

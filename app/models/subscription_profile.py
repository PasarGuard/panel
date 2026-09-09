"""Validated, machine-readable subscription profile definitions.

Profiles are stored in the existing client-template table.  Keeping the
definition independent from a host avoids turning a display remark into a
configuration key and leaves legacy subscription templates untouched.
"""

from __future__ import annotations

import base64
import binascii
import re
from enum import StrEnum
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$")

HAPP_ROUTING_PREFIXES = ("happ://routing/add/", "happ://routing/onadd/", "happ://routing/off")
# INCY parses the link regardless of scheme, so `happ://`, `incy://` and a bare
# `://` all reach the same handler.
INCY_ROUTING_PREFIXES = ("happ://routing/", "incy://routing/", "://routing/")


def _is_base64(value: str) -> bool:
    try:
        base64.b64decode(value, validate=True)
    except binascii.Error, ValueError:
        return False
    return bool(value)


class DomainStrategy(StrEnum):
    """Xray `routing.domainStrategy`.

    `AsIs` never resolves a domain, so IP-based rules (`geoip:*`, CIDRs) only
    match traffic that already arrived as an IP. Rulesets that mix domain and
    IP matching need one of the resolving strategies.
    """

    as_is = "AsIs"
    ip_if_non_match = "IPIfNonMatch"
    ip_on_demand = "IPOnDemand"


class BalancerStrategy(StrEnum):
    random = "random"
    round_robin = "roundRobin"
    least_ping = "leastPing"
    least_load = "leastLoad"


class ProfileClient(StrEnum):
    """Clients that accept a routing ruleset over the subscription response.

    All three read the same `routing` header but disagree on its value, so the
    client has to be known before one can be emitted. v2rayNG, v2rayN and
    Streisand are absent on purpose: they have no such mechanism.
    """

    generic = "generic"
    happ = "happ"
    incy = "incy"
    v2raytun = "v2raytun"


class HealthCheckSettings(BaseModel):
    url: str = Field(default="https://www.gstatic.com/generate_204", max_length=2048)
    interval: str = Field(default="3m", pattern=r"^\d+(?:ms|s|m|h)$")
    tolerance: int = Field(default=50, ge=0, le=65535)
    # Sing-box maps this to urltest.idle_timeout, so it must outlive an
    # interval rather than represent a single HTTP request timeout.
    timeout: str = Field(default="30m", pattern=r"^\d+(?:ms|s|m|h)$")
    # Xray burstObservatory's deadline for one probe, independent of the
    # Sing-box idle timeout and of the interval between measurement batches.
    probe_timeout: str = Field(default="5s", pattern=r"^\d+(?:ms|s|m|h)$")
    # `burstObservatory` measures concurrently and feeds leastLoad/leastPing;
    # plain `observatory` only tracks alive/dead for fallbackTag.
    burst: bool = False

    @model_validator(mode="after")
    def validate_timeout(self):
        multipliers = {"ms": 1, "s": 1_000, "m": 60_000, "h": 3_600_000}

        def milliseconds(value: str) -> int:
            match = re.fullmatch(r"(\d+)(ms|s|m|h)", value)
            assert match is not None  # Field patterns run before this validator.
            return int(match.group(1)) * multipliers[match.group(2)]

        if milliseconds(self.timeout) < milliseconds(self.interval):
            raise ValueError("health_check.timeout must be greater than or equal to health_check.interval")
        if milliseconds(self.probe_timeout) <= 0:
            raise ValueError("health_check.probe_timeout must be positive")
        return self


class BalancerSettings(BaseModel):
    """Tuning for the strategies that read the observatory's rankings.

    Measured against two servers, three endpoints: `leastLoad` on its own picks
    the single best endpoint and every request follows it, exactly like
    `leastPing`. With `expected` set it draws at random from the best N, which
    spreads the load while still leaving a failed endpoint out of the draw --
    the one combination that both distributes traffic and survives an outage.
    `random` and `roundRobin` distribute but keep dispatching to a dead server.

    Ignored by strategies that do not consult the observatory.
    """

    expected: int | None = Field(default=None, ge=1, le=64)
    # Xray treats an endpoint slower than every baseline as a last resort.
    baselines: list[str] | None = Field(default=None, max_length=8)

    @field_validator("baselines")
    @classmethod
    def validate_baselines(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for baseline in value:
            if not re.fullmatch(r"\d+(?:ms|s|m|h)", baseline):
                raise ValueError("balancer baselines must look like '1500ms' or '2s'")
        return value


class ProfileDns(BaseModel):
    """Resolver the client uses once the tunnel is up.

    Both cores previously carried a hardcoded public resolver, which cannot be
    right everywhere: an operator running their own DoH endpoint, or serving a
    region where a given resolver is blocked, had no way to change it.

    Each entry is a plain IP or an `https://host/path` DoH URL. Sing-box needs
    the two forms expressed as different server types, so anything else is
    rejected here rather than emitted as a config the client will refuse.
    """

    servers: list[str] = Field(default_factory=lambda: ["1.1.1.1"], min_length=1, max_length=8)

    @field_validator("servers")
    @classmethod
    def validate_servers(cls, value: list[str]) -> list[str]:
        for server in value:
            if server.startswith("https://"):
                # urlsplit, not string surgery: it unwraps an IPv6 literal's
                # brackets and range-checks the port, both of which sing-box
                # needs as separate fields. Anything it cannot read has to be
                # refused here -- reaching the generator would mean a config
                # that saves cleanly and then fails for every client.
                try:
                    parts = urlsplit(server)
                    host, port = parts.hostname, parts.port
                except ValueError as exc:
                    raise ValueError(f"DoH resolver '{server}' is not a usable URL: {exc}") from None
                if not host or not parts.path or parts.path == "/":
                    raise ValueError(
                        f"DoH resolver '{server}' needs a host and a path, e.g. https://dns.example/dns-query"
                    )
                if port is not None and not 1 <= port <= 65535:
                    raise ValueError(f"DoH resolver '{server}' has a port outside 1-65535")
                continue
            try:
                ip_address(server)
            except ValueError:
                raise ValueError(f"DNS server '{server}' must be an IP address or an https:// DoH URL") from None
        return value


class ProfilePool(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    # Shown to the end user in their client. `id` stays machine-readable because
    # routing rules address it; this is only ever a label.
    title: str | None = Field(default=None, max_length=64)
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
    dns: ProfileDns = Field(default_factory=ProfileDns)
    routing_rules: list[dict[str, Any]] = Field(default_factory=list, max_length=256)
    domain_strategy: DomainStrategy = DomainStrategy.as_is
    balancer_strategy: BalancerStrategy = BalancerStrategy.random
    # Only meaningful for leastLoad/leastPing; see BalancerSettings.
    balancer_settings: BalancerSettings | None = None
    # Publish a config per endpoint next to the automatic groups, so a user
    # can pick one server instead of only a group.
    publish_endpoint_configs: bool = True
    client: ProfileClient = ProfileClient.generic
    # Sent verbatim as the `routing` response header. The accepted shape depends
    # on `client`; see validate_client_routing below.
    routing_payload: str | None = Field(
        default=None, max_length=2048, validation_alias=AliasChoices("routing_payload", "happ_deeplink")
    )
    # Happ only: `routing-enable: 0` turns its routing off outright.
    routing_enabled: bool | None = None

    @field_validator("routing_payload")
    @classmethod
    def strip_routing_payload(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()

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
        return self

    @model_validator(mode="after")
    def validate_client_routing(self):
        """Each client decodes the `routing` header differently.

        Happ and INCY expect a Happ routing profile in base64; INCY ignores the
        URL scheme and also takes the bare payload. v2rayTun expects a bare
        base64 Xray `routing` object instead and does not decode a deeplink, so
        passing one there silently does nothing.
        """
        if self.routing_payload:
            if self.client is ProfileClient.generic:
                raise ValueError("routing_payload requires a specific client; generic profiles send no header")
            if self.client is ProfileClient.happ and not self.routing_payload.startswith(HAPP_ROUTING_PREFIXES):
                raise ValueError("a Happ routing payload must be a happ://routing/add|onadd|off link")
            if self.client is ProfileClient.incy and not (
                self.routing_payload.startswith(INCY_ROUTING_PREFIXES) or _is_base64(self.routing_payload)
            ):
                raise ValueError("an INCY routing payload must be a ://routing/... link or bare base64")
            if self.client is ProfileClient.v2raytun and not _is_base64(self.routing_payload):
                raise ValueError("a v2rayTun routing payload must be bare base64, without a deeplink prefix")
        if self.routing_enabled is not None and self.client is not ProfileClient.happ:
            raise ValueError("routing_enabled is only supported for Happ profiles")
        return self

"""Happ routing profiles (https://github.com/HappDev/happ_su, dev-docs/routing.md)."""

import base64
import json
from typing import Any

HAPP_ROUTING_LINK_PREFIX = "happ://routing/onadd/"

_BOOL_STRING_FIELDS = ("GlobalProxy", "FakeDNS")
_STRING_FIELDS = (
    "RemoteDNSType",
    "RemoteDNSDomain",
    "RemoteDNSIP",
    "DomesticDNSType",
    "DomesticDNSDomain",
    "DomesticDNSIP",
    "Geoipurl",
    "Geositeurl",
    "LastUpdated",
    "DomainStrategy",
)
_STRING_LIST_FIELDS = ("DirectSites", "DirectIp", "ProxySites", "ProxyIp", "BlockSites", "BlockIp")
_DOMAIN_STRATEGIES = ("AsIs", "IPIfNonMatch", "IPOnDemand")


def parse_happ_routing_profile(content: str) -> dict[str, Any]:
    """Parse and validate a Happ routing profile. Unknown keys are kept as-is."""
    try:
        profile = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Happ routing profile must be valid JSON: {exc.msg}") from exc

    if not isinstance(profile, dict):
        raise ValueError("Happ routing profile must be a JSON object")  # noqa: TRY004

    name = profile.get("Name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Happ routing profile must contain a non-empty 'Name' string")

    for field in _BOOL_STRING_FIELDS:
        if field in profile and profile[field] not in ("true", "false"):
            raise ValueError(f'\'{field}\' must be the string "true" or "false"')

    for field in _STRING_FIELDS:
        if field in profile and not isinstance(profile[field], str):
            raise ValueError(f"'{field}' must be a string")

    if "DomainStrategy" in profile and profile["DomainStrategy"] not in _DOMAIN_STRATEGIES:
        raise ValueError(f"'DomainStrategy' must be one of: {', '.join(_DOMAIN_STRATEGIES)}")

    for field in _STRING_LIST_FIELDS:
        if field in profile and (
            not isinstance(profile[field], list) or not all(isinstance(item, str) for item in profile[field])
        ):
            raise ValueError(f"'{field}' must be an array of strings")

    if "DnsHosts" in profile and (
        not isinstance(profile["DnsHosts"], dict)
        or not all(isinstance(value, str) for value in profile["DnsHosts"].values())
    ):
        raise ValueError("'DnsHosts' must be an object of host name to IP address strings")

    # json.loads accepts NaN/Infinity (and turns 1e999 into inf), which are not valid JSON for Happ
    try:
        json.dumps(profile, allow_nan=False)
    except ValueError as exc:
        raise ValueError("Happ routing profile must not contain NaN or Infinity numbers") from exc

    return profile


def build_happ_routing_link(profile: dict[str, Any]) -> str:
    """Build a `happ://routing/onadd/{base64}` link: standard Base64 of compact UTF-8 JSON."""
    payload = json.dumps(profile, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return HAPP_ROUTING_LINK_PREFIX + base64.b64encode(payload).decode("ascii")

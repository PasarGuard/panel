"""Happ routing documents carried as UTF-8 JSON in a deeplink."""

import base64
import json
from typing import Any

HAPP_HEADER_LIMIT = 2048
HAPP_OWNED_HEADERS = {"routing", "routing-enable"}


def load_happ_document(content: str) -> dict[str, Any]:
    def reject_constant(value: str):
        raise ValueError(f"Invalid JSON constant: {value}")

    document = json.loads(content, parse_constant=reject_constant)
    if not isinstance(document, dict):
        raise ValueError("Happ routing content must be a JSON object")  # noqa: TRY004
    if not isinstance(document.get("Name"), str) or not document["Name"].strip():
        raise ValueError("Happ routing content requires a nonempty Name")
    for key in ("GlobalProxy", "FakeDNS"):
        if key in document and document[key] not in ("true", "false"):
            raise ValueError(f"Happ {key} must be the string true or false")
    for key in (
        "RemoteDNSType", "DomesticDNSType", "RemoteDNSDomain", "RemoteDNSIP",
        "DomesticDNSDomain", "DomesticDNSIP", "Geoipurl", "Geositeurl", "LastUpdated",
    ):
        if key in document and not isinstance(document[key], str):
            raise ValueError(f"Happ {key} must be a string")
    for key in ("DirectSites", "DirectIp", "ProxySites", "ProxyIp", "BlockSites", "BlockIp"):
        if key in document and (
            not isinstance(document[key], list) or any(not isinstance(item, str) for item in document[key])
        ):
            raise ValueError(f"Happ {key} must be an array of strings")
    if "DnsHosts" in document:
        hosts = document["DnsHosts"]
        if not isinstance(hosts, dict) or any(not isinstance(value, str) for value in hosts.values()):
            raise ValueError("Happ DnsHosts must map names to strings")
    if "DomainStrategy" in document and document["DomainStrategy"] not in ("AsIs", "IPIfNonMatch", "IPOnDemand"):
        raise ValueError("Invalid Happ DomainStrategy")
    return document


def happ_deeplink(content: str, action: str, transport: str) -> tuple[str, dict[str, Any]]:
    document = load_happ_document(content)
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    link = f"happ://routing/{action}/{base64.b64encode(payload).decode('ascii')}"
    if transport == "header" and len(link.encode("ascii")) > HAPP_HEADER_LIMIT:
        raise ValueError(f"Happ routing header exceeds {HAPP_HEADER_LIMIT} ASCII bytes; use body transport")
    return link, document

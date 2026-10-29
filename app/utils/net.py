import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost")
_MAX_HOST_LENGTH = 253


def url_host_for_log(url: str) -> str:
    """Host part of url for log lines: no scheme, credentials, path, query or fragment."""
    try:
        host = urlparse(url).hostname
    except ValueError, TypeError, AttributeError:
        host = None
    return (host or "<invalid>")[:_MAX_HOST_LENGTH]


def is_http_url(url: str) -> bool:
    """True when url is http(s) with a host; no address checks. Never raises."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.hostname)
    except ValueError, TypeError, AttributeError:
        return False


def is_public_http_url(url: str) -> bool:
    """True when url is http(s) and every address it resolves to is public.

    Webhook destinations come from panel settings and are meant for external receivers, so loopback,
    private, link-local and other non-global addresses are not public. Any malformed value (bad port,
    overlong label, undecodable host) is simply not public: this never raises.
    """
    try:
        return _is_public_http_url(url)
    except ValueError, UnicodeError, OSError, TypeError:
        return False


def _is_public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if len(parsed.hostname) > _MAX_HOST_LENGTH:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(_BLOCKED_HOST_SUFFIXES):
        return False
    # parsed.port raises ValueError for a port outside 0-65535.
    infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not infos:
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            return False
    return True

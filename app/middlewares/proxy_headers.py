import ipaddress
from typing import Any, Awaitable, Callable

Scope = dict[str, Any]
ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, ASGIReceive, ASGISend], Awaitable[None]]


class ProxyHeadersMiddleware:
    """
    Handle trusted proxy headers to update scheme and client address.
    Derived from uvicorn.middleware.proxy_headers to avoid importing uvicorn.
    """

    def __init__(self, app: ASGIApp, trusted_hosts: list[str] | str = "127.0.0.1") -> None:
        self.app = app
        self.trusted_hosts = _TrustedHosts(trusted_hosts)

    async def __call__(self, scope: Scope, receive: ASGIReceive, send: ASGISend) -> None:
        if scope.get("type") == "lifespan":
            return await self.app(scope, receive, send)

        client_addr = scope.get("client")
        client_host = client_addr[0] if client_addr else None

        if client_host in self.trusted_hosts:
            headers = dict(scope.get("headers") or [])

            if b"x-forwarded-proto" in headers:
                x_forwarded_proto = headers[b"x-forwarded-proto"].decode("latin1").strip()

                if x_forwarded_proto in {"http", "https", "ws", "wss"}:
                    if scope["type"] == "websocket":
                        scope["scheme"] = x_forwarded_proto.replace("http", "ws")
                    else:
                        scope["scheme"] = x_forwarded_proto

            if b"x-forwarded-for" in headers:
                x_forwarded_for = headers[b"x-forwarded-for"].decode("latin1")
                host = self.trusted_hosts.get_trusted_client_host(x_forwarded_for)

                if host:
                    # The connecting client's port is lost when a proxy is in front.
                    port = 0
                    scope["client"] = (host, port)

        return await self.app(scope, receive, send)


def _parse_raw_hosts(value: str) -> list[str]:
    return [item.strip() for item in value.split(",")]


class _TrustedHosts:
    """Container for trusted hosts and networks."""

    def __init__(self, trusted_hosts: list[str] | str) -> None:
        self.always_trust: bool = trusted_hosts in ("*", ["*"])

        self.trusted_literals: set[str] = set()
        self.trusted_hosts: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        self.trusted_networks: set[ipaddress.IPv4Network | ipaddress.IPv6Network] = set()

        if not self.always_trust:
            if isinstance(trusted_hosts, str):
                trusted_hosts = _parse_raw_hosts(trusted_hosts)

            for host in trusted_hosts:
                if "/" in host:
                    try:
                        self.trusted_networks.add(ipaddress.ip_network(host))
                    except ValueError:
                        self.trusted_literals.add(host)
                else:
                    try:
                        self.trusted_hosts.add(ipaddress.ip_address(host))
                    except ValueError:
                        self.trusted_literals.add(host)

    def __contains__(self, host: str | None) -> bool:
        if self.always_trust:
            return True

        if not host:
            return False

        try:
            ip = ipaddress.ip_address(host)
            if ip in self.trusted_hosts:
                return True
            return any(ip in net for net in self.trusted_networks)

        except ValueError:
            return host in self.trusted_literals

    def get_trusted_client_host(self, x_forwarded_for: str) -> str:
        """Extract the first untrusted host from X-Forwarded-For."""
        x_forwarded_for_hosts = _parse_raw_hosts(x_forwarded_for)

        if self.always_trust:
            return x_forwarded_for_hosts[0]

        for host in reversed(x_forwarded_for_hosts):
            if host not in self:
                return host

        return x_forwarded_for_hosts[0]

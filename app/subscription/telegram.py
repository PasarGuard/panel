import base64
import re
from random import choice
from urllib.parse import quote

from app.models.subscription import SubscriptionInboundData

from .links import StandardLinks

_MTPROTO_SECRET_RE = re.compile(r"[0-9a-f]{32}")


class TelegramLinks(StandardLinks):
    """Share links for the subscription page and dashboard, including Telegram proxies."""

    def __init__(
        self,
        user_agent_template_content: str | None = None,
        grpc_user_agent_template_content: str | None = None,
    ):
        super().__init__(
            user_agent_template_content=user_agent_template_content,
            grpc_user_agent_template_content=grpc_user_agent_template_content,
        )
        self.protocol_handlers["mtproto"] = self._build_mtproto

    def _build_mtproto(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> str:
        """Build a Telegram proxy or WEB proxy link in telemt's form; "" without a valid secret or a served type."""
        secret = str(settings.get("secret") or "").strip().lower()
        if not _MTPROTO_SECRET_RE.fullmatch(secret):
            return ""
        if inbound.mtproto_link_type == "web":
            wanted = address.strip().lower()
            for vhost in inbound.mtproto_web_vhosts:
                host = (vhost.get("host") or "").strip().lower()
                if host and host == wanted:
                    return self._telegram_web_link(
                        host, vhost.get("base_path") or "", vhost.get("secret_mode") or "dd", secret
                    )
            return ""
        if not inbound.mtproto_native:
            return ""
        client_secret = self._mtproto_client_secret(secret, inbound)
        if not client_secret:
            return ""
        port = inbound.port if isinstance(inbound.port, int) else inbound.port[0]
        return f"tg://proxy?server={self._telegram_link_host(address)}&port={port}&secret={client_secret}"

    @staticmethod
    def _telegram_link_host(address: str) -> str:
        """Host for a Telegram proxy link: an IPv6 literal goes in without brackets, as telemt writes it."""
        host = address.strip()
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        return quote(host, safe=":")

    @staticmethod
    def _mtproto_client_secret(hex_secret: str, inbound: SubscriptionInboundData) -> str:
        """Client secret for the host's link type; "auto" takes the best mode the inbound serves
        (fake TLS, then secure, then classic).

        Return "" when the core does not serve the type; tls without a domain cannot be used.
        """
        secret = hex_secret.strip().lower()
        modes = inbound.mtproto_modes or {}
        link_type = inbound.mtproto_link_type
        if link_type == "auto":
            domain = (inbound.mtproto_tls_domain or "").strip()
            if modes.get("tls") and domain:
                return "ee" + secret + domain.encode("utf-8").hex()
            if modes.get("secure"):
                return "dd" + secret
            if modes.get("classic"):
                return secret
            return ""
        if not modes.get(link_type):
            return ""
        if link_type == "tls":
            domains = [domain for domain in inbound.mtproto_link_domains if domain]
            return "ee" + secret + choice(domains).encode("utf-8").hex() if domains else ""
        if link_type == "secure":
            return "dd" + secret
        if link_type == "classic":
            return secret
        return ""

    @staticmethod
    def _telegram_web_link(host: str, base_path: str, secret_mode: str, hex_secret: str) -> str:
        """WEB proxy link exactly as telemt's format_web_proxy_link writes it."""
        secret = hex_secret.lower()
        dd = secret_mode == "dd"
        if not base_path:
            return f"tg://webproxy?server={host}&secret={'dd' if dd else ''}{secret}"
        # telemt form-urlencodes host/base_path. The core check limits base_path to telemt's rule
        # ([A-Za-z0-9_-] segments joined by "/"), so it is used as is and quote matches telemt for it.
        server = quote(f"{host}/{base_path}", safe="")
        marked = bytes([0x70, *([0xDD] if dd else []), *bytes.fromhex(secret)])
        return f"tg://webproxy?server={server}&secret={base64.urlsafe_b64encode(marked).rstrip(b'=').decode()}"

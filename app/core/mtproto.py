from __future__ import annotations

import ipaddress
import json
import re
from copy import deepcopy
from urllib.parse import urlsplit

import commentjson

from app.models.core import CoreType
from app.models.protocol import ProxyProtocol

_MTPROTO_PROTOCOLS = frozenset((ProxyProtocol.mtproto,))
_RESTRICTED_ACCESS_KEYS = (
    "users",
    "user_ad_tags",
    "user_max_tcp_conns",
    "user_expirations",
    "user_data_quota",
    "user_max_unique_ips",
    "user_enabled",
)
# Paths the node refuses (node backend/mtproto/config.go rejectedConfigKeys), with the node's reason.
_NODE_REJECTED_KEYS = (
    (("include",), "telemt would read other files on the node host"),
    (("web", "debug"), "it opens a debug surface on the node host"),
    (("web", "limits", "max_profiles"), "the node sizes it for one WEB profile per user and vhost"),
    (("server", "api"), "the node manages the telemt control API"),
    (("server", "admin_api"), "it is an alias of server.api, which the node manages"),
    (("server", "metrics_port"), "the node manages the metrics endpoint"),
    (("server", "metrics_listen"), "the node manages the metrics endpoint"),
    (("server", "metrics_whitelist"), "the node manages the metrics endpoint"),
    (("access", "user_rate_limits"), "per-user maps are keyed by node-managed usernames"),
    (("access", "user_source_deny"), "per-user maps are keyed by node-managed usernames"),
)
_OBJECT_PATHS = (
    ("general",),
    ("general", "telemetry"),
    ("general", "modes"),
    ("server",),
    ("access",),
    ("logging",),
    ("censorship",),
    ("web",),
    ("web", "limits"),
)
_DEFAULT_INBOUND_TAG = "mtproto"
# The inbounds.tag column length.
_MAX_INBOUND_TAG_LENGTH = 256
# telemt 3.5.14 defaults: server.port 443 and, per field, general.modes classic=false, secure=false, tls=true.
TELEMT_DEFAULT_PORT = 443
TELEMT_DEFAULT_MODES = {"classic": False, "secure": False, "tls": True}
# The domain the default core template ships with; it must be replaced before the core saves.
TLS_DOMAIN_PLACEHOLDER = "your-domain.example"
# An ASCII host name of letter, digit and hyphen labels (an internationalized name in its xn-- form).
# telemt hex-encodes its IDNA-normalized host into the "ee" secret, so any other character gives a dead link.
_TLS_HOST_NAME = re.compile(
    r"(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)
# The PasarGuard-only per-vhost user_profile (the node expands it into one telemt profile per user).
_WEB_SECRET_MODES = ("dd", "plain")
_WEB_DEFAULT_SECRET_MODE = "dd"
_WEB_PROFILE_LIMITS = ("max_sessions", "max_streams", "max_streams_per_session")
_UINT32_MAX = 4294967295
# Go's net.IP.IsPrivate ranges (RFC 1918 and RFC 4193), which the node uses. Python's is_private also
# accepts documentation and other reserved ranges, such as 198.51.100.0/24, so it is not used.
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


def _find_key(value, key: str, path: str = "") -> str | None:
    """Path of the first set key named key at any depth (tables in arrays included), or None."""
    if isinstance(value, dict):
        for name in sorted(value):
            name_path = f"{path}.{name}" if path else name
            if name == key and value[name] is not None:
                return name_path
            found = _find_key(value[name], key, name_path)
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_key(item, key, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _private_ip(value) -> bool:
    """True for a loopback or private IP literal, like the node's IsLoopback() || IsPrivate()."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if address.is_unspecified:
        return False
    return address.is_loopback or any(address in network for network in _PRIVATE_NETWORKS)


def _port_value(field: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer between 1 and 65535")
    if not 1 <= value <= 65535:
        raise ValueError(f"{field} must be an integer between 1 and 65535, got {value}")
    return value


class MtprotoConfig(dict):
    def __init__(
        self,
        config: dict | str | None = None,
        exclude_inbound_tags: set[str] | None = None,
        fallbacks_inbound_tags: set[str] | None = None,
        skip_validation: bool = False,
    ):
        if config is None:
            config = {}
        if isinstance(config, str):
            config = commentjson.loads(config)
        if isinstance(config, dict):
            config = deepcopy(config)

        super().__init__(config)

        self._type = CoreType.mtproto
        self.exclude_inbound_tags = set(exclude_inbound_tags or set())
        self.fallbacks_inbound_tags = set(fallbacks_inbound_tags or set())
        self._inbounds: list[str] = []
        self._inbounds_by_tag: dict[str, dict] = {}
        self._listen_port = TELEMT_DEFAULT_PORT
        self._native = True

        if skip_validation:
            return

        self._validate()
        self._resolve_inbounds()

    @property
    def type(self) -> str:
        return self._type

    def _validate(self):
        if self.exclude_inbound_tags:
            raise ValueError("exclude_inbound_tags is only supported for xray cores")
        if self.fallbacks_inbound_tags:
            raise ValueError("fallbacks_inbound_tags is only supported for xray cores")

        self._validate_inbound_tag()

        # JSON null means "not set" everywhere, as on the node, whose renderer drops null fields.
        for path in _OBJECT_PATHS:
            self._object_at(*path)

        access = self._object_at("access")
        for key in _RESTRICTED_ACCESS_KEYS:
            if access is not None and access.get(key) is not None:
                raise ValueError(f"access.{key} must not be set; the node derives per-user access data")

        for path, reason in _NODE_REJECTED_KEYS:
            parent = self._object_at(*path[:-1])
            if parent is not None and parent.get(path[-1]) is not None:
                raise ValueError(f"{'.'.join(path)} must not be set: {reason}")

        # telemt reads a key named include in any table as a file include, so the node refuses it at any depth.
        include_path = _find_key(self, "include")
        if include_path is not None:
            raise ValueError(f"{include_path} must not be set: telemt would read other files on the node host")

        port = self._validate_ports()
        self._validate_modes()
        self._validate_tls_domain()
        self._validate_tls_domains()
        self._validate_web()
        self._listen_port = port

    def _object_at(self, *path: str) -> dict | None:
        """The object at path, or None when a part is missing or null; a non-object part is a TypeError."""
        current = self
        for index, key in enumerate(path):
            value = current.get(key)
            if value is None:
                return None
            if not isinstance(value, dict):
                raise TypeError(f"{'.'.join(path[: index + 1])} must be an object")
            current = value
        return current

    def _validate_inbound_tag(self):
        inbound_tag = self.get("inbound_tag")
        if inbound_tag is None:
            inbound_tag = _DEFAULT_INBOUND_TAG
        if not isinstance(inbound_tag, str):
            raise TypeError("inbound_tag must be a string")
        inbound_tag = inbound_tag.strip()
        if not inbound_tag:
            raise ValueError("inbound_tag must not be empty")
        # Xray's rule: user inbound lists are joined with "," and "<=>" marks generated fallback tags.
        if "," in inbound_tag or "<=>" in inbound_tag:
            raise ValueError('inbound_tag must not contain "," or "<=>"')
        if len(inbound_tag) > _MAX_INBOUND_TAG_LENGTH:
            raise ValueError(f"inbound_tag must be at most {_MAX_INBOUND_TAG_LENGTH} characters")
        self["inbound_tag"] = inbound_tag

    def _validate_ports(self) -> int:
        server = self._object_at("server")
        port = server.get("port") if server is not None else None
        port = TELEMT_DEFAULT_PORT if port is None else _port_value("server.port", port)

        listeners = server.get("listeners") if server is not None else None
        if listeners is None:
            return port
        if not isinstance(listeners, list):
            raise TypeError("server.listeners must be a list of objects")
        native = False
        for index, listener in enumerate(listeners):
            field = f"server.listeners[{index}]"
            if not isinstance(listener, dict):
                raise TypeError(f"{field} must be an object")
            transport = listener.get("transport")
            if transport == "web":
                self._validate_web_listener(field, listener, port)
                continue
            if transport is not None and transport != "mtproxy":
                raise ValueError(f'{field}.transport must be "mtproxy" or "web"; the node supports no other listener')
            native = True
            # telemt's own links use the first listener's port: equal ports keep its links, the panel's
            # links and the node's port bookkeeping identical.
            if listener.get("port") is not None and _port_value(f"{field}.port", listener["port"]) != port:
                raise ValueError(
                    f"{field}.port must equal server.port ({port}); the panel builds MTProto links with one port"
                )
        # telemt opens its default public listener only when server.listeners is empty.
        self._native = native or not listeners
        return port

    @staticmethod
    def _validate_web_listener(field: str, listener: dict, port: int):
        # A front (Caddy, nginx) holds the certificate and the public address; telemt's WEB listener stays private.
        if not _private_ip(listener.get("ip")):
            raise ValueError(
                f"{field}.ip must be a loopback or private IP address for a web listener; "
                "a front such as Caddy or nginx serves the public side"
            )
        if listener.get("port") is None:
            raise ValueError(f"{field}.port is required for a web listener")
        # Native listeners all use server.port (or telemt's default listener does), so this is the only clash.
        if _port_value(f"{field}.port", listener["port"]) == port:
            raise ValueError(f"{field}.port must differ from server.port ({port}), which MTProxy listeners use")

    def _validate_modes(self):
        raw_modes = self._object_at("general", "modes") or {}
        for name, enabled in raw_modes.items():
            if enabled is None:
                continue
            if name not in TELEMT_DEFAULT_MODES:
                raise ValueError(f"general.modes.{name} is not a telemt mode; use classic, secure or tls")
            if not isinstance(enabled, bool):
                raise TypeError(f"general.modes.{name} must be true or false")
        if not any(self._modes().values()):
            raise ValueError("general.modes must enable at least one of classic, secure, tls")

    def _validate_tls_domain(self):
        censorship = self._object_at("censorship")
        domain = censorship.get("tls_domain") if censorship is not None else None
        if domain is not None and not isinstance(domain, str):
            raise TypeError("censorship.tls_domain must be a string")
        tls = self._modes()["tls"]
        if domain is None:
            if tls:
                raise ValueError(
                    "censorship.tls_domain is required when general.modes.tls is on (telemt's default); "
                    "set the domain that TLS-mode clients present"
                )
            return
        domain = domain.strip()
        # telemt refuses an empty domain and any whitespace, "/" or "\" even when tls mode is off.
        if not domain:
            raise ValueError("censorship.tls_domain must not be empty")
        if any(char.isspace() or char in "/\\" for char in domain):
            raise ValueError("censorship.tls_domain must be a bare domain name, without spaces, '/' or '\\'")
        if tls:
            if ":" in domain:
                raise ValueError("censorship.tls_domain must be a bare domain name, without a port or ':'")
            # telemt keeps one trailing dot ("a.org."), so it is allowed and stored as written.
            host = domain.removesuffix(".")
            if not _TLS_HOST_NAME.fullmatch(host):
                raise ValueError(
                    f'censorship.tls_domain "{domain}" must be an ASCII host name: letters, digits, "-" and "." '
                    "(write an internationalized name in its xn-- form)"
                )
            if host.lower().endswith(".example"):
                raise ValueError(
                    f'censorship.tls_domain "{domain}" is a placeholder (.example is a reserved TLD); '
                    "replace it with the real domain that TLS-mode clients present"
                )
        censorship["tls_domain"] = domain

    def _validate_tls_domains(self):
        censorship = self._object_at("censorship")
        domains = censorship.get("tls_domains") if censorship is not None else None
        if domains is None:
            return
        if not isinstance(domains, list):
            raise TypeError("censorship.tls_domains must be a list of domain names")
        stored = []
        for index, domain in enumerate(domains):
            field = f"censorship.tls_domains[{index}]"
            if not isinstance(domain, str):
                raise TypeError(f"{field} must be a string")
            domain = domain.strip()
            # telemt skips empty entries and checks the rest like tls_domain, even with tls mode off.
            if domain:
                host = domain.removesuffix(".")
                if not _TLS_HOST_NAME.fullmatch(host):
                    raise ValueError(
                        f'{field} "{domain}" must be an ASCII host name: letters, digits, "-" and "." '
                        "(write an internationalized name in its xn-- form)"
                    )
                if host.lower().endswith(".example"):
                    raise ValueError(
                        f'{field} "{domain}" is a placeholder (.example is a reserved TLD); '
                        "replace it with a real domain that TLS-mode clients present"
                    )
            stored.append(domain)
        censorship["tls_domains"] = stored

    def _validate_web(self):
        web = self._object_at("web") or {}
        enabled = web.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise TypeError("web.enabled must be true or false")
        vhosts = web.get("vhosts")
        if vhosts is None:
            vhosts = []
        if not isinstance(vhosts, list):
            raise TypeError("web.vhosts must be a list of objects")
        for index, vhost in enumerate(vhosts):
            self._validate_web_vhost(f"web.vhosts[{index}]", vhost)

        has_listener = any(
            isinstance(listener, dict) and listener.get("transport") == "web" for listener in self._listeners()
        )
        if enabled and not has_listener:
            raise ValueError('web.enabled needs a server.listeners entry with transport "web"')
        if has_listener and not (enabled and vhosts):
            raise ValueError('a "web" listener needs web.enabled set to true and at least one web.vhosts entry')

    @staticmethod
    def _validate_web_vhost(field: str, vhost):
        if not isinstance(vhost, dict):
            raise TypeError(f"{field} must be an object")
        if vhost.get("profiles") is not None:
            raise ValueError(
                f"{field}.profiles must not be set: the node creates one profile per user from user_profile"
            )
        for key in ("host", "base_path"):
            if vhost.get(key) is not None and not isinstance(vhost[key], str):
                raise TypeError(f"{field}.{key} must be a string")

        decoy = vhost.get("decoy")
        if not isinstance(decoy, dict) or decoy.get("mode") != "http_upstream":
            mode = decoy.get("mode") if isinstance(decoy, dict) else None
            raise ValueError(
                f'{field}.decoy.mode must be "http_upstream" (got {mode!r}); '
                "static_directory would serve files from the node host"
            )
        upstream = decoy.get("upstream")
        host = urlsplit(upstream).hostname if isinstance(upstream, str) else None
        # telemt requires the decoy origin to be a private IP literal; checked here for a clear error.
        if not _private_ip(host):
            raise ValueError(f"{field}.decoy.upstream must be a URL whose host is a loopback or private IP literal")

        profile = vhost.get("user_profile")
        if profile is None:
            return
        if not isinstance(profile, dict):
            raise TypeError(f"{field}.user_profile must be an object")
        secret_mode = profile.get("secret_mode")
        if secret_mode is not None and secret_mode not in _WEB_SECRET_MODES:
            raise ValueError(f'{field}.user_profile.secret_mode must be "dd" or "plain"; WEB does not support "ee"')
        for key in _WEB_PROFILE_LIMITS:
            value = profile.get(key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field}.user_profile.{key} must be an integer")
            if not 0 <= value <= _UINT32_MAX:
                raise ValueError(f"{field}.user_profile.{key} must be between 0 and {_UINT32_MAX}, got {value}")

    def _listeners(self) -> list:
        server = self.get("server")
        listeners = server.get("listeners") if isinstance(server, dict) else None
        return listeners if isinstance(listeners, list) else []

    def _modes(self) -> dict[str, bool]:
        """telemt's resolved modes: its per-field defaults updated with the configured values."""
        modes = dict(TELEMT_DEFAULT_MODES)
        general = self.get("general")
        raw_modes = general.get("modes") if isinstance(general, dict) else None
        if isinstance(raw_modes, dict):
            modes.update({name: raw_modes[name] for name in TELEMT_DEFAULT_MODES if raw_modes.get(name) is not None})
        return modes

    def _tls_domain(self) -> str:
        if not self._modes()["tls"]:
            return ""
        censorship = self.get("censorship")
        domain = censorship.get("tls_domain") if isinstance(censorship, dict) else None
        return domain.strip() if isinstance(domain, str) else ""

    def _tls_domains(self) -> list[str]:
        """telemt's fake TLS domains: tls_domain first, then tls_domains, deduplicated like telemt (case-insensitive)."""
        primary = self._tls_domain()
        if not primary:
            return []
        domains = [primary]
        seen = {primary.lower()}
        extra = self["censorship"].get("tls_domains") or []
        for domain in extra:
            if domain and domain.lower() not in seen:
                seen.add(domain.lower())
                domains.append(domain)
        return domains

    def _web_vhosts(self) -> list[dict]:
        web = self.get("web")
        if not isinstance(web, dict) or not web.get("enabled"):
            return []
        vhosts = []
        for vhost in web.get("vhosts") or []:
            profile = vhost.get("user_profile") or {}
            vhosts.append(
                {
                    "host": vhost.get("host") or "",
                    "base_path": vhost.get("base_path") or "",
                    "secret_mode": profile.get("secret_mode") or _WEB_DEFAULT_SECRET_MODE,
                }
            )
        return vhosts

    def _resolve_inbounds(self):
        inbound_tag = self["inbound_tag"]
        metadata = {
            "tag": inbound_tag,
            "protocol": "mtproto",
            "network": "tcp",
            "tls": "none",
            "listen_port": self._listen_port,
            "port": self._listen_port,
            "modes": self._modes(),
            "tls_domain": self._tls_domain(),
            "tls_domains": self._tls_domains(),
            "native": self._native,
            "web_vhosts": self._web_vhosts(),
        }
        self._inbounds = [inbound_tag]
        self._inbounds_by_tag = {inbound_tag: metadata}

    def to_str(self, **json_kwargs) -> str:
        return json.dumps(self, **json_kwargs)

    @property
    def inbounds_by_tag(self) -> dict:
        return self._inbounds_by_tag

    @property
    def inbounds(self) -> list[str]:
        return self._inbounds

    @property
    def protocols(self) -> frozenset[ProxyProtocol]:
        return _MTPROTO_PROTOCOLS

    def to_json(self) -> dict:
        return {
            "type": self.type,
            "config": dict(self),
            "exclude_inbound_tags": [],
            "fallbacks_inbound_tags": [],
            "inbounds": self.inbounds,
            "inbounds_by_tag": self.inbounds_by_tag,
        }

    @classmethod
    def from_json(cls, data: dict) -> MtprotoConfig:
        instance = cls(config=data.get("config", {}), skip_validation=True)
        if "inbounds" in data:
            instance._inbounds = data["inbounds"]
        if "inbounds_by_tag" in data:
            instance._inbounds_by_tag = data["inbounds_by_tag"]
        return instance

    def copy(self):
        return deepcopy(self)

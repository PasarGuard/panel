from __future__ import annotations

import json
from copy import deepcopy
from pathlib import PosixPath

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
_DEFAULT_INBOUND_TAG = "mtproto"
_DEFAULT_MODES = {"classic": True}


class MtprotoConfig(dict):
    def __init__(
        self,
        config: dict | str | PosixPath | None = None,
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

        inbound_tag = str(self.get("inbound_tag") or _DEFAULT_INBOUND_TAG).strip()
        if not inbound_tag:
            raise ValueError("inbound_tag must not be empty")
        self["inbound_tag"] = inbound_tag

        access = self.get("access")
        if access is None:
            pass
        elif not isinstance(access, dict):
            raise TypeError("access must be an object")
        else:
            for key in _RESTRICTED_ACCESS_KEYS:
                if key in access:
                    raise ValueError(f"access.{key} must not be set; the node derives per-user access data")

        server = self.get("server")
        if server is None:
            raise ValueError("server is required")
        if not isinstance(server, dict):
            raise TypeError("server must be an object")

        port = server.get("port")
        if not isinstance(port, int) or port <= 0 or port > 65535:
            raise ValueError("server.port must be an integer between 1 and 65535")

        general = self.get("general")
        if general is not None and not isinstance(general, dict):
            raise TypeError("general must be an object")

        censorship = self.get("censorship")
        if censorship is not None and not isinstance(censorship, dict):
            raise TypeError("censorship must be an object")

    def _modes(self) -> dict[str, bool]:
        general = self.get("general")
        if not isinstance(general, dict):
            return dict(_DEFAULT_MODES)
        raw_modes = general.get("modes")
        if not isinstance(raw_modes, dict) or not raw_modes:
            return dict(_DEFAULT_MODES)
        return {str(name): bool(enabled) for name, enabled in raw_modes.items()}

    def _tls_domain(self) -> str:
        censorship = self.get("censorship")
        if not isinstance(censorship, dict):
            return ""
        return str(censorship.get("tls_domain") or "").strip()

    def _resolve_inbounds(self):
        inbound_tag = self["inbound_tag"]
        server = self["server"]
        metadata = {
            "tag": inbound_tag,
            "protocol": "mtproto",
            "network": "tcp",
            "tls": "none",
            "listen_port": server["port"],
            "port": server["port"],
            "modes": self._modes(),
            "tls_domain": self._tls_domain(),
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

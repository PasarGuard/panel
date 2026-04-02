from __future__ import annotations

import json
from copy import deepcopy
from ipaddress import ip_interface
from pathlib import PosixPath
from typing import Union

import commentjson

from app.models.core import CoreType
from app.utils.crypto import get_wireguard_public_key, validate_wireguard_key


class WireGuardConfig(dict):
    def __init__(
        self,
        config: Union[dict, str, PosixPath] | None = None,
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

        self._backend_type = CoreType.WIREGUARD
        self.exclude_inbound_tags = set(exclude_inbound_tags or set())
        self.fallbacks_inbound_tags = set(fallbacks_inbound_tags or set())
        self._inbounds: list[str] = []
        self._inbounds_by_tag: dict[str, dict] = {}

        if skip_validation:
            return

        self._validate()
        self._resolve_inbounds()

    @property
    def backend_type(self) -> str:
        return self._backend_type

    def _validate(self):
        if self.exclude_inbound_tags:
            raise ValueError("exclude_inbound_tags is only supported for xray cores")
        if self.fallbacks_inbound_tags:
            raise ValueError("fallbacks_inbound_tags is only supported for xray cores")

        interface_name = str(self.get("interface_name") or "").strip()
        if not interface_name:
            raise ValueError("interface_name is required")
        if "," in interface_name:
            raise ValueError("character ',' is not allowed in interface_name")
        if "<=>" in interface_name:
            raise ValueError("character '<=>' is not allowed in interface_name")
        self["interface_name"] = interface_name

        private_key = str(self.get("private_key") or "").strip()
        if not private_key:
            raise ValueError("private_key is required")
        self["private_key"] = validate_wireguard_key(private_key, "private_key")
        self["public_key"] = get_wireguard_public_key(self["private_key"])

        pre_shared_key = str(self.get("pre_shared_key") or "").strip()
        if pre_shared_key:
            self["pre_shared_key"] = validate_wireguard_key(pre_shared_key, "pre_shared_key")
        else:
            self.pop("pre_shared_key", None)

        listen_port = self.get("listen_port")
        if not isinstance(listen_port, int) or listen_port <= 0 or listen_port > 65535:
            raise ValueError("listen_port must be an integer between 1 and 65535")

        addresses = self.get("address")
        if not isinstance(addresses, list) or not addresses:
            raise ValueError("address must contain at least one CIDR")

        normalized_addresses: list[str] = []
        for cidr in addresses:
            if not isinstance(cidr, str) or not cidr.strip():
                raise ValueError("address entries must be valid CIDR strings")
            normalized_addresses.append(str(ip_interface(cidr.strip())))
        self["address"] = normalized_addresses

        peer_keepalive_seconds = self.get("peer_keepalive_seconds", 25)
        if not isinstance(peer_keepalive_seconds, int):
            raise ValueError("peer_keepalive_seconds must be an integer")
        if peer_keepalive_seconds <= 0:
            peer_keepalive_seconds = 25
        self["peer_keepalive_seconds"] = peer_keepalive_seconds

    def _resolve_inbounds(self):
        interface_name = self["interface_name"]
        metadata = {
            "tag": interface_name,
            "protocol": "wireguard",
            "network": "udp",
            "tls": "none",
            "interface_name": interface_name,
            "listen_port": self["listen_port"],
            "address": list(self["address"]),
            "peer_keepalive_seconds": self["peer_keepalive_seconds"],
            "public_key": self.get("public_key", ""),
            "private_key": self.get("private_key", ""),
            "pre_shared_key": self.get("pre_shared_key", ""),
        }
        self._inbounds = [interface_name]
        self._inbounds_by_tag = {interface_name: metadata}

    def to_str(self, **json_kwargs) -> str:
        return json.dumps(self, **json_kwargs)

    @property
    def inbounds_by_tag(self) -> dict:
        return self._inbounds_by_tag

    @property
    def inbounds(self) -> list[str]:
        return self._inbounds

    def to_json(self) -> dict:
        return {
            "backend_type": self.backend_type,
            "config": dict(self),
            "exclude_inbound_tags": [],
            "fallbacks_inbound_tags": [],
            "inbounds": self.inbounds,
            "inbounds_by_tag": self.inbounds_by_tag,
        }

    @classmethod
    def from_json(cls, data: dict) -> "WireGuardConfig":
        instance = cls(config=data.get("config", {}), skip_validation=True)
        if "inbounds" in data:
            instance._inbounds = data["inbounds"]
        if "inbounds_by_tag" in data:
            instance._inbounds_by_tag = data["inbounds_by_tag"]
        return instance

    def copy(self):
        return deepcopy(self)

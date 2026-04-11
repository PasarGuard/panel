import json
from enum import StrEnum
from ipaddress import ip_network
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key, validate_wireguard_key
from app.utils.system import random_password


class VMessSettings(BaseModel):
    id: UUID = Field(default_factory=uuid4)


class XTLSFlows(StrEnum):
    NONE = ""
    VISION = "xtls-rprx-vision"
    VISION_UDP = "xtls-rprx-vision-udp443"


class VlessSettings(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    flow: XTLSFlows = XTLSFlows.NONE


class TrojanSettings(BaseModel):
    password: str = Field(default_factory=random_password)


class ShadowsocksMethods(StrEnum):
    AES_128_GCM = "aes-128-gcm"
    AES_256_GCM = "aes-256-gcm"
    CHACHA20_POLY1305 = "chacha20-ietf-poly1305"
    XCHACHA20_POLY1305 = "xchacha20-poly1305"


class ShadowsocksSettings(BaseModel):
    password: str = Field(default_factory=random_password, min_length=22)
    method: ShadowsocksMethods = ShadowsocksMethods.CHACHA20_POLY1305


class HysteriaSettings(BaseModel):
    auth: str = Field(default_factory=random_password, min_length=1)


class WireGuardPeerIPs(BaseModel):
    peer_ips: list[str] = Field(default_factory=list)

    @field_validator("peer_ips", mode="before")
    @classmethod
    def validate_peer_ips(cls, value):
        if value in (None, ""):
            return []

        if isinstance(value, str):
            items = [value]
        else:
            try:
                items = list(value)
            except TypeError:
                return []

        normalized: list[str] = []
        for peer_ip in items:
            if not isinstance(peer_ip, str) or not peer_ip.strip():
                continue
            normalized_peer_ip = str(ip_network(peer_ip.strip(), strict=False))
            if normalized_peer_ip not in normalized:
                normalized.append(normalized_peer_ip)
        return normalized


class WireGuardSettings(BaseModel):
    private_key: str | None = None
    public_key: str | None = None
    peer_ips: list[str] = Field(default_factory=list)

    @field_validator("private_key", mode="before")
    @classmethod
    def validate_private_key(cls, value):
        if value in (None, ""):
            return None
        return validate_wireguard_key(value, "private_key")

    @field_validator("public_key", mode="before")
    @classmethod
    def validate_public_key(cls, value):
        if value in (None, ""):
            return None
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("peer_ips", mode="before")
    @classmethod
    def validate_peer_ips(cls, value):
        return WireGuardPeerIPs.model_validate({"peer_ips": value}).peer_ips

    @model_validator(mode="after")
    def handle_keys(self):
        if not self.private_key:
            self.private_key, self.public_key = generate_wireguard_keypair()
        elif not self.public_key:
            self.public_key = get_wireguard_public_key(self.private_key)
        return self


class ProxyTable(BaseModel):
    vmess: VMessSettings = Field(default_factory=VMessSettings)
    vless: VlessSettings = Field(default_factory=VlessSettings)
    trojan: TrojanSettings = Field(default_factory=TrojanSettings)
    shadowsocks: ShadowsocksSettings = Field(default_factory=ShadowsocksSettings)
    wireguard: WireGuardSettings = Field(default_factory=WireGuardSettings)
    hysteria: HysteriaSettings = Field(default_factory=HysteriaSettings)

    def dict(self, *, no_obj=True, **kwargs):
        if no_obj:
            return json.loads(self.model_dump_json())
        return super().model_dump(**kwargs)

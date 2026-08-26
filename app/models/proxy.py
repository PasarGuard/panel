import json
import re
import secrets
from enum import StrEnum
from ipaddress import ip_network
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.crypto import get_wireguard_public_key, validate_wireguard_key
from app.utils.system import random_password

_MTPROTO_SECRET_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def generate_mtproto_secret() -> str:
    return secrets.token_hex(16)


class VMessSettings(BaseModel):
    id: UUID = Field(default_factory=uuid4)


class VlessSettings(BaseModel):
    id: UUID = Field(default_factory=uuid4)


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
    model_config = ConfigDict(validate_assignment=True)


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


class MtprotoSettings(BaseModel):
    secret: str = Field(default_factory=generate_mtproto_secret)
    user_ad_tag: str = ""
    max_tcp_conns: int = 0
    max_unique_ips: int = 0

    @field_validator("secret", mode="before")
    @classmethod
    def validate_secret(cls, value):
        if not isinstance(value, str) or not _MTPROTO_SECRET_RE.fullmatch(value.strip()):
            raise ValueError("mtproto secret must be 32 hex characters")
        return value.strip().lower()

    @field_validator("user_ad_tag", mode="before")
    @classmethod
    def validate_user_ad_tag(cls, value):
        if value in (None,):
            return ""
        return str(value)

    @field_validator("max_tcp_conns", "max_unique_ips", mode="before")
    @classmethod
    def validate_limits(cls, value):
        if value in (None, ""):
            return 0
        limit = int(value)
        if limit < 0:
            raise ValueError("must be greater than or equal to 0")
        return limit


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
        if self.private_key and not self.public_key:
            self.public_key = get_wireguard_public_key(self.private_key)
        return self


class ProxyTable(BaseModel):
    vmess: VMessSettings = Field(default_factory=VMessSettings)
    vless: VlessSettings = Field(default_factory=VlessSettings)
    trojan: TrojanSettings = Field(default_factory=TrojanSettings)
    shadowsocks: ShadowsocksSettings = Field(default_factory=ShadowsocksSettings)
    wireguard: WireGuardSettings = Field(default_factory=WireGuardSettings)
    hysteria: HysteriaSettings = Field(default_factory=HysteriaSettings)
    mtproto: MtprotoSettings = Field(default_factory=MtprotoSettings)

    def dict(self, *, no_obj=True, **kwargs):
        if no_obj:
            return json.loads(self.model_dump_json())
        return super().model_dump(**kwargs)

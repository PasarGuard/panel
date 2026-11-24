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
    """Return a new random MTProto user secret: 32 lowercase hex characters.

    This is the single server-side source of new secrets. The backfill migration
    d5e1f3a7b9c2 inlines the same ``secrets.token_hex(16)``; change both together.
    """
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


class MasqueSettings(BaseModel):
    password: str = Field(default_factory=random_password, min_length=1)

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
    # None means "no secret yet": the read path never invents one; write paths assign it.
    secret: str | None = Field(default=None, min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    user_ad_tag: str = ""
    max_tcp_conns: int = Field(default=0, ge=0, le=4294967295, strict=True)
    max_unique_ips: int = Field(default=0, ge=0, le=4294967295, strict=True)

    @field_validator("secret", mode="before")
    @classmethod
    def validate_secret(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("mtproto secret must be a string")  # noqa: TRY004
        value = value.strip()
        if not value:
            return None
        if not _MTPROTO_SECRET_RE.fullmatch(value):
            raise ValueError("mtproto secret must be 32 hex characters")
        return value.lower()

    @field_validator("user_ad_tag", mode="before")
    @classmethod
    def validate_user_ad_tag(cls, value):
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("mtproto user_ad_tag must be a string")  # noqa: TRY004
        value = value.strip()
        if value and not _MTPROTO_SECRET_RE.fullmatch(value):
            raise ValueError("mtproto user_ad_tag must be empty or 32 hex characters")
        return value.lower()


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
            value = value.strip()
            # Canonical base64, so the panel and the node compare one key the same way. Stored rows load through
            # this model too, so a value that is not a key is kept here; input models reject it (check_input_keys).
            try:
                return validate_wireguard_key(value, "public_key")
            except ValueError:
                return value
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

    def check_input_keys(self) -> None:
        """Strict checks for keys sent by a client. A public key alone (no private key) stays allowed."""
        if not self.public_key:
            return
        validate_wireguard_key(self.public_key, "wireguard public_key")
        if self.private_key and self.public_key != get_wireguard_public_key(self.private_key):
            raise ValueError("wireguard public_key does not match private_key")


class ProxyTable(BaseModel):
    vmess: VMessSettings = Field(default_factory=VMessSettings)
    vless: VlessSettings = Field(default_factory=VlessSettings)
    trojan: TrojanSettings = Field(default_factory=TrojanSettings)
    shadowsocks: ShadowsocksSettings = Field(default_factory=ShadowsocksSettings)
    wireguard: WireGuardSettings = Field(default_factory=WireGuardSettings)
    hysteria: HysteriaSettings = Field(default_factory=HysteriaSettings)
    masque: MasqueSettings = Field(default_factory=MasqueSettings)
    mtproto: MtprotoSettings = Field(default_factory=MtprotoSettings)

    def dict(self, *, no_obj=True, **kwargs):
        if no_obj:
            return json.loads(self.model_dump_json())
        return super().model_dump(**kwargs)

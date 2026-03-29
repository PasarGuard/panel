import json
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

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
    auth: UUID = Field(default_factory=uuid4)


class ProxyTable(BaseModel):
    vmess: VMessSettings = Field(default_factory=VMessSettings)
    vless: VlessSettings = Field(default_factory=VlessSettings)
    trojan: TrojanSettings = Field(default_factory=TrojanSettings)
    shadowsocks: ShadowsocksSettings = Field(default_factory=ShadowsocksSettings)
    hysteria: HysteriaSettings = Field(default_factory=HysteriaSettings)

    def dict(self, *, no_obj=True, **kwargs):
        if no_obj:
            return json.loads(self.model_dump_json())
        return super().model_dump(**kwargs)

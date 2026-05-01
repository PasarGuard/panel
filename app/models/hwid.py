from datetime import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class HWIDDeviceResponse(BaseModel):
    id: int
    user_id: int
    username: str | None = None
    hwid_hash: str
    device_os: str | None = None
    os_version: str | None = None
    device_model: str | None = None
    user_agent: str | None = None
    request_ip: str | None = None
    first_seen_at: dt
    last_seen_at: dt
    created_at: dt
    updated_at: dt
    model_config = ConfigDict(from_attributes=True)


class HWIDDeviceListResponse(BaseModel):
    items: list[HWIDDeviceResponse] = Field(default_factory=list)
    total: int = 0


class HWIDStatsResponse(BaseModel):
    total_devices: int
    users_with_devices: int


class HWIDDeleteRequest(BaseModel):
    user_id: int
    hwid_hash: str


class HWIDDeleteAllRequest(BaseModel):
    user_id: int


class HWIDAddRequest(BaseModel):
    user_id: int
    hwid: str
    device_os: str | None = None
    os_version: str | None = None
    device_model: str | None = None
    user_agent: str | None = None
    request_ip: str | None = None


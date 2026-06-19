from datetime import datetime as dt, timezone as tz
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import APIKeyStatus
from app.models.admin_role import RolePermissions
from app.utils.helpers import fix_datetime_timezone


class APIKeyBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=512)
    roles: RolePermissions = Field(default_factory=RolePermissions)
    expire_date: dt | None = None

    model_config = ConfigDict(from_attributes=True)


class APIKeyCreate(APIKeyBase):
    @field_validator("expire_date", mode="before")
    @classmethod
    def validate_expire_date(cls, value):
        if value is None:
            return None
        parsed = fix_datetime_timezone(value)
        if parsed <= dt.now(tz.utc):
            raise ValueError("expire_date must be in the future")
        return parsed


class APIKeyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=512)
    roles: RolePermissions | None = None
    expire_date: dt | None = None
    status: APIKeyStatus | None = None

    @field_validator("expire_date", mode="before")
    @classmethod
    def validate_expire_date(cls, value):
        if value is None:
            return None
        parsed = fix_datetime_timezone(value)
        if parsed <= dt.now(tz.utc):
            raise ValueError("expire_date must be in the future")
        return parsed


class APIKeyResponse(APIKeyBase):
    id: int
    admin_id: int
    created_at: dt
    api_key_trimmed: str
    revoked_at: dt | None = None
    status: APIKeyStatus = APIKeyStatus.active
    is_expired: bool = False


class APIKeyCreateResponse(APIKeyResponse):
    api_key: str


class APIKeysResponse(BaseModel):
    api_keys: list[APIKeyResponse]
    total: int


Offset = Annotated[int, Field(default=0, ge=0)]
Limit = Annotated[int, Field(default=50, ge=1, le=200)]


class APIKeysQuery(BaseModel):
    offset: Offset = 0
    limit: Limit = 50
    key_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: APIKeyStatus | None = None

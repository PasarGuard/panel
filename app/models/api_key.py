from datetime import UTC, datetime as dt
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import APIKeyStatus
from app.models.admin_role import RolePermissions
from app.utils.helpers import fix_datetime_timezone

from .validators import ListValidator


class APIKeyBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=512)
    permissions: RolePermissions = Field(default_factory=RolePermissions)
    inherit_permissions: bool = True
    expire_date: dt | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("permissions", mode="before")
    @classmethod
    def validate_permissions(cls, value):
        return value or RolePermissions()


class APIKeyCreate(APIKeyBase):
    admin_id: int | None = Field(default=None, ge=1)

    @field_validator("expire_date", mode="before")
    @classmethod
    def validate_expire_date(cls, value):
        if value is None:
            return None
        parsed = fix_datetime_timezone(value)
        if parsed <= dt.now(UTC):
            raise ValueError("expire_date must be in the future")
        return parsed


class APIKeyUpdate(BaseModel):
    admin_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=512)
    permissions: RolePermissions | None = None
    inherit_permissions: bool | None = None
    expire_date: dt | None = None
    status: APIKeyStatus | None = None

    @field_validator("expire_date", mode="before")
    @classmethod
    def validate_expire_date(cls, value):
        if value is None:
            return None
        parsed = fix_datetime_timezone(value)
        if parsed <= dt.now(UTC):
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


class BulkAPIKeySelection(BaseModel):
    """Model for bulk API key selection by IDs."""

    ids: set[int] = Field(default_factory=set)

    @field_validator("ids", mode="after")
    @classmethod
    def ids_validator(cls, v):
        return ListValidator.not_null_list(list(v), "API key")


class RemoveAPIKeysResponse(BaseModel):
    """Response model for bulk API key deletion."""

    api_keys: list[str]
    count: int


Offset = Annotated[int, Field(default=0, ge=0)]
Limit = Annotated[int, Field(default=50, ge=1, le=200)]


class APIKeysQuery(BaseModel):
    offset: Offset = 0
    limit: Limit = 50
    key_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: APIKeyStatus | None = None

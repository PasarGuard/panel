import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime as dt
from enum import Enum
from typing import Literal

import bcrypt
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.db.models import AdminStatus
from app.models.admin_role import RoleAccess, RoleFeatures, RoleHWIDSettings, RoleLimits, RolePermissions
from app.models.stats import Period
from app.utils.helpers import fix_datetime_timezone

from .notification_enable import UserNotificationEnable
from .validators import DiscordValidator, ListValidator, NumericValidatorMixin, PasswordValidator

AdminStatusModify = Literal[AdminStatus.active, AdminStatus.disabled]

BCRYPT_ROUNDS = 12
_PASSWORD_WORKERS = max(2, min(os.cpu_count() or 1, 8))
_password_executor = ThreadPoolExecutor(max_workers=_PASSWORD_WORKERS, thread_name_prefix="bcrypt")
_password_semaphore = asyncio.Semaphore(_PASSWORD_WORKERS)


def _hash_password_sync(raw: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(raw.encode("utf-8"), salt).decode("utf-8")


def _verify_password_sync(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


async def hash_password(raw: str) -> str:
    loop = asyncio.get_running_loop()
    async with _password_semaphore:
        return await loop.run_in_executor(_password_executor, _hash_password_sync, raw)


async def verify_password(raw: str, hashed: str) -> bool:
    loop = asyncio.get_running_loop()
    async with _password_semaphore:
        return await loop.run_in_executor(_password_executor, _verify_password_sync, raw, hashed)


class AdminRoleData(BaseModel):
    """Runtime role data carried on AdminDetails — only the fields needed for permission checks."""

    id: int | None = None
    name: str = ""
    is_owner: bool = False
    permissions: RolePermissions = Field(default_factory=RolePermissions)
    limits: RoleLimits = Field(default_factory=RoleLimits)
    features: RoleFeatures = Field(default_factory=RoleFeatures)
    access: RoleAccess = Field(default_factory=RoleAccess)
    hwid: RoleHWIDSettings = Field(default_factory=RoleHWIDSettings)
    disabled_when_limited: bool = False
    disconnect_users_when_limited: bool = True
    disconnect_users_when_disabled: bool = True

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminBase(BaseModel):
    """Minimal admin model containing only the username."""

    id: int | None = None
    username: str

    model_config = ConfigDict(from_attributes=True)


class AdminContactInfo(AdminBase):
    """Base model containing the core admin identification fields."""

    telegram_id: int | None = None
    discord_webhook: str | None = None
    sub_domain: str | None = None
    profile_title: str | None = None
    support_url: str | None = None
    notification_enable: UserNotificationEnable | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("notification_enable", mode="before")
    @classmethod
    def convert_notification_enable(cls, value):
        """Convert dict to UserNotificationEnable object when loading from database."""
        if value is None:
            return None
        if isinstance(value, UserNotificationEnable):
            return value
        if isinstance(value, dict):
            return UserNotificationEnable(**value)
        return value


class AdminDetails(AdminContactInfo):
    """Complete admin model with all fields for database representation and API responses."""

    total_users: int = 0
    used_traffic: int = 0
    data_limit: int | None = None
    status: AdminStatus = AdminStatus.active
    sub_template: str | None = None
    lifetime_used_traffic: int | None = None
    note: str | None = None
    role: AdminRoleData | None = None
    permission_overrides: RoleLimits | None = None

    @property
    def is_owner(self) -> bool:
        return self.role.is_owner if self.role is not None else False

    @computed_field
    @property
    def is_disabled(self) -> bool:
        return self.status == AdminStatus.disabled

    @computed_field
    @property
    def is_limited(self) -> bool:
        return self.status == AdminStatus.limited

    model_config = ConfigDict(from_attributes=True)

    @field_validator("used_traffic", mode="before")
    def cast_to_int(cls, v):
        return NumericValidatorMixin.cast_to_int(v)


class AdminModify(BaseModel):
    password: str | None = None
    telegram_id: int | None = None
    discord_webhook: str | None = None
    status: AdminStatusModify | None = None
    data_limit: int | None = None
    sub_template: str | None = None
    sub_domain: str | None = None
    profile_title: str | None = None
    support_url: str | None = None
    note: str | None = None
    notification_enable: UserNotificationEnable | None = None
    role_id: int | None = None
    permission_overrides: RoleLimits | None = None

    @field_validator("discord_webhook")
    @classmethod
    def validate_discord_webhook(cls, value):
        return DiscordValidator.validate_webhook(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None):
        return PasswordValidator.validate_password(value)


class AdminCreate(AdminModify):
    """Model for creating new admin accounts requiring username and password."""

    username: str
    password: str
    role_id: int


class AdminInDB(AdminDetails):
    hashed_password: str

    def verify_password(self, plain_password):
        return _verify_password_sync(plain_password, self.hashed_password)

    async def verify_password_async(self, plain_password):
        return await verify_password(plain_password, self.hashed_password)


class AdminValidationResult(BaseModel):
    id: int | None = None
    username: str
    status: AdminStatus = Field(default=AdminStatus.active)


class AdminsResponse(BaseModel):
    """Response model for admins list with pagination and statistics."""

    admins: list[AdminDetails]
    total: int
    active: int
    disabled: int
    limited: int


class AdminSimple(BaseModel):
    """Lightweight admin model with only id and username for performance."""

    id: int
    username: str
    model_config = ConfigDict(from_attributes=True)


class AdminsSimpleResponse(BaseModel):
    """Response model for lightweight admin list."""

    admins: list[AdminSimple]
    total: int


class AdminSortField(str, Enum):
    username = "username"
    created_at = "created_at"
    used_traffic = "used_traffic"


class AdminSimpleSortField(str, Enum):
    id = "id"
    username = "username"


class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"


class AdminSortOption(str, Enum):
    username = "username"
    created_at = "created_at"
    used_traffic = "used_traffic"
    desc_username = "-username"
    desc_created_at = "-created_at"
    desc_used_traffic = "-used_traffic"

    @property
    def field(self) -> AdminSortField:
        return AdminSortField(self.value.lstrip("-"))

    @property
    def direction(self) -> SortDirection:
        return SortDirection.desc if self.value.startswith("-") else SortDirection.asc


class AdminSimpleSortOption(str, Enum):
    id = "id"
    username = "username"
    desc_id = "-id"
    desc_username = "-username"

    @property
    def field(self) -> AdminSimpleSortField:
        return AdminSimpleSortField(self.value.lstrip("-"))

    @property
    def direction(self) -> SortDirection:
        return SortDirection.desc if self.value.startswith("-") else SortDirection.asc


class AdminListQuery(BaseModel):
    ids: list[int] | None = None
    usernames: list[str] | None = None
    username: str | None = None
    offset: int | None = None
    limit: int | None = None
    sort: list[AdminSortOption] = Field(default_factory=list)

    @field_validator("sort", mode="before")
    @classmethod
    def validate_sort(cls, value):
        return ListValidator.normalize_enum_list_input(value, AdminSortOption)


class AdminSimpleListQuery(BaseModel):
    ids: list[int] | None = None
    usernames: list[str] | None = None
    search: str | None = None
    offset: int | None = None
    limit: int | None = None
    sort: list[AdminSimpleSortOption] = Field(default_factory=list)
    all: bool = False

    @field_validator("sort", mode="before")
    @classmethod
    def validate_sort(cls, value):
        return ListValidator.normalize_enum_list_input(value, AdminSimpleSortOption)


class AdminUsageQuery(BaseModel):
    period: Period = Field(default=Period.hour)
    node_id: int | None = None
    group_by_node: bool = False
    start: dt | None = Field(default=None, examples=["2024-01-01T00:00:00+03:30"])
    end: dt | None = Field(default=None, examples=["2024-01-31T23:59:59+03:30"])

    @field_validator("start", "end", mode="before")
    @classmethod
    def validate_datetimes(cls, value):
        if not value:
            return value
        return fix_datetime_timezone(value)


class BulkAdminSelection(BaseModel):
    """Model for bulk admin selection by IDs"""

    ids: set[int] = Field(default_factory=set)

    @field_validator("ids", mode="after")
    @classmethod
    def ids_validator(cls, v):
        return ListValidator.not_null_list(list(v), "admin")


class RemoveAdminsResponse(BaseModel):
    """Response model for bulk admin deletion"""

    admins: list[str]
    count: int


class BulkAdminsActionResponse(BaseModel):
    """Response model for bulk admin actions."""

    admins: list[str]
    count: int

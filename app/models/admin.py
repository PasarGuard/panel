import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

import bcrypt
from pydantic import BaseModel, ConfigDict, field_validator

from .notification_enable import UserNotificationEnable
from .validators import DiscordValidator, NumericValidatorMixin, PasswordValidator

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


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminBase(BaseModel):
    """Minimal admin model containing only the username."""

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

    id: int | None = None
    is_sudo: bool
    total_users: int = 0
    used_traffic: int = 0
    is_disabled: bool = False
    discord_id: int | None = None
    sub_template: str | None = None
    lifetime_used_traffic: int | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("used_traffic", mode="before")
    def cast_to_int(cls, v):
        return NumericValidatorMixin.cast_to_int(v)


class AdminModify(BaseModel):
    password: str | None = None
    is_sudo: bool
    telegram_id: int | None = None
    discord_webhook: str | None = None
    discord_id: int | None = None
    is_disabled: bool | None = None
    sub_template: str | None = None
    sub_domain: str | None = None
    profile_title: str | None = None
    support_url: str | None = None
    notification_enable: UserNotificationEnable | None = None

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


class AdminInDB(AdminDetails):
    hashed_password: str

    def verify_password(self, plain_password):
        return _verify_password_sync(plain_password, self.hashed_password)

    async def verify_password_async(self, plain_password):
        return await verify_password(plain_password, self.hashed_password)


class AdminValidationResult(BaseModel):
    username: str
    is_sudo: bool
    is_disabled: bool


class AdminsResponse(BaseModel):
    """Response model for admins list with pagination and statistics."""

    admins: list[AdminDetails]
    total: int
    active: int
    disabled: int


class AdminSimple(BaseModel):
    """Lightweight admin model with only id and username for performance."""

    id: int
    username: str
    model_config = ConfigDict(from_attributes=True)


class AdminsSimpleResponse(BaseModel):
    """Response model for lightweight admin list."""

    admins: list[AdminSimple]
    total: int

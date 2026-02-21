import asyncio
from datetime import timezone as tz

from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.nats.admin_auth_cache import (
    AdminAuthCacheCorruptedError,
    AdminAuthCacheUnavailableError,
    admin_auth_cache_service,
)
from app.db import AsyncSession, get_db
from app.db.crud.admin import get_admin as get_admin_by_username, get_admin_by_telegram_id
from app.models.admin import AdminDetails, AdminValidationResult, verify_password
from app.nats import is_nats_enabled
from app.models.settings import Telegram
from app.settings import telegram_settings
from app.utils.jwt import get_admin_payload
from config import DEBUG, SUDOERS

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/token")
_ADMIN_AUTH_KV_READ_TIMEOUT_SECONDS = 1.0


def _to_utc(value):
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=tz.utc)
    return value.astimezone(tz.utc)


def _build_admin_details(db_admin) -> AdminDetails:
    return AdminDetails(
        id=db_admin.id,
        username=db_admin.username,
        is_sudo=db_admin.is_sudo,
        used_traffic=db_admin.used_traffic,
        is_disabled=db_admin.is_disabled,
        telegram_id=db_admin.telegram_id,
        discord_webhook=db_admin.discord_webhook,
        sub_domain=db_admin.sub_domain,
        profile_title=db_admin.profile_title,
        support_url=db_admin.support_url,
        notification_enable=db_admin.notification_enable,
        discord_id=db_admin.discord_id,
        sub_template=db_admin.sub_template,
    )


async def get_admin_db(db: AsyncSession, token: str) -> AdminDetails | None:
    payload = await get_admin_payload(token)
    if not payload:
        return None

    db_admin = await get_admin_by_username(db, payload["username"], load_users=False, load_usage_logs=False)
    if db_admin:
        if db_admin.password_reset_at:
            if not payload.get("created_at"):
                return None
            if _to_utc(db_admin.password_reset_at) > _to_utc(payload.get("created_at")):
                return None

        return _build_admin_details(db_admin)

    elif payload["username"] in SUDOERS and payload["is_sudo"] is True:
        return AdminDetails(username=payload["username"], is_sudo=True)

    return None


async def get_admin_nats(token: str) -> AdminDetails | None:
    payload = await get_admin_payload(token)
    if not payload:
        return None

    if payload["username"] in SUDOERS and payload["is_sudo"] is True:
        return AdminDetails(username=payload["username"], is_sudo=True)

    cache_entry = await asyncio.wait_for(
        admin_auth_cache_service.get_admin(payload["username"]), timeout=_ADMIN_AUTH_KV_READ_TIMEOUT_SECONDS
    )

    if cache_entry.password_reset_at:
        if not payload.get("created_at"):
            return None
        if _to_utc(cache_entry.password_reset_at) > _to_utc(payload.get("created_at")):
            return None

    return AdminDetails(
        id=cache_entry.id,
        username=cache_entry.username,
        is_sudo=cache_entry.is_sudo,
        is_disabled=cache_entry.is_disabled,
    )


async def get_current_db(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    admin: AdminDetails | None = await get_admin_db(db, token)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if admin.is_disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="your account has been disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return admin


async def get_current_nats_enabled(
    request: Request, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)
):
    if request.method != "GET":
        return await get_current_db(db=db, token=token)

    try:
        admin: AdminDetails | None = await get_admin_nats(token)
    except (asyncio.TimeoutError, AdminAuthCacheUnavailableError, AdminAuthCacheCorruptedError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin auth cache unavailable",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if admin.is_disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="your account has been disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return admin


get_current = get_current_nats_enabled if is_nats_enabled() else get_current_db


async def check_sudo_admin(admin: AdminDetails = Depends(get_current)):
    if not admin.is_sudo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You're not allowed")
    return admin


async def validate_admin(db: AsyncSession, username: str, password: str) -> AdminValidationResult | None:
    """Validate admin credentials with environment variables or database."""

    db_admin = await get_admin_by_username(db, username, load_users=False, load_usage_logs=False)
    if db_admin and await verify_password(password, db_admin.hashed_password):
        return AdminValidationResult(
            username=db_admin.username, is_sudo=db_admin.is_sudo, is_disabled=db_admin.is_disabled
        )

    if not db_admin and SUDOERS.get(username) == password:
        if not DEBUG:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env admin not allowed in production")

        return AdminValidationResult(username=username, is_sudo=True, is_disabled=False)


async def validate_mini_app_admin(db: AsyncSession, token: str) -> AdminValidationResult | None:
    """Validate raw MiniApp init data and return it as AdminValidationResult object"""
    settings: Telegram = await telegram_settings()

    if not settings.mini_app_login or not settings.enable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service unavailable",
        )

    try:
        data: WebAppInitData = safe_parse_webapp_init_data(token=settings.token, init_data=token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db_admin = await get_admin_by_telegram_id(db, data.user.id, load_users=False, load_usage_logs=False)
    if db_admin:
        return AdminValidationResult(
            username=db_admin.username, is_sudo=db_admin.is_sudo, is_disabled=db_admin.is_disabled
        )

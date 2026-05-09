from datetime import timezone as tz

from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy import func, select

from app.db import AsyncSession, get_db
from app.db.crud.admin import (
    find_admins_by_telegram_id,
    get_admin as get_admin_by_username,
    get_admin_by_id as get_admin_by_id_crud,
    get_admin_by_telegram_id,
)
from app.db.models import Admin, AdminUsageLogs, User
from app.models.admin import AdminDetails, AdminValidationResult, verify_password
from app.models.settings import Telegram
from app.settings import telegram_settings
from app.utils.jwt import get_admin_payload
from config import auth_settings, runtime_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/token")


def _build_admin_details(
    db_admin: Admin,
    *,
    total_users: int = 0,
    reseted_usage: int | None = None,
) -> AdminDetails:
    used_traffic = int(db_admin.used_traffic or 0)
    return AdminDetails(
        id=db_admin.id,
        username=db_admin.username,
        is_sudo=db_admin.is_sudo,
        total_users=int(total_users or 0),
        used_traffic=used_traffic,
        is_disabled=db_admin.is_disabled,
        telegram_id=db_admin.telegram_id,
        discord_webhook=db_admin.discord_webhook,
        sub_domain=db_admin.sub_domain,
        profile_title=db_admin.profile_title,
        support_url=db_admin.support_url,
        note=db_admin.note,
        notification_enable=db_admin.notification_enable,
        discord_id=db_admin.discord_id,
        sub_template=db_admin.sub_template,
        lifetime_used_traffic=None if reseted_usage is None else int(reseted_usage or 0) + used_traffic,
    )


def _is_token_valid_for_admin(db_admin: Admin, payload: dict) -> bool:
    if not db_admin.password_reset_at:
        return True
    if not payload.get("created_at"):
        return False
    return db_admin.password_reset_at.astimezone(tz.utc) <= payload.get("created_at")


async def get_admin(db: AsyncSession, token: str) -> AdminDetails | None:
    payload = await get_admin_payload(token)
    if not payload:
        return

    db_admin = None
    if payload.get("admin_id") is not None:
        db_admin = await get_admin_by_id_crud(db, payload["admin_id"], load_users=False, load_usage_logs=False)

    if not db_admin:
        db_admin = await get_admin_by_username(db, payload["username"], load_users=False, load_usage_logs=False)

    if db_admin:
        if not _is_token_valid_for_admin(db_admin, payload):
            return

        return _build_admin_details(db_admin)

    elif payload["username"] in auth_settings.sudoers and payload["is_sudo"] is True:
        return AdminDetails(username=payload["username"], is_sudo=True)


async def get_admin_with_metrics(db: AsyncSession, token: str) -> AdminDetails | None:
    payload = await get_admin_payload(token)
    if not payload:
        return

    total_users_subquery = (
        select(func.count(User.id)).where(User.admin_id == Admin.id).correlate(Admin).scalar_subquery()
    )
    reseted_usage_subquery = (
        select(func.coalesce(func.sum(AdminUsageLogs.used_traffic_at_reset), 0))
        .where(AdminUsageLogs.admin_id == Admin.id)
        .correlate(Admin)
        .scalar_subquery()
    )
    if payload.get("admin_id") is not None:
        admin_row = (
            await db.execute(
                select(Admin, total_users_subquery, reseted_usage_subquery).where(Admin.id == payload["admin_id"])
            )
        ).one_or_none()
        if admin_row is None:
            admin_row = (
                await db.execute(
                    select(Admin, total_users_subquery, reseted_usage_subquery).where(
                        Admin.username == payload["username"]
                    )
                )
            ).one_or_none()
    else:
        admin_row = (
            await db.execute(
                select(Admin, total_users_subquery, reseted_usage_subquery).where(Admin.username == payload["username"])
            )
        ).one_or_none()

    if admin_row:
        db_admin, total_users, reseted_usage = admin_row
        if not _is_token_valid_for_admin(db_admin, payload):
            return

        return _build_admin_details(db_admin, total_users=total_users, reseted_usage=reseted_usage)

    elif payload["username"] in auth_settings.sudoers and payload["is_sudo"] is True:
        return AdminDetails(username=payload["username"], is_sudo=True)


async def get_current(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    admin: AdminDetails | None = await get_admin(db, token)
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


async def get_current_with_metrics(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    admin: AdminDetails | None = await get_admin_with_metrics(db, token)
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


async def check_sudo_admin(admin: AdminDetails = Depends(get_current)):
    if not admin.is_sudo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You're not allowed")
    return admin


async def validate_admin(db: AsyncSession, username: str, password: str) -> AdminValidationResult | None:
    """Validate admin credentials with environment variables or database."""

    db_admin = await get_admin_by_username(db, username, load_users=False, load_usage_logs=False)
    if db_admin and await verify_password(password, db_admin.hashed_password):
        return AdminValidationResult(
            id=db_admin.id,
            username=db_admin.username,
            is_sudo=db_admin.is_sudo,
            is_disabled=db_admin.is_disabled,
        )

    if not db_admin and auth_settings.sudoers.get(username) == password:
        if not runtime_settings.debug:
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

    duplicate_admins = await find_admins_by_telegram_id(db, data.user.id, limit=2)
    if len(duplicate_admins) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Telegram ID is assigned to multiple admins. Please contact support.",
        )

    db_admin = await get_admin_by_telegram_id(db, data.user.id, load_users=False, load_usage_logs=False)
    if db_admin:
        return AdminValidationResult(
            id=db_admin.id,
            username=db_admin.username,
            is_sudo=db_admin.is_sudo,
            is_disabled=db_admin.is_disabled,
        )

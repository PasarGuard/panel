from datetime import timezone as tz

from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db import AsyncSession, get_db
from app.db.crud.admin import (
    build_admin_details,
    find_admins_by_telegram_id,
    get_admin as get_admin_by_username,
    get_admin_by_id as get_admin_by_id_crud,
    get_admin_by_telegram_id,
)
from app.db.models import Admin, AdminUsageLogs, User
from app.models.admin import AdminDetails, AdminRoleData, AdminStatus, AdminValidationResult, verify_password
from app.models.admin_role import RoleAccess, RoleFeatures, RoleLimits, RolePermissions
from app.models.settings import Telegram
from app.operation.permissions import PermissionDenied, enforce_permission, is_scope_all
from app.settings import telegram_settings
from app.utils.jwt import get_admin_payload
from config import auth_settings, runtime_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/token")

# Owner-level role data given to env admins — full permissions, bypasses all checks
_ENV_ADMIN_ROLE = AdminRoleData(
    is_owner=True,
    permissions=RolePermissions(),  # is_owner=True bypasses permission checks entirely
    limits=RoleLimits(),
    features=RoleFeatures(),
    access=RoleAccess(),
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
        return None

    db_admin = None
    if payload.get("admin_id") is not None:
        db_admin = await get_admin_by_id_crud(db, payload["admin_id"], load_users=False, load_usage_logs=False)

    if not db_admin:
        db_admin = await get_admin_by_username(db, payload["username"], load_users=False, load_usage_logs=False)

    if db_admin:
        if not _is_token_valid_for_admin(db_admin, payload):
            return None
        return build_admin_details(db_admin)

    # Env admin fallback — no DB record, but username is a known env admin
    if payload["username"] in auth_settings.sudoers:
        return AdminDetails(username=payload["username"], role=_ENV_ADMIN_ROLE)

    return None


async def get_admin_with_metrics(db: AsyncSession, token: str) -> AdminDetails | None:
    payload = await get_admin_payload(token)
    if not payload:
        return None

    total_users_subquery = (
        select(func.count(User.id)).where(User.admin_id == Admin.id).correlate(Admin).scalar_subquery()
    )
    reseted_usage_subquery = (
        select(func.coalesce(func.sum(AdminUsageLogs.used_traffic_at_reset), 0))
        .where(AdminUsageLogs.admin_id == Admin.id)
        .correlate(Admin)
        .scalar_subquery()
    )

    base_stmt = select(Admin, total_users_subquery, reseted_usage_subquery).options(selectinload(Admin.role))

    if payload.get("admin_id") is not None:
        admin_row = (await db.execute(base_stmt.where(Admin.id == payload["admin_id"]))).one_or_none()
        if admin_row is None:
            admin_row = (await db.execute(base_stmt.where(Admin.username == payload["username"]))).one_or_none()
    else:
        admin_row = (await db.execute(base_stmt.where(Admin.username == payload["username"]))).one_or_none()

    if admin_row:
        db_admin, total_users, reseted_usage = admin_row
        if not _is_token_valid_for_admin(db_admin, payload):
            return None
        return build_admin_details(db_admin, total_users=total_users, reseted_usage=reseted_usage)

    # Env admin fallback — no DB record, but username is a known env admin
    if payload["username"] in auth_settings.sudoers:
        return AdminDetails(username=payload["username"], role=_ENV_ADMIN_ROLE)

    return None


async def get_current(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    admin: AdminDetails | None = await get_admin(db, token)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if admin.status == AdminStatus.disabled:
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
    if admin.status == AdminStatus.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="your account has been disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return admin


def require_permission(resource: str, action: str):
    """FastAPI dependency factory — checks RBAC permission for resource+action."""

    async def _check(admin: AdminDetails = Depends(get_current)):
        try:
            enforce_permission(admin, resource, action)
        except PermissionDenied as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        return admin

    return _check


def require_scope_all(resource: str, action: str):
    """
    FastAPI dependency factory — checks RBAC permission AND requires scope=all (or owner).
    Used for operations that affect all users regardless of ownership.
    """

    async def _check(admin: AdminDetails = Depends(get_current)):
        try:
            enforce_permission(admin, resource, action)
        except PermissionDenied as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        # Scope check: must be owner or have scope=ALL (or True = no scope restriction)
        if not is_scope_all(admin, resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}.{action} requires scope=all",
            )
        return admin

    return _check


async def require_owner(admin: AdminDetails = Depends(get_current)):
    """FastAPI dependency — allows only the owner (is_owner=True)."""
    if not admin.is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can perform this action")
    return admin


async def validate_admin(db: AsyncSession, username: str, password: str) -> AdminValidationResult | None:
    """Validate admin credentials against the database, with env admin fallback."""
    db_admin = await get_admin_by_username(db, username, load_users=False, load_usage_logs=False)
    if db_admin and await verify_password(password, db_admin.hashed_password):
        return AdminValidationResult(
            id=db_admin.id,
            username=db_admin.username,
            status=db_admin.status,
        )

    # Env admin fallback — only allowed in debug/testing
    if not db_admin and auth_settings.sudoers.get(username) == password:
        if not runtime_settings.debug:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="env admin not allowed in production")
        return AdminValidationResult(username=username, status=AdminStatus.active)

    return None


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
            status=db_admin.status,
        )
    return None

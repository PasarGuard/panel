from uuid import UUID

from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func, select

from app.db import AsyncSession, get_db
from app.db.crud.admin import (
    find_admins_by_telegram_id,
    get_admin as get_admin_by_username,
    get_admin_by_id as get_admin_by_id_crud,
    get_admin_by_telegram_id,
)
from app.db.crud.api_key import get_api_key_by_hash, hash_api_key
from app.db.models import Admin, AdminUsageLogs, User, APIKeyStatus
from app.models.admin import AdminDetails, AdminRoleData, AdminStatus, AdminValidationResult, verify_password
from app.models.admin_role import RoleAccess, RoleFeatures, RoleLimits, RolePermissions
from app.models.settings import Telegram
from app.operation.permissions import PermissionDenied, enforce_permission, is_scope_all
from app.settings import telegram_settings
from app.utils.jwt import get_admin_payload
from config import auth_settings, runtime_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/token", auto_error=False)

# Owner-level role data given to env admins — full permissions, bypasses all checks
_ENV_ADMIN_ROLE = AdminRoleData(
    is_owner=True,
    permissions=RolePermissions(),  # is_owner=True bypasses permission checks entirely
    limits=RoleLimits(),
    features=RoleFeatures(),
    access=RoleAccess(),
)


def _build_admin_details(
    db_admin: Admin,
    *,
    total_users: int = 0,
    reseted_usage: int | None = None,
) -> AdminDetails:
    used_traffic = int(db_admin.used_traffic or 0)
    role = AdminRoleData.model_validate(db_admin.role) if db_admin.role is not None else None
    return AdminDetails(
        id=db_admin.id,
        username=db_admin.username,
        total_users=int(total_users or 0),
        used_traffic=used_traffic,
        data_limit=db_admin.data_limit,
        status=db_admin.status,
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
        role=role,
        permission_overrides=RoleLimits.model_validate(db_admin.permission_overrides)
        if db_admin.permission_overrides
        else None,
    )


def _is_token_valid_for_admin(db_admin: Admin, payload: dict) -> bool:
    if not db_admin.password_reset_at:
        return True
    if not payload.get("created_at"):
        return False
    return db_admin.password_reset_at.astimezone(tz.utc) <= payload.get("created_at")


def _extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    x_api_key = request.headers.get("X-Api-Key")

    if x_api_key:
        return x_api_key.strip()

    if not auth:
        return None

    scheme, _, credentials = auth.partition(" ")
    if not scheme or not credentials:
        return None

    scheme = scheme.lower().strip()
    credentials = credentials.strip()
    if scheme == "apikey":
        return credentials
    return None


async def _build_admin_metrics(db: AsyncSession, admin_id: int) -> tuple[int, int]:
    total_users = (await db.execute(select(func.count(User.id)).where(User.admin_id == admin_id))).scalar() or 0
    reseted_usage = (
        await db.execute(
            select(func.coalesce(func.sum(AdminUsageLogs.used_traffic_at_reset), 0)).where(
                AdminUsageLogs.admin_id == admin_id
            )
        )
    ).scalar() or 0
    return int(total_users), int(reseted_usage)


async def get_admin_from_api_key(db: AsyncSession, raw_key: str, *, with_metrics: bool = False) -> AdminDetails | None:
    if not raw_key:
        return

    try:
        parsed_key = UUID(raw_key)
    except ValueError:
        return
    if parsed_key.version != 4:
        return

    db_key = await get_api_key_by_hash(db, hash_api_key(str(parsed_key)))
    if db_key is None:
        return

    db_admin = db_key.admin
    if db_admin is None:
        return

    if not db_key.is_usable:
        return

    if with_metrics:
        total_users, reseted_usage = await _build_admin_metrics(db, db_admin.id)
        admin = _build_admin_details(db_admin, total_users=total_users, reseted_usage=reseted_usage)
    else:
        admin = _build_admin_details(db_admin)

    if db_key.role is not None:
        admin.role = AdminRoleData.model_validate(db_key.role)
    return admin


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
        return _build_admin_details(db_admin)

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

    base_stmt = select(Admin, total_users_subquery, reseted_usage_subquery)

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
        return _build_admin_details(db_admin, total_users=total_users, reseted_usage=reseted_usage)

    # Env admin fallback — no DB record, but username is a known env admin
    if payload["username"] in auth_settings.sudoers:
        return AdminDetails(username=payload["username"], role=_ENV_ADMIN_ROLE)

    return None


async def get_current(request: Request, db: AsyncSession = Depends(get_db), token: str | None = Depends(oauth2_scheme)):
    admin: AdminDetails | None = None

    if token:
        admin = await get_admin(db, token)
    else:
        api_key = _extract_api_key(request)
        if api_key:
            admin = await get_admin_from_api_key(db, api_key)

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


async def get_current_with_metrics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str | None = Depends(oauth2_scheme),
):
    admin: AdminDetails | None = None

    if token:
        admin = await get_admin_with_metrics(db, token)
    else:
        api_key = _extract_api_key(request)
        if api_key:
            admin = await get_admin_from_api_key(db, api_key, with_metrics=True)

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

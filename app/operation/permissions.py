from functools import wraps

from app.models.admin import AdminDetails


class PermissionDenied(Exception):
    def __init__(self, detail: str = "Permission denied"):
        self.detail = detail
        super().__init__(detail)


class LimitExceeded(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def enforce_permission(admin: AdminDetails, resource: str, action: str) -> None:
    """
    Check if admin has permission for resource+action.
    Raises PermissionDenied if not allowed.

    Resolution order (from plan):
    1. If admin.is_owner (role.is_locked) → ALLOW unconditionally
    2. Look up permissions[resource][action]:
       - missing → DENY
       - True → ALLOW
       - {"scope": "own"} → ALLOW (scope check done separately via enforce_scope)
       - {"scope": "all"} → ALLOW
    """
    if admin.is_owner:
        return

    permissions = admin.role.get("permissions", {}) if admin.role else {}
    resource_perms = permissions.get(resource)
    if resource_perms is None:
        raise PermissionDenied(f"Permission denied: {resource}.{action}")

    action_perm = resource_perms.get(action)
    if action_perm is None:
        raise PermissionDenied(f"Permission denied: {resource}.{action}")

    # True or {"scope": ...} both mean allowed at the permission level
    # (scope enforcement is done separately)


def enforce_scope(admin: AdminDetails, resource: str, action: str, target_admin_id: int | None) -> None:
    """
    Enforce scope restriction for actions that support it (users resource only).
    Call AFTER enforce_permission.
    Raises PermissionDenied if scope is "own" and target doesn't belong to this admin.
    """
    if admin.is_owner:
        return

    permissions = admin.role.get("permissions", {}) if admin.role else {}
    action_perm = permissions.get(resource, {}).get(action)

    if isinstance(action_perm, dict) and action_perm.get("scope") == "own":
        if target_admin_id != admin.id:
            raise PermissionDenied(f"Permission denied: {resource}.{action} (scope: own)")


def get_effective_limits(admin: AdminDetails) -> dict:
    """
    Merge role limits with per-admin permission_overrides.
    Non-null override values win over role limits.
    Returns a dict with the same keys as RoleLimits.
    """
    role_limits = {}
    if admin.role:
        role_limits = admin.role.get("limits", {}) or {}

    overrides = admin.permission_overrides or {}

    merged = dict(role_limits)
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value

    return merged


def check_permission(resource: str, action: str):
    """
    Decorator for operation-layer methods.
    Expects the decorated method to have signature:
        async def method(self, db, *args, admin: AdminDetails, **kwargs)
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, db, *args, admin: AdminDetails, **kwargs):
            enforce_permission(admin, resource, action)
            return await func(self, db, *args, admin=admin, **kwargs)

        return wrapper

    return decorator

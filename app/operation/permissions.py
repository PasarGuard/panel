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
    1. If role.is_owner → ALLOW unconditionally
    2. Look up permissions[resource][action]:
       - missing → DENY
       - True → ALLOW
       - {"scope": "own"} → ALLOW (scope check done separately via enforce_scope)
       - {"scope": "all"} → ALLOW
    """
    if admin.is_owner:
        return

    permissions = admin.role.permissions if admin.role else {}
    resource_perms = permissions.get(resource)
    if resource_perms is None:
        raise PermissionDenied(f"Permission denied: {resource}.{action}")

    action_perm = resource_perms.get(action)
    if action_perm is None:
        raise PermissionDenied(f"Permission denied: {resource}.{action}")

    # True or {"scope": ...} both mean allowed at the permission level
    # (scope enforcement is done separately via enforce_scope)


def enforce_scope(admin: AdminDetails, resource: str, action: str, target_admin_id: int | None) -> None:
    """
    Enforce scope restriction for actions that support it (users resource only).
    Call AFTER enforce_permission.
    Raises PermissionDenied if scope is "own" and target doesn't belong to this admin.
    """
    if admin.is_owner:
        return

    permissions = admin.role.permissions if admin.role else {}
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
    role_limits = admin.role.limits.model_dump() if admin.role else {}
    overrides = admin.permission_overrides or {}

    merged = dict(role_limits)
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value

    return merged


def get_allowed_group_ids(admin: AdminDetails) -> list[int] | None:
    """
    Return the list of group IDs this admin is allowed to see/use.
    None means all groups are allowed (owner or no restriction set).
    """
    if admin.is_owner:
        return None
    if admin.role is None:
        return None
    return admin.role.access.allowed_group_ids


def get_allowed_template_ids(admin: AdminDetails) -> list[int] | None:
    """
    Return the list of user-template IDs this admin is allowed to see/use.
    None means all templates are allowed (owner or no restriction set).
    """
    if admin.is_owner:
        return None
    if admin.role is None:
        return None
    return admin.role.access.allowed_template_ids


def _intersect_ids(requested: list[int] | None, allowed: list[int] | None) -> list[int] | None:
    """
    Intersect a requested id list with an allowed id list.
    - allowed=None means no restriction → return requested as-is
    - requested=None means no filter → return allowed as-is (or None if allowed is also None)
    """
    if allowed is None:
        return requested
    if requested is None:
        return allowed
    return [i for i in requested if i in set(allowed)]


def apply_group_access(admin: AdminDetails, ids: list[int] | None) -> list[int] | None:
    """
    Apply the admin's allowed_group_ids restriction to a requested id list.
    Returns the filtered id list to pass to the CRUD query.
    """
    return _intersect_ids(ids, get_allowed_group_ids(admin))


def apply_template_access(admin: AdminDetails, ids: list[int] | None) -> list[int] | None:
    """
    Apply the admin's allowed_template_ids restriction to a requested id list.
    Returns the filtered id list to pass to the CRUD query.
    """
    return _intersect_ids(ids, get_allowed_template_ids(admin))


def get_scope_admin_id(admin: AdminDetails, resource: str, action: str) -> int | None:
    """
    Return admin.id if the given resource+action has scope='own', else None.

    Usage: pass the returned value as admin_id to CRUD queries.
    - None  → no admin_id filter applied (scope=all, True, or owner)
    - int   → WHERE admin_id = ? added by the CRUD (scope=own)
    """
    if admin.is_owner:
        return None
    if admin.role is None:
        return None
    perm = admin.role.permissions.get(resource, {}).get(action)
    if isinstance(perm, dict) and perm.get("scope") == "own":
        return admin.id
    return None


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

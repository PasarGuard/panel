from aiogram.filters import Filter

from app.models.admin import AdminDetails
from app.operation.permissions import enforce_permission, is_scope_all, PermissionDenied


class IsAdminFilter(Filter):
    """Passes if the user is a known, non-disabled admin."""

    async def __call__(self, _, admin: AdminDetails | None = None) -> bool:
        return bool(admin)


class HasPermission(Filter):
    """
    RBAC filter — passes if the admin has the given resource+action permission.
    Usage: HasPermission("users", "create")
    """

    def __init__(self, resource: str, action: str):
        self.resource = resource
        self.action = action

    async def __call__(self, _, admin: AdminDetails | None = None) -> bool:
        if not admin:
            return False
        try:
            enforce_permission(admin, self.resource, self.action)
            return True
        except PermissionDenied:
            return False


class IsScopeAll(Filter):
    """
    RBAC filter — passes only if the admin has scope=ALL (or is owner) for resource+action.
    Usage: IsScopeAll("users", "update")
    """

    def __init__(self, resource: str, action: str):
        self.resource = resource
        self.action = action

    async def __call__(self, _, admin: AdminDetails | None = None) -> bool:
        if not admin:
            return False
        return is_scope_all(admin, self.resource, self.action)

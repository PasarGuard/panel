from dataclasses import dataclass
from typing import Any, Mapping

from app.models.admin import AdminDetails


@dataclass
class PermissionCheckResult:
    """Represents the result of a permission check."""

    allowed: bool
    reason: str | None = None


class PermissionManager:
    """Central place to allow admin permissions

    Currently allows everything you can add real permissions later
    """

    def __init__(self, operator_type: int | None = None):
        self.operator_type = operator_type

    async def check(
        self,
        action: str,
        *,
        admin: AdminDetails | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> PermissionCheckResult:
        """Return an allow-all result; hook point for future enforcement"""
        if admin and admin.is_sudo:
            return PermissionCheckResult(allowed=True)

        # Example placeholder: enforce traffic limits for non-sudo admins
        # if action == "user.create":
        #     proposed_mb = (context or {}).get("data_limit_mb", 0)
        #     current_mb = (context or {}).get("current_usage_mb", 0)
        #     quota_mb = (context or {}).get("quota_mb")
        #     if quota_mb is not None and current_mb + proposed_mb > quota_mb:
        #         return PermissionCheckResult(allowed=False, reason="Traffic quota exceeded")

        return PermissionCheckResult(allowed=True)

# core/permission_manager.py

from datetime import datetime, timedelta

class PermissionManager:
    """
    Permission manager for admin limits
    Limits are inactive unless values are set for each admin
    """

    @staticmethod
    def allow(admin, action: str, **kwargs) -> bool:
        """
        Checks if the admin can do the given action.
        """

        # sudo admins are not restricted
        if getattr(admin, "sudo", False):
            return True

        # traffic limit
        # if traffic_limit is empty or 0 → no limit
        if hasattr(admin, "traffic_limit") and hasattr(admin, "traffic_used"):
            if admin.traffic_limit and admin.traffic_limit > 0:
                if admin.traffic_used >= admin.traffic_limit:
                    return False

        # user count limit
        if action == "create_user":
            if hasattr(admin, "user_limit") and hasattr(admin, "user_count"):
                if admin.user_limit and admin.user_limit > 0:
                    if admin.user_count >= admin.user_limit:
                        return False

        # max expiry limit
        # if max_expiry_days is 0 or None → no limit
        if action in ("create_user", "update_user"):
            expiry = kwargs.get("expiry")
            max_days = getattr(admin, "max_expiry_days", 0)

            if expiry and max_days and max_days > 0:
                max_allowed = datetime.utcnow() + timedelta(days=max_days)
                if expiry > max_allowed:
                    return False

        return True

    @staticmethod
    def enforce(admin, action: str, **kwargs):
        """
        Raises PermissionError if access is not allowed.
        """
        if not PermissionManager.allow(admin, action, **kwargs):
            raise PermissionError(f"Permission denied for '{action}'")

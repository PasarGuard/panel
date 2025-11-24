# core/permission_manager.py

class PermissionManager:
    """
    Simple permission manager placeholder.
    You can add rules later when needed
    """

    @staticmethod
    def allow(admin, action: str, **kwargs) -> bool:
        """
        Returns True if the admin is allowed to perform this action.
        You can add rules later
        """

        # Sudo admins always have full access
        if getattr(admin, "sudo", False) is True:
            return True

        # Non-sudo rules can be added here later
        return True

    @staticmethod
    def enforce(admin, action: str, **kwargs):
        """
        Use this inside operations.
        """
        if not PermissionManager.allow(admin, action, **kwargs):
            raise PermissionError(f"Permission denied for action '{action}'")

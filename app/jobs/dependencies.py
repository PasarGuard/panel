from app.models.admin import AdminDetails, AdminRoleData

SYSTEM_ADMIN = AdminDetails(username="system", role=AdminRoleData(is_owner=True))

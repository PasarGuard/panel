from app.db import AsyncSession
from app.db.crud.hwid import delete_user_hwid, get_user_hwids, reset_user_hwids
from app.models.admin import AdminDetails
from app.models.user import UserHWIDListResponse, UserHWIDResponse
from app.operation import BaseOperation
from app.operation.permissions import PermissionDenied, enforce_permission


class HWIDOperation(BaseOperation):
    async def _get_hwid_user(self, db: AsyncSession, user_id: int, admin: AdminDetails, *scope_actions: str):
        """Resolve the user whose HWIDs are accessed. The routes gate on hwids.*, which carries no
        ownership scope, so the admin must also be able to see the user: users.read is required (a
        missing action would otherwise mean "unrestricted") and every given users.* scope must hold."""
        try:
            enforce_permission(admin, "users", "read")
        except PermissionDenied:
            await self.raise_error(message="User not found", code=404)
        db_user = None
        for scope_action in scope_actions:
            db_user = await self.get_validated_user_by_id(db, user_id, admin, scope_action=scope_action)
        return db_user

    async def get_user_hwids(self, db: AsyncSession, user_id: int, admin: AdminDetails) -> UserHWIDListResponse:
        db_user = await self._get_hwid_user(db, user_id, admin, "read")
        hwids = await get_user_hwids(db, db_user.id)
        hwid_responses = [UserHWIDResponse.model_validate(h) for h in hwids]
        return UserHWIDListResponse(hwids=hwid_responses, count=len(hwid_responses))

    async def delete_user_hwid(self, db: AsyncSession, user_id: int, hwid: str, admin: AdminDetails) -> dict:
        db_user = await self._get_hwid_user(db, user_id, admin, "read", "delete")
        deleted = await delete_user_hwid(db, db_user.id, hwid)
        if not deleted:
            await self.raise_error(message="HWID not found", code=404)
        return {}

    async def reset_user_hwids(self, db: AsyncSession, user_id: int, admin: AdminDetails) -> dict:
        db_user = await self._get_hwid_user(db, user_id, admin, "read", "delete")
        count = await reset_user_hwids(db, db_user.id)
        return {"count": count}

from app.db import AsyncSession
from app.db.crud.hwid import delete_user_hwid, get_user_hwids, reset_user_hwids
from app.models.admin import AdminDetails
from app.models.user import UserHWIDListResponse, UserHWIDResponse
from app.operation import BaseOperation


class HWIDOperation(BaseOperation):
    async def get_user_hwids(self, db: AsyncSession, user_id: int, admin: AdminDetails) -> UserHWIDListResponse:
        db_user = await self.get_validated_user_by_id(db, user_id, admin)
        hwids = await get_user_hwids(db, db_user.id)
        hwid_responses = [UserHWIDResponse.model_validate(h) for h in hwids]
        return UserHWIDListResponse(hwids=hwid_responses, count=len(hwid_responses))

    async def delete_user_hwid(self, db: AsyncSession, user_id: int, hwid: str, admin: AdminDetails) -> dict:
        db_user = await self.get_validated_user_by_id(db, user_id, admin)
        deleted = await delete_user_hwid(db, db_user.id, hwid)
        if not deleted:
            await self.raise_error(message="HWID not found", code=404)
        return {}

    async def reset_user_hwids(self, db: AsyncSession, user_id: int, admin: AdminDetails) -> dict:
        db_user = await self.get_validated_user_by_id(db, user_id, admin)
        count = await reset_user_hwids(db, db_user.id)
        return {"count": count}

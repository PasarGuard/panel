from fastapi import APIRouter, Depends

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.user import UserHWIDListResponse
from app.operation import OperatorType
from app.operation.hwid import HWIDOperation
from app.utils import responses
from .authentication import get_current

hwid_operator = HWIDOperation(operator_type=OperatorType.API)
router = APIRouter(tags=["User HWID"], prefix="/api/user", responses={401: responses._401})


@router.get(
    "/{user_id}/hwids",
    response_model=UserHWIDListResponse,
    responses={403: responses._403, 404: responses._404},
)
async def get_user_hwids(user_id: int, db: AsyncSession = Depends(get_db), admin: AdminDetails = Depends(get_current)):
    """Get user's registered hardware IDs"""
    return await hwid_operator.get_user_hwids(db, user_id=user_id, admin=admin)


@router.delete(
    "/{user_id}/hwids/{hwid}",
    responses={403: responses._403, 404: responses._404},
)
async def delete_user_hwid(
    user_id: int, hwid: str, db: AsyncSession = Depends(get_db), admin: AdminDetails = Depends(get_current)
):
    """Delete a specific hardware ID from user"""
    return await hwid_operator.delete_user_hwid(db, user_id=user_id, hwid=hwid, admin=admin)


@router.post(
    "/{user_id}/hwids/reset",
    responses={403: responses._403, 404: responses._404},
)
async def reset_user_hwids(
    user_id: int, db: AsyncSession = Depends(get_db), admin: AdminDetails = Depends(get_current)
):
    """Delete all hardware IDs for user"""
    return await hwid_operator.reset_user_hwids(db, user_id=user_id, admin=admin)

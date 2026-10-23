from fastapi import APIRouter, Depends, HTTPException

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.settings import General, SettingsSchema
from app.operation import OperatorType
from app.operation.settings import SettingsOperation
from app.utils import responses

from .authentication import require_permission

settings_operator = SettingsOperation(operator_type=OperatorType.API)
router = APIRouter(tags=["Settings"], prefix="/api/settings", responses={401: responses._401, 403: responses._403})


@router.get("", response_model=SettingsSchema)
async def get_settings(db: AsyncSession = Depends(get_db), _=Depends(require_permission("settings", "read"))):
    return await settings_operator.get_settings(db)


@router.get("/general", response_model=General)
async def get_general_settings(
    db: AsyncSession = Depends(get_db), _=Depends(require_permission("settings", "read_general"))
):
    return await settings_operator.get_general_settings(db)


@router.put("", response_model=SettingsSchema)
async def modify_settings(
    modify: SettingsSchema,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("settings", "update")),
):
    if modify.general and modify.general.my_hosts is not None and not admin.is_owner:
        raise HTTPException(403, "Only the owner can change My Hosts policy")
    return await settings_operator.modify_settings(db, modify)

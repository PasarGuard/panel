from fastapi import APIRouter, Depends

from app.db import AsyncSession, get_db
from app.models.hwid import (
    HWIDAddRequest,
    HWIDDeleteAllRequest,
    HWIDDeleteRequest,
    HWIDDeviceListResponse,
    HWIDDeviceResponse,
    HWIDStatsResponse,
)
from app.operation import OperatorType
from app.operation.hwid import HWIDOperation
from app.utils import responses

from .authentication import get_current

router = APIRouter(tags=["HWID"], prefix="/api/hwid/devices", responses={401: responses._401, 403: responses._403})
hwid_operator = HWIDOperation(operator_type=OperatorType.API)


@router.get("", response_model=HWIDDeviceListResponse)
async def get_hwid_devices(
    offset: int = 0,
    limit: int = 50,
    user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current),
):
    items, total = await hwid_operator.list_devices(db, admin, offset=offset, limit=limit, user_id=user_id)
    return HWIDDeviceListResponse(items=[HWIDDeviceResponse.model_validate(i) for i in items], total=total)


@router.get("/stats", response_model=HWIDStatsResponse)
async def get_hwid_devices_stats(db: AsyncSession = Depends(get_db), admin=Depends(get_current)):
    stats = await hwid_operator.stats(db, admin)
    return HWIDStatsResponse(**stats)


@router.post("/delete")
async def delete_hwid_device(payload: HWIDDeleteRequest, db: AsyncSession = Depends(get_db), admin=Depends(get_current)):
    deleted = await hwid_operator.delete_device(db, admin, user_id=payload.user_id, hwid_hash=payload.hwid_hash)
    return {"deleted": deleted}


@router.post("/delete-all")
async def delete_all_hwid_devices(
    payload: HWIDDeleteAllRequest, db: AsyncSession = Depends(get_db), admin=Depends(get_current)
):
    deleted = await hwid_operator.delete_all_devices(db, admin, user_id=payload.user_id)
    return {"deleted": deleted}


@router.post("")
async def add_hwid_device(payload: HWIDAddRequest, db: AsyncSession = Depends(get_db), admin=Depends(get_current)):
    item, created = await hwid_operator.add_device(
        db,
        admin,
        user_id=payload.user_id,
        hwid=payload.hwid,
        device_os=payload.device_os,
        os_version=payload.os_version,
        device_model=payload.device_model,
        user_agent=payload.user_agent,
        request_ip=payload.request_ip,
    )
    return {"created": created, "item": HWIDDeviceResponse.model_validate(item)}


@router.get("/top-users")
async def get_top_users(limit: int = 20, db: AsyncSession = Depends(get_db), admin=Depends(get_current)):
    return await hwid_operator.top_users(db, admin, limit=limit)


@router.get("/{user_id}", response_model=HWIDDeviceListResponse)
async def get_user_hwid_devices(user_id: int, db: AsyncSession = Depends(get_db), admin=Depends(get_current)):
    items, total = await hwid_operator.list_devices(db, admin, user_id=user_id)
    return HWIDDeviceListResponse(items=[HWIDDeviceResponse.model_validate(i) for i in items], total=total)


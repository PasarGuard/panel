from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.db import AsyncSession, get_db
from app.db.crud.admin import (
    OwnerUpgradeError,
    build_admin_details,
    create_admin,
    get_owner,
    owner_exists,
    remove_admin,
    update_owner_password,
    upgrade_admin_to_owner,
)
from app.db.crud.temp_key import TempKeyConsumeError, consume_temp_key
from app.models.admin import AdminCreate, AdminDetails
from app.models.setup import OwnerCreateRequest, OwnerResetRequest, OwnerUpgradeRequest
from app.utils import responses
from app.utils.request import get_client_ip

router = APIRouter(tags=["Setup"], prefix="/api/setup")


async def _consume_key_or_raise(db: AsyncSession, key_str: str, action: str, request: Request) -> None:
    try:
        await consume_temp_key(db, key_str, action=action, ip=get_client_ip(request))
    except TempKeyConsumeError as exc:
        status_code = status.HTTP_400_BAD_REQUEST if exc.detail == "invalid key" else status.HTTP_410_GONE
        raise HTTPException(status_code=status_code, detail=exc.detail) from exc


@router.post(
    "/owner",
    response_model=AdminDetails,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: responses._400,
        409: responses._409,
        410: {"description": "Key already used or expired"},
    },
)
async def create_owner(
    body: OwnerCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create the owner admin using a one-time temp key."""
    if await get_owner(db) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="owner already exists")

    await _consume_key_or_raise(db, body.key, action="create_owner", request=request)

    db_admin = await create_admin(
        db,
        AdminCreate(username=body.username, password=body.password, role_id=1),
    )
    return build_admin_details(db_admin, include_loaded_metrics=True)


@router.patch(
    "/owner",
    response_model=AdminDetails,
    responses={
        400: responses._400,
        404: responses._404,
        410: {"description": "Key already used or expired"},
    },
)
async def reset_owner_password(
    body: OwnerResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Reset the owner admin's password using a one-time temp key."""
    await _consume_key_or_raise(db, body.key, action="reset_owner", request=request)

    owner = await get_owner(db)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="owner not found")

    owner = await update_owner_password(db, owner, body.password)
    return build_admin_details(owner, include_loaded_metrics=True)


@router.delete(
    "/owner",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: responses._400,
        404: responses._404,
        410: {"description": "Key already used or expired"},
    },
)
async def delete_owner(
    request: Request,
    db: AsyncSession = Depends(get_db),
    key: str = Query(..., description="One-time temp key for deleting the owner admin"),
):
    """Delete the owner admin using a one-time temp key."""
    await _consume_key_or_raise(db, key, action="delete_owner", request=request)

    owner = await get_owner(db)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="owner not found")

    await remove_admin(db, owner)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/owner/upgrade",
    response_model=AdminDetails,
    responses={
        400: responses._400,
        404: responses._404,
        409: responses._409,
        410: {"description": "Key already used or expired"},
    },
)
async def upgrade_owner(
    body: OwnerUpgradeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Upgrade an existing admin to owner using a one-time temp key."""
    if await owner_exists(db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="owner already exists")

    await _consume_key_or_raise(db, body.key, action="upgrade_owner", request=request)

    try:
        upgraded_owner = await upgrade_admin_to_owner(db, body.username)
    except OwnerUpgradeError as exc:
        if exc.detail == "admin not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc

    return build_admin_details(upgraded_owner, include_loaded_metrics=True)

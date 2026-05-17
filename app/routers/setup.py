from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from app.db import AsyncSession, get_db
from app.db.crud.admin import create_admin, get_owner, remove_admin, update_owner_password
from app.db.crud.temp_key import consume_temp_key, get_temp_key
from app.models.admin import AdminCreate, AdminDetails
from app.models.setup import OwnerCreateRequest, OwnerDeleteRequest, OwnerResetRequest
from app.utils import responses
from app.utils.request import get_client_ip

router = APIRouter(tags=["Setup"], prefix="/api/setup")


async def _validate_key(db: AsyncSession, key_str: str):
    """Validate a temp key and return it, or raise an appropriate HTTPException."""
    temp_key = await get_temp_key(db, key_str)
    if temp_key is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid key")
    if temp_key.used_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="key already used")
    if temp_key.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="key expired")
    return temp_key


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
    temp_key = await _validate_key(db, body.key)

    if await get_owner(db) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="owner already exists")

    db_admin = await create_admin(
        db,
        AdminCreate(username=body.username, password=body.password, role_id=1, is_sudo=True),
    )
    await consume_temp_key(db, temp_key, action="create_owner", ip=get_client_ip(request))
    return AdminDetails.model_validate(db_admin)


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
    temp_key = await _validate_key(db, body.key)

    owner = await get_owner(db)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="owner not found")

    owner = await update_owner_password(db, owner, body.password)
    await consume_temp_key(db, temp_key, action="reset_owner", ip=get_client_ip(request))
    return AdminDetails.model_validate(owner)


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
    body: OwnerDeleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete the owner admin using a one-time temp key."""
    temp_key = await _validate_key(db, body.key)

    owner = await get_owner(db)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="owner not found")

    await remove_admin(db, owner)
    await consume_temp_key(db, temp_key, action="delete_owner", ip=get_client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

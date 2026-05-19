from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from app.db import AsyncSession, get_db
from app.db.crud.admin import create_admin, get_owner, remove_admin, update_owner_password
from app.db.crud.temp_key import TempKeyConsumeError, consume_temp_key
from app.models.admin import AdminCreate, AdminDetails
from app.models.setup import OwnerCreateRequest, OwnerDeleteRequest, OwnerResetRequest
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
    owner = await get_owner(db)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="owner not found")

    await _consume_key_or_raise(db, body.key, action="reset_owner", request=request)

    owner = await update_owner_password(db, owner, body.password)
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
    owner = await get_owner(db)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="owner not found")

    await _consume_key_or_raise(db, body.key, action="delete_owner", request=request)

    await remove_admin(db, owner)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

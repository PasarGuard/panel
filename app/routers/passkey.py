from fastapi import APIRouter, Depends, Request

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails, Token
from app.models.passkey import (
    PasskeyAuthenticationRequest,
    PasskeyInfo,
    PasskeyOptionsRequest,
    PasskeyRegistrationRequest,
)
from app.operation import OperatorType
from app.operation.passkey import PasskeyOperation
from app.utils import responses

from .authentication import get_current, get_current_session

router = APIRouter(
    tags=["Passkeys"],
    prefix="/api/admin/passkey",
    responses={401: responses._401, 403: responses._403},
)
passkey_operator = PasskeyOperation(operator_type=OperatorType.API)


@router.get("", response_model=list[PasskeyInfo])
async def list_passkeys(admin: AdminDetails = Depends(get_current), db: AsyncSession = Depends(get_db)):
    return await passkey_operator.list_passkeys(admin=admin, db=db)


@router.get("/admins/{admin_id}", response_model=list[PasskeyInfo])
async def list_admin_passkeys(
    admin_id: int,
    current_admin: AdminDetails = Depends(get_current),
    db: AsyncSession = Depends(get_db),
):
    return await passkey_operator.list_admin_passkeys(admin_id=admin_id, current_admin=current_admin, db=db)


@router.delete("/admins/{admin_id}/{passkey_id}")
async def delete_admin_passkey(
    admin_id: int,
    passkey_id: int,
    current_admin: AdminDetails = Depends(get_current),
    db: AsyncSession = Depends(get_db),
):
    return await passkey_operator.delete_admin_passkey(
        admin_id=admin_id, passkey_id=passkey_id, current_admin=current_admin, db=db
    )


@router.delete("/{passkey_id}")
async def delete_passkey(
    passkey_id: int, admin: AdminDetails = Depends(get_current), db: AsyncSession = Depends(get_db)
):
    return await passkey_operator.delete_passkey(passkey_id=passkey_id, admin=admin, db=db)


@router.post("/login/options")
async def passkey_login_options(body: PasskeyOptionsRequest, request: Request, db: AsyncSession = Depends(get_db)):
    return await passkey_operator.passkey_login_options(body=body, request=request, db=db)


@router.post("/login/verify", response_model=Token)
async def passkey_login_verify(
    body: PasskeyAuthenticationRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    return await passkey_operator.passkey_login_verify(body=body, request=request, db=db)


@router.post("/register/options")
async def passkey_register_options(
    request: Request, admin: AdminDetails = Depends(get_current_session), db: AsyncSession = Depends(get_db)
):
    return await passkey_operator.passkey_register_options(request=request, admin=admin, db=db)


@router.post("/register/verify")
async def passkey_register_verify(
    body: PasskeyRegistrationRequest,
    request: Request,
    admin: AdminDetails = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    return await passkey_operator.passkey_register_verify(body=body, request=request, admin=admin, db=db)


@router.post("/admins/{admin_id}/register/options")
async def admin_passkey_register_options(
    admin_id: int,
    request: Request,
    current_admin: AdminDetails = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    return await passkey_operator.admin_passkey_register_options(
        admin_id=admin_id, request=request, current_admin=current_admin, db=db
    )


@router.post("/admins/{admin_id}/register/verify")
async def admin_passkey_register_verify(
    admin_id: int,
    body: PasskeyRegistrationRequest,
    request: Request,
    current_admin: AdminDetails = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    return await passkey_operator.admin_passkey_register_verify(
        admin_id=admin_id, body=body, request=request, current_admin=current_admin, db=db
    )

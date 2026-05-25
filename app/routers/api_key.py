from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.api_key import APIKeyCreate, APIKeyCreateResponse, APIKeyResponse, APIKeysResponse
from app.operation import OperatorType
from app.operation.api_key import APIKeyOperation
from app.utils import responses

from .authentication import require_permission

router = APIRouter(
    tags=["API Keys"],
    prefix="/api/api_key",
    responses={401: responses._401, 403: responses._403},
)

api_key_operator = APIKeyOperation(operator_type=OperatorType.API)


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: responses._409},
)
async def create_api_key(
    data: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "create")),
):
    return await api_key_operator.create_api_key(db, admin=admin, data=data)


@router.get("s", response_model=APIKeysResponse)
async def list_api_keys(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "read")),
):
    return await api_key_operator.list_api_keys(db, admin=admin, offset=offset, limit=limit)


@router.get("/{key_id}", response_model=APIKeyResponse, responses={404: responses._404})
async def get_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "read")),
):
    return await api_key_operator.get_api_key(db, admin=admin, key_id=key_id)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: responses._404})
async def remove_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "delete")),
):
    await api_key_operator.delete_api_key(db, admin=admin, key_id=key_id)
    return {}

from fastapi import APIRouter, Depends, status
from starlette.responses import Response

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.api_key import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyResponse,
    APIKeysQuery,
    APIKeysResponse,
    APIKeyUpdate,
    BulkAPIKeySelection,
    RemoveAPIKeysResponse,
)
from app.operation import OperatorType
from app.operation.api_key import APIKeyOperation
from app.routers.dependencies import get_api_key_list_query
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
    model: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "create")),
):
    return await api_key_operator.create_api_key(db, admin=admin, model=model)


@router.get("s", response_model=APIKeysResponse)
async def list_api_keys(
    query: APIKeysQuery = Depends(get_api_key_list_query),
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "read")),
):
    return await api_key_operator.list_api_keys(db, admin=admin, query=query)


@router.post(
    "s/bulk/delete",
    response_model=RemoveAPIKeysResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_delete_api_keys(
    bulk_api_keys: BulkAPIKeySelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "delete")),
):
    return await api_key_operator.bulk_delete_api_keys(db, admin=admin, bulk_api_keys=bulk_api_keys)


@router.patch("/{key_id}", response_model=APIKeyResponse, responses={404: responses._404, 409: responses._409})
async def modify_api_key(
    key_id: int,
    model: APIKeyUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "update")),
):
    return await api_key_operator.modify_api_key(db, admin=admin, key_id=key_id, model=model)


@router.get("/{key_id}", response_model=APIKeyResponse, responses={404: responses._404})
async def get_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "read")),
):
    return await api_key_operator.get_api_key(db, admin=admin, key_id=key_id)


@router.post("/{key_id}/revoke", response_model=APIKeyCreateResponse, responses={404: responses._404})
async def revoke_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "delete")),
):
    return await api_key_operator.revoke_api_key(db, admin=admin, key_id=key_id)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: responses._404})
async def remove_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("api_keys", "delete")),
):
    await api_key_operator.delete_api_key(db, admin=admin, key_id=key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

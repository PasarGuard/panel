from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.admin_role import (
    AdminRoleCreate,
    AdminRoleListQuery,
    AdminRoleModify,
    AdminRoleResponse,
    AdminRolesResponse,
    AdminRolesSimpleResponse,
)
from app.operation import OperatorType
from app.operation.admin_role import AdminRoleOperation
from app.utils import responses

from .authentication import require_owner, require_permission
from .dependencies import get_admin_role_list_query

router = APIRouter(
    tags=["Admin Roles"],
    prefix="/api/admin-role",
    responses={401: responses._401, 403: responses._403},
)
role_operator = AdminRoleOperation(operator_type=OperatorType.API)


@router.get("s", response_model=AdminRolesResponse)
async def get_roles(
    query: Annotated[AdminRoleListQuery, Depends(get_admin_role_list_query)],
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("admin_roles", "read")),
):
    """List all roles."""
    return await role_operator.get_roles(db, query)


@router.get("s/simple", response_model=AdminRolesSimpleResponse)
async def get_roles_simple(
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("admin_roles", "read_simple")),
):
    """List all roles as lightweight id/name/is_owner tuples."""
    return await role_operator.get_roles_simple(db)


@router.get("/{role_id}", response_model=AdminRoleResponse, responses={404: responses._404})
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("admin_roles", "read")),
):
    """Get a role by ID."""
    return await role_operator.get_role(db, role_id)


@router.post(
    "",
    response_model=AdminRoleResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: responses._409},
)
async def create_role(
    data: AdminRoleCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_owner),
):
    """Create a new role. Owner only."""
    return await role_operator.create_role(db, data, admin)


@router.put(
    "/{role_id}",
    response_model=AdminRoleResponse,
    responses={403: responses._403, 404: responses._404, 409: responses._409},
)
async def modify_role(
    role_id: int,
    data: AdminRoleModify,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_owner),
):
    """Modify a role. Owner only. Owner role cannot be modified."""
    return await role_operator.modify_role(db, role_id, data, admin)


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={403: responses._403, 404: responses._404, 409: responses._409},
)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_owner),
):
    """Delete a role. Owner only. Built-in roles and in-use roles cannot be deleted."""
    await role_operator.delete_role(db, role_id, admin)
    return {}

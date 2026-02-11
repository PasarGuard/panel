from fastapi import APIRouter, Depends, status

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.core import CoreCreate, CoreResponse, CoreResponseList, CoresSimpleResponse
from app.operation import OperatorType
from app.operation.core import CoreOperation
from app.operation.node import NodeOperation
from app.utils import responses

from .authentication import check_sudo_admin

core_operator = CoreOperation(operator_type=OperatorType.API)
node_operator = NodeOperation(operator_type=OperatorType.API)
router = APIRouter(tags=["Core"], prefix="/api/core", responses={401: responses._401, 403: responses._403})


@router.post("", response_model=CoreResponse, status_code=status.HTTP_201_CREATED)
async def create_core_config(
    new_core: CoreCreate, admin: AdminDetails = Depends(check_sudo_admin), db: AsyncSession = Depends(get_db)
):
    """Create a new core configuration."""
    return await core_operator.create_core(db, new_core, admin)


@router.get("/{core_id}", response_model=CoreResponse)
async def get_core_config(
    core_id: int, _: AdminDetails = Depends(check_sudo_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    """Get a core configuration by its ID."""
    return await core_operator.get_validated_core_config(db, core_id)


@router.put("/{core_id}", response_model=CoreResponse)
async def modify_core_config(
    core_id: int,
    restart_nodes: bool,
    modified_core: CoreCreate,
    admin: AdminDetails = Depends(check_sudo_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing core configuration."""
    response = await core_operator.modify_core(db, core_id, modified_core, admin)

    if restart_nodes:
        await node_operator.restart_all_node(db=db, core_id=core_id, admin=admin)

    return response


@router.delete("/{core_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_core_config(
    core_id: int,
    restart_nodes: bool = False,
    admin: AdminDetails = Depends(check_sudo_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a core configuration."""
    await core_operator.delete_core(db, core_id, admin)

    if restart_nodes:
        await node_operator.restart_all_node(db=db, core_id=core_id, admin=admin)

    return {}


@router.get("s", response_model=CoreResponseList)
async def get_all_cores(
    offset: int | None = None,
    limit: int | None = None,
    _: AdminDetails = Depends(check_sudo_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a list of all core configurations."""
    return await core_operator.get_all_cores(db, offset, limit)


@router.get(
    "s/simple",
    response_model=CoresSimpleResponse,
    summary="Get lightweight core list",
    description="Returns only id and name for cores. Optimized for dropdowns and autocomplete.",
)
async def get_cores_simple(
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: str | None = None,
    all: bool = False,
    _: AdminDetails = Depends(check_sudo_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get lightweight core list with only id and name"""
    return await core_operator.get_cores_simple(
        db=db,
        offset=offset,
        limit=limit,
        search=search,
        sort=sort,
        all=all,
    )


@router.post("/{core_id}/restart", status_code=status.HTTP_204_NO_CONTENT)
async def restart_core(
    core_id: int, admin: AdminDetails = Depends(check_sudo_admin), db: AsyncSession = Depends(get_db)
):
    """restart nodes related to the core config"""

    await node_operator.restart_all_node(db=db, core_id=core_id, admin=admin)
    return {}

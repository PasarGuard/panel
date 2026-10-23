from fastapi import APIRouter, Depends, status

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.client_profile import (
    BulkClientProfileSelection,
    ClientProfileAssignUsers,
    ClientProfileCreate,
    ClientProfileModify,
    ClientProfileResponse,
    ClientProfileResponseList,
    ClientProfilesSimpleResponse,
    ClientProfileUnassignUsers,
    ClientProfileUsersResponse,
    RemoveClientProfilesResponse,
)
from app.operation import OperatorType
from app.operation.client_profile import ClientProfileOperation
from app.utils import responses

from .authentication import require_permission
from .dependencies import get_client_profile_list_query, get_client_profile_simple_list_query

router = APIRouter(
    tags=["Client Profile"],
    prefix="/api/client_profile",
    responses={401: responses._401, 403: responses._403},
)

client_profile_operator = ClientProfileOperation(OperatorType.API)


@router.post(
    "",
    response_model=ClientProfileResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: responses._400, 409: responses._409},
)
async def create_client_profile(
    new_profile: ClientProfileCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("client_profiles", "create")),
):
    """Create a client profile: per-format client templates and subscription delivery overrides."""
    return await client_profile_operator.create_client_profile(db, new_profile, admin)


@router.get("/{profile_id}", response_model=ClientProfileResponse, responses={404: responses._404})
async def get_client_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("client_profiles", "read")),
):
    return await client_profile_operator.get_client_profile(db, profile_id)


@router.put(
    "/{profile_id}",
    response_model=ClientProfileResponse,
    responses={400: responses._400, 404: responses._404, 409: responses._409},
)
async def modify_client_profile(
    profile_id: int,
    modified_profile: ClientProfileModify,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("client_profiles", "update")),
):
    """Partial update; `templates` and `settings`, when sent, replace the stored value as a whole."""
    return await client_profile_operator.modify_client_profile(db, profile_id, modified_profile, admin)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: responses._404})
async def remove_client_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("client_profiles", "delete")),
):
    """Delete a client profile; its users and user templates fall back to the default delivery."""
    await client_profile_operator.remove_client_profile(db, profile_id, admin)
    return {}


@router.post(
    "/{profile_id}/users",
    response_model=ClientProfileUsersResponse,
    responses={404: responses._404},
)
async def assign_client_profile_users(
    profile_id: int,
    body: ClientProfileAssignUsers,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("client_profiles", "update")),
):
    """Attach users to the profile (also needs users.update; scope own limits it to own users)."""
    return await client_profile_operator.assign_users(db, profile_id, body, admin)


@router.delete(
    "/{profile_id}/users",
    response_model=ClientProfileUsersResponse,
    responses={404: responses._404},
)
async def unassign_client_profile_users(
    profile_id: int,
    body: ClientProfileUnassignUsers,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("client_profiles", "update")),
):
    """Detach the listed users, or with `all: true` every user, from the profile."""
    return await client_profile_operator.unassign_users(db, profile_id, body, admin)


@router.get("s", response_model=ClientProfileResponseList)
async def get_client_profiles(
    query=Depends(get_client_profile_list_query),
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("client_profiles", "read")),
):
    """List client profiles; `users_count` counts all users on a profile, not only the caller's own users."""
    return await client_profile_operator.get_client_profiles(db, query=query)


@router.get("s/simple", response_model=ClientProfilesSimpleResponse)
async def get_client_profiles_simple(
    query=Depends(get_client_profile_simple_list_query),
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("client_profiles", "read_simple")),
):
    return await client_profile_operator.get_client_profiles_simple(db=db, query=query)


@router.post(
    "s/bulk/delete",
    response_model=RemoveClientProfilesResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_delete_client_profiles(
    bulk_profiles: BulkClientProfileSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("client_profiles", "delete")),
):
    """Delete selected client profiles by ID."""
    return await client_profile_operator.bulk_remove_client_profiles(db, bulk_profiles, admin)

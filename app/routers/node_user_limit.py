import hashlib
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.db import AsyncSession, get_db
from app.db.crud import node_user_limit as crud
from app.db.crud.node import get_node_by_id
from app.db.crud.user import get_user_by_id
from app.models.admin import AdminDetails
from app.models.node_user_limit import (
    BulkSetLimitRequest,
    NodeUserLimitCreate,
    NodeUserLimitModify,
    NodeUserLimitResponse,
    NodeUserLimitsResponse,
)
from app.utils import responses

from .authentication import check_sudo_admin

router = APIRouter(
    tags=["Node User Limits"],
    prefix="/api/node-user-limits",
    responses={401: responses._401, 403: responses._403},
)


@router.post(
    "",
    response_model=NodeUserLimitResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: responses._404, 409: responses._409},
)
async def create_node_user_limit(
    limit: NodeUserLimitCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(check_sudo_admin),
):
    """
    Create a new per-user per-node traffic limit.

    Only accessible to sudo admins.
    """
    # Validate user exists
    user = await get_user_by_id(db, limit.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate node exists
    node = await get_node_by_id(db, limit.node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Check if limit already exists
    existing = await crud.get_node_user_limit(db, limit.user_id, limit.node_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Limit already exists for user {limit.user_id} on node {limit.node_id}",
        )

    return await crud.create_node_user_limit(db, limit)


@router.get(
    "/user/{user_id}",
    response_model=NodeUserLimitsResponse,
    responses={404: responses._404},
)
async def get_user_limits(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(check_sudo_admin),
):
    """
    Get all node limits for a specific user.

    Returns a list of all per-node traffic limits configured for the user.
    """
    # Validate user exists
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    limits = await crud.get_node_limits_for_user(db, user_id)
    return NodeUserLimitsResponse(limits=limits, total=len(limits))


@router.get(
    "/node/{node_id}",
    responses={404: responses._404, 304: {"description": "Not Modified"}},
)
async def get_node_limits(
    node_id: int,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(check_sudo_admin),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
):
    """
    Get all user limits for a specific node.

    Returns a list of all per-user traffic limits configured for the node.
    Supports ETag for conditional requests - returns 304 if data unchanged.
    """
    # Validate node exists
    node = await get_node_by_id(db, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    limits = await crud.get_user_limits_for_node(db, node_id)
    
    # Generate ETag from limits data
    limits_data = [
        {"user_id": limit.user_id, "data_limit": limit.data_limit}
        for limit in limits
    ]
    etag_content = json.dumps(limits_data, sort_keys=True)
    etag = f'"{hashlib.md5(etag_content.encode()).hexdigest()}"'
    
    # Check if client has current version
    if if_none_match and if_none_match == etag:
        return Response(status_code=304)
    
    # Set response headers
    response.headers["ETag"] = etag
    response.headers["X-Limits-Version"] = etag.strip('"')[:8]  # Short version for debugging
    
    return NodeUserLimitsResponse(limits=limits, total=len(limits))


@router.get(
    "/{limit_id}",
    response_model=NodeUserLimitResponse,
    responses={404: responses._404},
)
async def get_limit(
    limit_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(check_sudo_admin),
):
    """
    Get a specific node user limit by ID.
    """
    limit = await crud.get_node_user_limit_by_id(db, limit_id)
    if not limit:
        raise HTTPException(status_code=404, detail="Limit not found")
    return limit


@router.put(
    "/{limit_id}",
    response_model=NodeUserLimitResponse,
    responses={404: responses._404},
)
async def modify_limit(
    limit_id: int,
    modify: NodeUserLimitModify,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(check_sudo_admin),
):
    """
    Modify an existing node user limit.

    Updates the data_limit, reset_strategy, and reset_time for the specified limit.
    """
    limit = await crud.get_node_user_limit_by_id(db, limit_id)
    if not limit:
        raise HTTPException(status_code=404, detail="Limit not found")

    return await crud.modify_node_user_limit(
        db, limit, modify.data_limit, modify.data_limit_reset_strategy, modify.reset_time
    )


@router.delete(
    "/{limit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: responses._404},
)
async def delete_limit(
    limit_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(check_sudo_admin),
):
    """
    Delete a node user limit.

    Removes the per-user per-node traffic limit. The user will then be subject
    to the global node limit and user limit (if configured).
    """
    limit = await crud.get_node_user_limit_by_id(db, limit_id)
    if not limit:
        raise HTTPException(status_code=404, detail="Limit not found")

    await crud.remove_node_user_limit(db, limit)


@router.post(
    "/bulk-set",
    response_model=NodeUserLimitsResponse,
    status_code=status.HTTP_200_OK,
    responses={404: responses._404},
)
async def bulk_set_all_users_limit(
    request: BulkSetLimitRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(check_sudo_admin),
):
    """
    Set the same data limit for ALL users on a specific node.

    This endpoint fetches all users and applies the specified data_limit,
    reset_strategy, and reset_time to each user on the given node. 
    If a limit already exists, it updates it. If not, it creates a new one.

    Example request body:
    ```json
    {
        "node_id": 1,
        "data_limit": 10737418240,  // 10 GB in bytes
        "data_limit_reset_strategy": "month",
        "reset_time": 1
    }
    ```
    """
    from app.db.crud.user import get_users

    # Validate node exists
    node = await get_node_by_id(db, request.node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Get all users (get_users returns list[User] directly)
    users = await get_users(db, offset=0, limit=10000)  # Get up to 10k users

    # Build user_limits dict for all users
    user_limits = {user.id: request.data_limit for user in users}

    # Use existing bulk set function with reset strategy
    limits = await crud.bulk_set_user_limits_for_node(
        db, request.node_id, user_limits, 
        request.data_limit_reset_strategy, request.reset_time
    )
    return NodeUserLimitsResponse(limits=limits, total=len(limits))


@router.post(
    "/node/{node_id}/bulk",
    response_model=NodeUserLimitsResponse,
    responses={404: responses._404},
)
async def bulk_set_limits(
    node_id: int,
    user_limits: dict[int, int],
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(check_sudo_admin),
):
    """
    Bulk set or update user limits for a node.

    Accepts a dictionary mapping user_id to data_limit. Creates new limits
    or updates existing ones as needed.

    Example request body:
    ```json
    {
        "1": 10737418240,
        "2": 21474836480,
        "3": 0
    }
    ```
    """
    # Validate node exists
    node = await get_node_by_id(db, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    limits = await crud.bulk_set_user_limits_for_node(db, node_id, user_limits)
    return NodeUserLimitsResponse(limits=limits, total=len(limits))

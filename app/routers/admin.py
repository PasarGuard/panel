import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app import notification
from app.db import AsyncSession, get_db
from app.models.admin import (
    AdminCreate,
    AdminDetails,
    AdminListQuery,
    AdminModify,
    AdminSimpleListQuery,
    AdminsResponse,
    AdminsSimpleResponse,
    AdminStatus,
    AdminUsageQuery,
    BulkAdminsActionResponse,
    BulkAdminSelection,
    RemoveAdminsResponse,
    Token,
)
from app.models.stats import UserUsageStatsList
from app.operation import OperatorType
from app.operation.admin import AdminOperation
from app.utils import responses
from app.utils.jwt import create_admin_token
from app.utils.request import get_client_ip

from .authentication import (
    get_current,
    get_current_with_metrics,
    require_permission,
    validate_admin,
    validate_mini_app_admin,
)
from .dependencies import get_admin_list_query, get_admin_simple_list_query, get_admin_usage_query

router = APIRouter(tags=["Admin"], prefix="/api/admin", responses={401: responses._401, 403: responses._403})
admin_operator = AdminOperation(operator_type=OperatorType.API)


@router.post("/token", response_model=Token)
async def admin_token(
    request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    """Authenticate an admin and issue a token."""
    client_ip = get_client_ip(request)
    db_admin = await validate_admin(db, form_data.username, form_data.password)
    if not db_admin:
        asyncio.create_task(notification.admin_login(form_data.username, form_data.password, client_ip, False))
        raise HTTPException(
            status_code=401, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"}
        )
    if db_admin.status == AdminStatus.disabled:
        asyncio.create_task(notification.admin_login(form_data.username, form_data.password, client_ip, False))
        raise HTTPException(
            status_code=403, detail="your account has been disabled", headers={"WWW-Authenticate": "Bearer"}
        )
    asyncio.create_task(notification.admin_login(db_admin.username, "", client_ip, True))
    return Token(access_token=await create_admin_token(db_admin.id, form_data.username))


@router.post("/miniapp/token", responses={409: responses._409})
async def admin_mini_app_token(
    request: Request, x_telegram_authorization: str = Header(), db: AsyncSession = Depends(get_db)
):
    """Authenticate an admin via Telegram MiniApp and issue a token."""
    client_ip = get_client_ip(request)
    db_admin = await validate_mini_app_admin(db, x_telegram_authorization)
    if not db_admin:
        raise HTTPException(status_code=401, detail="admin not found.", headers={"WWW-Authenticate": "Bearer"})
    if db_admin.status == AdminStatus.disabled:
        raise HTTPException(
            status_code=403, detail="your account has been disabled", headers={"WWW-Authenticate": "Bearer"}
        )
    asyncio.create_task(notification.admin_login(db_admin.username, "", client_ip, True))
    return Token(access_token=await create_admin_token(db_admin.id, db_admin.username))


@router.post(
    "",
    response_model=AdminDetails,
    status_code=status.HTTP_201_CREATED,
    responses={201: {"description": "Admin created successfully"}, 409: responses._409},
)
async def create_admin(
    new_admin: AdminCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "create")),
):
    """Create a new admin."""
    return await admin_operator.create_admin(db, new_admin=new_admin, admin=admin)


@router.put(
    "/{username}",
    response_model=AdminDetails,
    responses={403: responses._403, 404: responses._404, 409: responses._409},
)
async def modify_admin(
    username: str,
    modified_admin: AdminModify,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    """Modify an existing admin's details."""
    return await admin_operator.modify_admin(
        db, username=username, modified_admin=modified_admin, current_admin=current_admin
    )


@router.put(
    "/by-username/{username}",
    response_model=AdminDetails,
    responses={403: responses._403, 404: responses._404, 409: responses._409},
)
async def modify_admin_by_username(
    username: str,
    modified_admin: AdminModify,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    return await admin_operator.modify_admin(
        db, username=username, modified_admin=modified_admin, current_admin=current_admin
    )


@router.put(
    "/by-id/{admin_id}",
    response_model=AdminDetails,
    responses={403: responses._403, 404: responses._404, 409: responses._409},
)
async def modify_admin_by_id(
    admin_id: int,
    modified_admin: AdminModify,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    return await admin_operator.modify_admin_by_id(
        db, admin_id=admin_id, modified_admin=modified_admin, current_admin=current_admin
    )


@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_admin(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminDetails = Depends(require_permission("admins", "delete")),
):
    """Remove an admin from the database."""
    await admin_operator.remove_admin(db, username=username, current_admin=current_admin)
    return {}


@router.delete("/by-username/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_admin_by_username(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminDetails = Depends(require_permission("admins", "delete")),
):
    await admin_operator.remove_admin(db, username=username, current_admin=current_admin)
    return {}


@router.delete("/by-id/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_admin_by_id(
    admin_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminDetails = Depends(require_permission("admins", "delete")),
):
    await admin_operator.remove_admin_by_id(db, admin_id=admin_id, current_admin=current_admin)
    return {}


@router.get("", response_model=AdminDetails)
def get_current_admin(admin: AdminDetails = Depends(get_current_with_metrics)):
    """Retrieve the current authenticated admin."""
    return admin


@router.get("s", response_model=AdminsResponse)
async def get_admins(
    query: Annotated[AdminListQuery, Depends(get_admin_list_query)],
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "read")),
):
    """Fetch a list of admins with optional filters for pagination and username."""
    return await admin_operator.get_admins(db, query=query, admin=admin)


@router.get(
    "s/simple",
    response_model=AdminsSimpleResponse,
    summary="Get lightweight admin list",
    description="Returns only id and username for admins. Optimized for dropdowns and autocomplete.",
)
async def get_admins_simple(
    query: Annotated[AdminSimpleListQuery, Depends(get_admin_simple_list_query)],
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "read_simple")),
):
    """Get lightweight admin list with only id and username."""
    return await admin_operator.get_admins_simple(db=db, query=query, admin=admin)


@router.get(
    "/{username}/usage",
    response_model=UserUsageStatsList,
    responses={403: responses._403, 404: responses._404},
)
async def get_admin_usage(
    username: str,
    query: Annotated[AdminUsageQuery, Depends(get_admin_usage_query)],
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(get_current),
):
    """Get admin usage aggregated from user traffic."""
    return await admin_operator.get_admin_usage(db, username=username, admin=admin, query=query)


@router.get(
    "/by-username/{username}/usage",
    response_model=UserUsageStatsList,
    responses={403: responses._403, 404: responses._404},
)
async def get_admin_usage_by_username(
    username: str,
    query: Annotated[AdminUsageQuery, Depends(get_admin_usage_query)],
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "read")),
):
    return await admin_operator.get_admin_usage(db, username=username, admin=admin, query=query)


@router.get(
    "/by-id/{admin_id}/usage",
    response_model=UserUsageStatsList,
    responses={403: responses._403, 404: responses._404},
)
async def get_admin_usage_by_id(
    admin_id: int,
    query: Annotated[AdminUsageQuery, Depends(get_admin_usage_query)],
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "read")),
):
    return await admin_operator.get_admin_usage_by_id(db, admin_id=admin_id, admin=admin, query=query)


@router.post("/{username}/users/disable", responses={404: responses._404})
async def disable_all_active_users(
    username: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    """Disable all active users under a specific admin."""
    await admin_operator.disable_all_active_users(db, username=username, admin=admin)
    return {}


@router.post("/by-username/{username}/users/disable", responses={404: responses._404})
async def disable_all_active_users_by_username(
    username: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    await admin_operator.disable_all_active_users(db, username=username, admin=admin)
    return {}


@router.post("/by-id/{admin_id}/users/disable", responses={404: responses._404})
async def disable_all_active_users_by_id(
    admin_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    await admin_operator.disable_all_active_users_by_id(db, admin_id=admin_id, admin=admin)
    return {}


@router.post("/{username}/users/activate", responses={404: responses._404})
async def activate_all_disabled_users(
    username: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    """Activate all disabled users under a specific admin."""
    await admin_operator.activate_all_disabled_users(db, username=username, admin=admin)
    return {}


@router.post("/by-username/{username}/users/activate", responses={404: responses._404})
async def activate_all_disabled_users_by_username(
    username: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    await admin_operator.activate_all_disabled_users(db, username=username, admin=admin)
    return {}


@router.post("/by-id/{admin_id}/users/activate", responses={404: responses._404})
async def activate_all_disabled_users_by_id(
    admin_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    await admin_operator.activate_all_disabled_users_by_id(db, admin_id=admin_id, admin=admin)
    return {}


@router.delete("/{username}/users", responses={403: responses._403, 404: responses._404})
async def remove_all_users(
    username: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "delete")),
):
    """Remove all users under a specific admin."""
    deleted = await admin_operator.remove_all_users(db, username=username, admin=admin)
    return {"detail": f"operation has been successfuly done {deleted} users deleted"}


@router.delete("/by-username/{username}/users", responses={403: responses._403, 404: responses._404})
async def remove_all_users_by_username(
    username: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "delete")),
):
    deleted = await admin_operator.remove_all_users(db, username=username, admin=admin)
    return {"detail": f"operation has been successfuly done {deleted} users deleted"}


@router.delete("/by-id/{admin_id}/users", responses={403: responses._403, 404: responses._404})
async def remove_all_users_by_id(
    admin_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "delete")),
):
    deleted = await admin_operator.remove_all_users_by_id(db, admin_id=admin_id, admin=admin)
    return {"detail": f"operation has been successfuly done {deleted} users deleted"}


@router.post("/{username}/reset", response_model=AdminDetails, responses={404: responses._404})
async def reset_admin_usage(
    username: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "reset_usage")),
):
    """Resets usage of admin."""
    return await admin_operator.reset_admin_usage(db, username=username, admin=admin)


@router.post("/by-username/{username}/reset", response_model=AdminDetails, responses={404: responses._404})
async def reset_admin_usage_by_username(
    username: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "reset_usage")),
):
    return await admin_operator.reset_admin_usage(db, username=username, admin=admin)


@router.post("/by-id/{admin_id}/reset", response_model=AdminDetails, responses={404: responses._404})
async def reset_admin_usage_by_id(
    admin_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "reset_usage")),
):
    return await admin_operator.reset_admin_usage_by_id(db, admin_id=admin_id, admin=admin)


@router.post(
    "s/bulk/delete",
    response_model=RemoveAdminsResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_delete_admins(
    bulk_admins: BulkAdminSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "delete")),
):
    """Delete selected admins by ID."""
    return await admin_operator.bulk_remove_admins(db, bulk_admins, admin)


@router.post(
    "s/bulk/reset",
    response_model=BulkAdminsActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_reset_admins_usage(
    bulk_admins: BulkAdminSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "reset_usage")),
):
    """Reset usage for selected admins by ID."""
    return await admin_operator.bulk_reset_admins_usage(db, bulk_admins, admin)


@router.post(
    "s/bulk/disable",
    response_model=BulkAdminsActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_disable_admins(
    bulk_admins: BulkAdminSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    """Disable selected admins by ID."""
    return await admin_operator.bulk_set_admins_disabled(db, bulk_admins, admin, is_disabled=True)


@router.post(
    "s/bulk/enable",
    response_model=BulkAdminsActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_enable_admins(
    bulk_admins: BulkAdminSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    """Enable selected admins by ID."""
    return await admin_operator.bulk_set_admins_disabled(db, bulk_admins, admin, is_disabled=False)


@router.post(
    "s/bulk/users/disable",
    response_model=BulkAdminsActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_disable_all_active_users(
    bulk_admins: BulkAdminSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    """Disable all active users under selected admins."""
    return await admin_operator.bulk_disable_all_active_users_for_admins(db, bulk_admins, admin)


@router.post(
    "s/bulk/users/activate",
    response_model=BulkAdminsActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_activate_all_disabled_users(
    bulk_admins: BulkAdminSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "update")),
):
    """Activate all disabled users under selected admins."""
    return await admin_operator.bulk_activate_all_disabled_users_for_admins(db, bulk_admins, admin)


@router.delete(
    "s/bulk/users",
    response_model=BulkAdminsActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_remove_all_users(
    bulk_admins: BulkAdminSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("admins", "delete")),
):
    """Remove all users under selected admins."""
    return await admin_operator.bulk_remove_all_users_for_admins(db, bulk_admins, admin)

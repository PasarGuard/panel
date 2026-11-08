from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.db import AsyncSession, get_db
from app.db.models import Admin
from app.models.admin import AdminDetails
from app.models.host import (
    BaseHost,
    BulkHostsActionResponse,
    BulkHostSelection,
    CreateHost,
    HostListQuery,
    RemoveHostsResponse,
    validate_format_variables,
)
from app.operation import OperatorType
from app.operation.host import HostOperation
from app.utils import responses

from .authentication import get_current, require_permission
from .dependencies import get_host_list_query

host_operator = HostOperation(operator_type=OperatorType.API)
router = APIRouter(tags=["Host"], prefix="/api/host", responses={401: responses._401, 403: responses._403})


class HostPreference(BaseModel):
    id: int
    remark: str = Field(min_length=1, max_length=256)
    default_remark: str
    priority: int = Field(ge=0, le=1000000)
    default_priority: int
    is_customized: bool = False
    enabled: bool = True


class HostPreferenceUpdate(BaseModel):
    id: int
    remark: str | None = Field(default=None, min_length=1, max_length=256)
    priority: int = Field(ge=0, le=1000000)
    enabled: bool = True

    @field_validator("remark")
    @classmethod
    def validate_remark(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Custom host remark cannot be empty")
        return validate_format_variables(value)


async def _operator_account(db: AsyncSession, admin: AdminDetails) -> Admin:
    if admin.id is None or admin.role.is_owner or admin.role.name != "operator":
        raise HTTPException(status_code=403, detail="Operator role required")
    account = await db.scalar(select(Admin).where(Admin.id == admin.id))
    if account is None:
        raise HTTPException(status_code=403, detail="Operator account required")
    return account


def _apply_host_preferences(hosts: list[BaseHost], account: Admin) -> list[BaseHost]:
    saved_hosts = (account.host_preferences or {}).get("hosts", {})
    personalized = [
        host.model_copy(
            update={
                "remark": saved_hosts.get(str(host.id), {}).get("remark") or host.remark,
                "priority": saved_hosts.get(str(host.id), {}).get("priority", host.priority),
            }
        )
        for host in hosts
        if saved_hosts.get(str(host.id), {}).get("enabled", True)
    ]
    return sorted(personalized, key=lambda item: (item.priority, item.id))


@router.get("s/preferences", response_model=list[HostPreference])
async def get_host_preferences(db: AsyncSession = Depends(get_db), admin: AdminDetails = Depends(get_current)):
    account = await _operator_account(db, admin)
    hosts = [host for host in await host_operator.get_hosts(db, HostListQuery()) if not host.is_disabled]
    saved = account.host_preferences or {}
    saved_hosts = saved.get("hosts", {})
    preferences = [
        HostPreference(
            id=host.id,
            remark=saved_hosts.get(str(host.id), {}).get("remark") or host.remark,
            default_remark=host.remark,
            priority=saved_hosts.get(str(host.id), {}).get("priority", host.priority),
            default_priority=host.priority,
            is_customized=bool(saved_hosts.get(str(host.id), {}).get("remark")),
            enabled=saved_hosts.get(str(host.id), {}).get("enabled", True),
        )
        for host in hosts
    ]
    return sorted(preferences, key=lambda item: (item.priority, item.id))


@router.put("s/preferences", response_model=list[HostPreference])
async def save_host_preferences(
    preferences: list[HostPreferenceUpdate],
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(get_current),
):
    account = await _operator_account(db, admin)
    all_hosts = await host_operator.get_hosts(db, HostListQuery())
    hosts = [host for host in all_hosts if not host.is_disabled]
    current_ids = {host.id for host in hosts}
    submitted_ids = [item.id for item in preferences]
    if len(submitted_ids) != len(set(submitted_ids)) or set(submitted_ids) != current_ids:
        raise HTTPException(status_code=400, detail="Submit each current host exactly once")
    saved_hosts = (account.host_preferences or {}).get("hosts", {})
    current_hosts = {host.id: host for host in hosts}
    existing_ids = {str(host.id) for host in all_hosts}
    updated_hosts = {host_id: value for host_id, value in saved_hosts.items() if host_id in existing_ids}
    for item in preferences:
        host_id = str(item.id)
        previous = saved_hosts.get(host_id, {})
        remains_disabled = previous.get("enabled", True) is False and not item.enabled
        updated_hosts[host_id] = {
            "remark": previous.get("remark") if remains_disabled else item.remark,
            "priority": previous.get("priority", current_hosts[item.id].priority)
            if remains_disabled
            else item.priority,
            "enabled": item.enabled,
        }
    account.host_preferences = {"hosts": updated_hosts}
    await db.commit()
    return await get_host_preferences(db, admin)


@router.get("/{host_id}", response_model=BaseHost)
async def get_host(
    host_id: int, db: AsyncSession = Depends(get_db), _: AdminDetails = Depends(require_permission("hosts", "read"))
):
    """
    get host by **id**
    """
    return await host_operator.get_validated_host(db=db, host_id=host_id)


@router.get("s", response_model=list[BaseHost])
async def get_hosts(
    query=Depends(get_host_list_query),
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("hosts", "read")),
):
    """
    Get proxy hosts.
    """
    hosts = await host_operator.get_hosts(db=db, query=query)
    if admin.role.name == "operator" and not admin.role.is_owner:
        account = await _operator_account(db, admin)
        return _apply_host_preferences(hosts, account)
    return hosts


@router.post("/", response_model=BaseHost, status_code=status.HTTP_201_CREATED)
async def create_host(
    new_host: CreateHost,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("hosts", "create")),
):
    """
    create a new host

    **inbound_tag** must be available in one of the configured cores
    """
    return await host_operator.create_host(db, new_host=new_host, admin=admin)


@router.put("/{host_id}", response_model=BaseHost, responses={404: responses._404})
async def modify_host(
    host_id: int,
    modified_host: CreateHost,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("hosts", "update")),
):
    """
    modify host by **id**

    **inbound_tag** must be available in one of the configured cores
    """
    return await host_operator.modify_host(db, host_id=host_id, modified_host=modified_host, admin=admin)


@router.delete(
    "/{host_id}",
    responses={404: responses._404, 409: responses._409},
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("hosts", "update")),
):
    """
    remove host by **id**
    """
    await host_operator.remove_host(db, host_id=host_id, admin=admin)
    return {}


@router.put("s", response_model=list[BaseHost])
async def modify_hosts(
    modified_hosts: list[CreateHost],
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("hosts", "update")),
):
    """
    Modify proxy hosts and update the configuration.
    """
    return await host_operator.modify_hosts(db=db, modified_hosts=modified_hosts, admin=admin)


@router.post(
    "s/bulk/delete",
    response_model=RemoveHostsResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404, 409: responses._409},
)
async def bulk_delete_hosts(
    bulk_hosts: BulkHostSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("hosts", "update")),
):
    """Delete selected hosts by ID."""
    return await host_operator.bulk_remove_hosts(db, bulk_hosts, admin)


@router.post(
    "s/bulk/disable",
    response_model=BulkHostsActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_disable_hosts(
    bulk_hosts: BulkHostSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("hosts", "update")),
):
    """Disable selected hosts by ID."""
    return await host_operator.bulk_set_hosts_disabled(db, bulk_hosts, admin, is_disabled=True)


@router.post(
    "s/bulk/enable",
    response_model=BulkHostsActionResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_enable_hosts(
    bulk_hosts: BulkHostSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("hosts", "update")),
):
    """Enable selected hosts by ID."""
    return await host_operator.bulk_set_hosts_disabled(db, bulk_hosts, admin, is_disabled=False)

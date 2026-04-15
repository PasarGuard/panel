from fastapi import APIRouter, Depends, status

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.client_template import (
    BulkClientTemplateSelection,
    ClientTemplateCreate,
    ClientTemplateModify,
    ClientTemplateResponse,
    ClientTemplateResponseList,
    ClientTemplatesSimpleResponse,
    ClientTemplateType,
    RemoveClientTemplatesResponse,
)
from app.operation import OperatorType
from app.operation.client_template import ClientTemplateOperation
from app.utils import responses

from .authentication import check_sudo_admin, get_current

router = APIRouter(
    tags=["Client Template"],
    prefix="/api/client_template",
    responses={401: responses._401, 403: responses._403},
)

client_template_operator = ClientTemplateOperation(OperatorType.API)


@router.post("", response_model=ClientTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_client_template(
    new_template: ClientTemplateCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(check_sudo_admin),
):
    return await client_template_operator.create_client_template(db, new_template, admin)


@router.get("/{template_id}", response_model=ClientTemplateResponse)
async def get_client_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(get_current),
):
    return await client_template_operator.get_validated_client_template(db, template_id)


@router.put("/{template_id}", response_model=ClientTemplateResponse)
async def modify_client_template(
    template_id: int,
    modified_template: ClientTemplateModify,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(check_sudo_admin),
):
    return await client_template_operator.modify_client_template(db, template_id, modified_template, admin)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_client_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(check_sudo_admin),
):
    await client_template_operator.remove_client_template(db, template_id, admin)
    return {}


@router.get("s", response_model=ClientTemplateResponseList)
async def get_client_templates(
    template_type: ClientTemplateType | None = None,
    offset: int | None = None,
    limit: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(get_current),
):
    return await client_template_operator.get_client_templates(
        db, template_type=template_type, offset=offset, limit=limit
    )


@router.get("s/simple", response_model=ClientTemplatesSimpleResponse)
async def get_client_templates_simple(
    template_type: ClientTemplateType | None = None,
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: str | None = None,
    all: bool = False,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(get_current),
):
    return await client_template_operator.get_client_templates_simple(
        db=db,
        template_type=template_type,
        offset=offset,
        limit=limit,
        search=search,
        sort=sort,
        all=all,
    )


@router.post(
    "s/bulk/delete",
    response_model=RemoveClientTemplatesResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_delete_client_templates(
    bulk_templates: BulkClientTemplateSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(check_sudo_admin),
):
    """Delete selected client templates by ID."""
    return await client_template_operator.bulk_remove_client_templates(db, bulk_templates, admin)

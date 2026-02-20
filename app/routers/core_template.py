from fastapi import APIRouter, Depends, status

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.core_template import (
    CoreTemplateCreate,
    CoreTemplateModify,
    CoreTemplateResponse,
    CoreTemplateResponseList,
    CoreTemplatesSimpleResponse,
    CoreTemplateType,
)
from app.operation import OperatorType
from app.operation.core_template import CoreTemplateOperation
from app.utils import responses

from .authentication import check_sudo_admin, get_current

router = APIRouter(
    tags=["Core Template"],
    prefix="/api/core_template",
    responses={401: responses._401, 403: responses._403},
)

core_template_operator = CoreTemplateOperation(OperatorType.API)


@router.post("", response_model=CoreTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_core_template(
    new_template: CoreTemplateCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(check_sudo_admin),
):
    return await core_template_operator.create_core_template(db, new_template, admin)


@router.get("/{template_id}", response_model=CoreTemplateResponse)
async def get_core_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(get_current),
):
    return await core_template_operator.get_validated_core_template(db, template_id)


@router.put("/{template_id}", response_model=CoreTemplateResponse)
async def modify_core_template(
    template_id: int,
    modified_template: CoreTemplateModify,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(check_sudo_admin),
):
    return await core_template_operator.modify_core_template(db, template_id, modified_template, admin)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_core_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(check_sudo_admin),
):
    await core_template_operator.remove_core_template(db, template_id, admin)
    return {}


@router.get("s", response_model=CoreTemplateResponseList)
async def get_core_templates(
    template_type: CoreTemplateType | None = None,
    offset: int | None = None,
    limit: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(get_current),
):
    return await core_template_operator.get_core_templates(db, template_type=template_type, offset=offset, limit=limit)


@router.get("s/simple", response_model=CoreTemplatesSimpleResponse)
async def get_core_templates_simple(
    template_type: CoreTemplateType | None = None,
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: str | None = None,
    all: bool = False,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(get_current),
):
    return await core_template_operator.get_core_templates_simple(
        db=db,
        template_type=template_type,
        offset=offset,
        limit=limit,
        search=search,
        sort=sort,
        all=all,
    )

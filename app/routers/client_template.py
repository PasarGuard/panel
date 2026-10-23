from fastapi import APIRouter, Depends, HTTPException, status

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.client_template import (
    BulkClientTemplateSelection,
    ClientTemplateCreate,
    ClientTemplateModify,
    ClientTemplateResponse,
    ClientTemplateResponseList,
    ClientTemplatesSimpleResponse,
    ClientTemplateValidate,
    ClientTemplateValidation,
    RemoveClientTemplatesResponse,
)
from app.operation import OperatorType
from app.operation.client_template import ClientTemplateOperation
from app.operation.permissions import PermissionDenied, enforce_permission
from app.utils import responses

from .authentication import get_current, require_permission
from .dependencies import get_client_template_list_query, get_client_template_simple_list_query

router = APIRouter(
    tags=["Client Template"],
    prefix="/api/client_template",
    responses={401: responses._401, 403: responses._403},
)

client_template_operator = ClientTemplateOperation(OperatorType.API)


async def _require_create_or_update(admin: AdminDetails = Depends(get_current)) -> AdminDetails:
    """/validate is used by both the create and the edit modal, so either permission is enough for it."""
    for action in ("create", "update"):
        try:
            enforce_permission(admin, "client_templates", action)
            return admin
        except PermissionDenied as e:
            denied = e
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(denied))


@router.post("", response_model=ClientTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_client_template(
    new_template: ClientTemplateCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("client_templates", "create")),
):
    return await client_template_operator.create_client_template(db, new_template, admin)


@router.post("/validate", response_model=ClientTemplateValidation)
async def validate_client_template(
    template: ClientTemplateValidate,
    _: AdminDetails = Depends(_require_create_or_update),
):
    """Render and check template content as saving would, without saving it."""
    return await client_template_operator.validate_client_template(
        template.template_type, template.content, template.use_jinja
    )


@router.get("/{template_id}", response_model=ClientTemplateResponse)
async def get_client_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("client_templates", "read")),
):
    return await client_template_operator.get_validated_client_template(db, template_id)


@router.put("/{template_id}", response_model=ClientTemplateResponse)
async def modify_client_template(
    template_id: int,
    modified_template: ClientTemplateModify,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("client_templates", "update")),
):
    return await client_template_operator.modify_client_template(db, template_id, modified_template, admin)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_client_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("client_templates", "delete")),
):
    await client_template_operator.remove_client_template(db, template_id, admin)
    return {}


@router.get("s", response_model=ClientTemplateResponseList)
async def get_client_templates(
    query=Depends(get_client_template_list_query),
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("client_templates", "read")),
):
    return await client_template_operator.get_client_templates(db, query=query)


@router.get("s/simple", response_model=ClientTemplatesSimpleResponse)
async def get_client_templates_simple(
    query=Depends(get_client_template_simple_list_query),
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("client_templates", "read_simple")),
):
    return await client_template_operator.get_client_templates_simple(db=db, query=query)


@router.post(
    "s/bulk/delete",
    response_model=RemoveClientTemplatesResponse,
    responses={400: responses._400, 403: responses._403, 404: responses._404},
)
async def bulk_delete_client_templates(
    bulk_templates: BulkClientTemplateSelection,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("client_templates", "delete")),
):
    """Delete selected client templates by ID."""
    return await client_template_operator.bulk_remove_client_templates(db, bulk_templates, admin)

from fastapi import APIRouter, Depends

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.inbound_ratio import InboundRatioModify, InboundRatioResponse
from app.operation import OperatorType
from app.operation.inbound_ratio import InboundRatioOperation
from app.utils import responses

from .authentication import require_permission

inbound_ratio_operator = InboundRatioOperation(operator_type=OperatorType.API)
router = APIRouter(
    tags=["InboundRatio"],
    prefix="/api/inbound-ratio",
    responses={401: responses._401, 403: responses._403},
)


@router.get("/usages", response_model=list[InboundRatioResponse])
async def get_inbound_ratios(
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("hosts", "read")),
):
    """
    Get every inbound with its usage ratio.

    The ratio multiplies the traffic recorded for users whose groups expose the inbound.
    """
    return await inbound_ratio_operator.get_inbound_ratios(db)


@router.patch("/{tag}/usage", response_model=InboundRatioResponse, responses={404: responses._404})
async def modify_inbound_ratio(
    tag: str,
    payload: InboundRatioModify,
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_permission("hosts", "update")),
):
    """
    Set the usage ratio of one inbound.

    Takes effect for usage recorded from the next accounting cycle (at most one minute).
    """
    return await inbound_ratio_operator.set_inbound_ratio(db, tag, payload.usage_coefficient)

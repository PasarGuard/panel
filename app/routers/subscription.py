from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from app.db import AsyncSession, get_db
from app.models.settings import Application, ConfigFormat
from app.models.stats import UserUsageStatsList
from app.models.user import SubscriptionUserResponse
from app.operation import OperatorType
from app.operation.subscription import SubscriptionOperation
from config import subscription_env_settings

from .dependencies import get_subscription_headers, get_subscription_usage_query

router = APIRouter(tags=["Subscription"], prefix=f"/{subscription_env_settings.path}")
subscription_operator = SubscriptionOperation(operator_type=OperatorType.API)


@router.get("/{token}/")
@router.get("/{token}", include_in_schema=False)
async def user_subscription(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    user_agent: str = Header(default=""),
    headers=Depends(get_subscription_headers),
):
    """Provides a subscription link based on the user agent (Clash, V2Ray, etc.)."""
    return await subscription_operator.user_subscription(
        db,
        token=token,
        accept_header=request.headers.get("Accept", ""),
        user_agent=user_agent,
        ip=request.client.host if request.client else None,
        request_url=str(request.url),
        **headers.model_dump(),
    )


@router.get("/{token}/info", response_model=SubscriptionUserResponse)
async def user_subscription_info(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    """Retrieves detailed information about the user's subscription."""
    user_data, response_headers = await subscription_operator.user_subscription_info(
        db, token=token, ip=request.client.host if request.client else None
    )
    return JSONResponse(content=user_data.model_dump(mode="json"), headers=response_headers)


@router.get("/{token}/raw")
async def user_subscription_raw(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    return await subscription_operator.user_subscription_raw(db, token=token, request_url=str(request.url))


@router.get("/{token}/apps", response_model=list[Application])
async def user_subscription_apps(token: str, db: AsyncSession = Depends(get_db)):
    """
    Get applications available for user's subscription.
    """
    return await subscription_operator.user_subscription_apps(db, token)


@router.get("/{token}/usage", response_model=UserUsageStatsList)
async def get_sub_user_usage(
    token: str,
    query=Depends(get_subscription_usage_query),
    db: AsyncSession = Depends(get_db),
):
    """Fetches the usage statistics for the user within a specified date range."""
    return await subscription_operator.get_user_usage(db, token=token, query=query)


@router.get("/{token}/{client_type}")
async def user_subscription_with_client_type(
    request: Request,
    token: str,
    client_type: ConfigFormat,
    db: AsyncSession = Depends(get_db),
    headers=Depends(get_subscription_headers),
):
    """Provides a subscription link based on the specified client type (e.g., Clash, V2Ray)."""
    return await subscription_operator.user_subscription_with_client_type(
        db,
        token=token,
        client_type=client_type,
        request_url=str(request.url),
        **headers.model_dump(),
    )

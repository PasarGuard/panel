from fastapi import APIRouter, Depends

from app.db import AsyncSession, get_db
from app.models.settings import General, SettingsSchema, SubRule
from app.models.subscription_defaults import build_default_subscription_rules
from app.operation import OperatorType
from app.operation.settings import SettingsOperation
from app.utils import responses
from config import subscription_env_settings

from .authentication import require_permission

settings_operator = SettingsOperation(operator_type=OperatorType.API)
router = APIRouter(tags=["Settings"], prefix="/api/settings", responses={401: responses._401, 403: responses._403})


@router.get("", response_model=SettingsSchema)
async def get_settings(db: AsyncSession = Depends(get_db), _=Depends(require_permission("settings", "read"))):
    return await settings_operator.get_settings(db)


@router.get("/general", response_model=General)
async def get_general_settings(
    db: AsyncSession = Depends(get_db), _=Depends(require_permission("settings", "read_general"))
):
    return await settings_operator.get_general_settings(db)


@router.get("/subscription/defaults", response_model=list[SubRule])
async def get_default_subscription_rules(_=Depends(require_permission("settings", "read"))):
    return build_default_subscription_rules(
        use_custom_json_default=subscription_env_settings.use_custom_json_default,
        use_custom_json_for_v2rayn=subscription_env_settings.use_custom_json_for_v2rayn,
        use_custom_json_for_v2rayng=subscription_env_settings.use_custom_json_for_v2rayng,
        use_custom_json_for_streisand=subscription_env_settings.use_custom_json_for_streisand,
        use_custom_json_for_happ=subscription_env_settings.use_custom_json_for_happ,
        use_custom_json_for_npvtunnel=subscription_env_settings.use_custom_json_for_npvtunnel,
    )


@router.put("", response_model=SettingsSchema)
async def modify_settings(
    modify: SettingsSchema, db: AsyncSession = Depends(get_db), _=Depends(require_permission("settings", "update"))
):
    return await settings_operator.modify_settings(db, modify)

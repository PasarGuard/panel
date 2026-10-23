from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.plugin import PluginsResponse
from app.operation import OperatorType
from app.operation.plugin import PluginOperation
from app.utils import responses
from config import jwt_settings

from .authentication import get_current_for_request, oauth2_scheme, require_owner

PLUGIN_UI_COOKIE = "pasarguard_plugin_ui"
SDK_FILE = Path(__file__).resolve().parent.parent / "plugins" / "static" / "sdk.js"

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

router = APIRouter(tags=["Plugins"], prefix="/api/plugins", responses={401: responses._401, 403: responses._403})

plugin_operator = PluginOperation(operator_type=OperatorType.API)


async def require_plugin_ui_owner(
    request: Request, db: AsyncSession = Depends(get_db), token: str | None = Depends(oauth2_scheme)
) -> AdminDetails:
    """Owner auth for plugin UI files: iframes cannot send headers, so the UI cookie is accepted too."""
    admin = await get_current_for_request(request, db, token or request.cookies.get(PLUGIN_UI_COOKIE))
    if not admin.is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can perform this action")
    return admin


def ui_cookie_secure(request: Request) -> bool:
    """Secure unless the panel is opened on localhost over plain HTTP; TLS may end at a proxy that sends no headers."""
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if request.url.scheme == "https" or forwarded_proto == "https":
        return True
    return request.url.hostname not in LOCAL_HOSTS


@router.get("", response_model=PluginsResponse)
async def get_plugins(_: AdminDetails = Depends(require_owner)):
    """List enabled plugins (loaded and failed). Empty when the plugin system is off."""
    return plugin_operator.get_plugins()


@router.get("/sdk.js", include_in_schema=False)
async def get_plugin_sdk():
    return FileResponse(SDK_FILE, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/{plugin_id}/settings", response_model=dict[str, Any])
async def get_plugin_settings(plugin_id: str, _: AdminDetails = Depends(require_owner)):
    return await plugin_operator.get_plugin_settings(plugin_id)


@router.put("/{plugin_id}/settings", response_model=dict[str, Any])
async def modify_plugin_settings(
    plugin_id: str,
    settings: Annotated[dict[str, Any], Body()],
    db: AsyncSession = Depends(get_db),
    _: AdminDetails = Depends(require_owner),
):
    return await plugin_operator.modify_plugin_settings(db, plugin_id, settings)


@router.post("/{plugin_id}/ui-session", status_code=status.HTTP_204_NO_CONTENT)
async def create_plugin_ui_session(
    plugin_id: str,
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    _: AdminDetails = Depends(require_owner),
):
    """Set a cookie scoped to this plugin's UI path so the dashboard iframe can load it."""
    await plugin_operator.get_ui_file(plugin_id, "")
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    if token:
        max_age = (
            jwt_settings.access_token_expire_minutes * 60 if jwt_settings.access_token_expire_minutes > 0 else None
        )
        response.set_cookie(
            PLUGIN_UI_COOKIE,
            token,
            max_age=max_age,
            path=f"/api/plugins/{plugin_id}/ui/",
            secure=ui_cookie_secure(request),
            httponly=True,
            samesite="strict",
        )
    return response


@router.get("/{plugin_id}/ui/{file_path:path}", include_in_schema=False)
async def get_plugin_ui_file(plugin_id: str, file_path: str, _: AdminDetails = Depends(require_plugin_ui_owner)):
    target = await plugin_operator.get_ui_file(plugin_id, file_path)
    return FileResponse(target, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

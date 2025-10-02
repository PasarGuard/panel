
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.templates import render_template
from config import DASHBOARD_PATH, HOME_PAGE_TEMPLATE

DASHBOARD_ROUTE = DASHBOARD_PATH.rstrip("/")
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def base():
    return render_template(HOME_PAGE_TEMPLATE)


@router.get("/manifest.json")
async def get_manifest(request: Request, start_url: str | None = None):
    """Dynamic PWA manifest generator
    """
    # Get the base URL
    # base_url = str(request.base_url).rstrip("/")

    # Determine start URL - prioritize query param, then dashboard path, then root
    if start_url:
        # Validate that start_url is within the dashboard path for security
        if start_url.startswith(DASHBOARD_ROUTE):
            resolved_start_url = start_url
        else:
            resolved_start_url = DASHBOARD_ROUTE
    else:
        resolved_start_url = DASHBOARD_ROUTE or "/"

    manifest = {
        "name": "PasarGuard",
        "short_name": "PasarGuard",
        "description": "PasarGuard: Modern dashboard for managing proxies and users.",
        "theme_color": "#1b1b1d",
        "background_color": "#1b1b1d",
        "display": "standalone",
        "start_url": resolved_start_url,
        "scope": DASHBOARD_ROUTE or "/",
        "icons": [
            {"src": "/statics/favicon/logo-pwa.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/statics/favicon/logo-pwa.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/statics/favicon/logo-pwa.png", "sizes": "180x180", "type": "image/png"},
        ],
    }

    return JSONResponse(content=manifest)

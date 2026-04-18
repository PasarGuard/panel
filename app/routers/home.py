from fastapi import APIRouter, status
from fastapi.responses import HTMLResponse

from app.templates import render_template
from config import DASHBOARD_PATH, HOME_PAGE_TEMPLATE

DASHBOARD_ROUTE = DASHBOARD_PATH.rstrip("/")
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def base():
    return render_template(HOME_PAGE_TEMPLATE)


@router.get("/health", response_model=dict, status_code=status.HTTP_200_OK)
async def health():
    return {"status": "ok"}

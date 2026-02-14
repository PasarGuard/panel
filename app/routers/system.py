import asyncio
import time

from aiogram.types import Update
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.settings import Telegram
from app.models.system import SystemStats, WorkerHealth, WorkersHealth
from app.nats import is_nats_enabled
from app.nats.node_rpc import node_nats_client
from app.nats.scheduler_rpc import scheduler_nats_client
from app.operation import OperatorType
from app.operation.system import SystemOperation
from app.settings import telegram_settings
from app.telegram import get_bot, get_dispatcher
from app.utils import responses
from app.utils.logger import EndpointFilter, get_logger
from config import DO_NOT_LOG_TELEGRAM_BOT

from .authentication import get_current

system_operator = SystemOperation(operator_type=OperatorType.API)
router = APIRouter(tags=["System"], prefix="/api", responses={401: responses._401})

TELEGRAM_WEBHOOK_PATH = "/tghook"
if DO_NOT_LOG_TELEGRAM_BOT:
    uvicorn_access_logger = get_logger("uvicorn.access")
    uvicorn_access_logger.addFilter(EndpointFilter([f"{router.prefix}{TELEGRAM_WEBHOOK_PATH}"]))


@router.get("/system", response_model=SystemStats)
async def get_system_stats(
    admin_username: str | None = None, db: AsyncSession = Depends(get_db), admin: AdminDetails = Depends(get_current)
):
    """Fetch system stats including memory, CPU, and user metrics."""
    return await system_operator.get_system_stats(db, admin=admin, admin_username=admin_username)


@router.get("/inbounds", response_model=list[str])
async def get_inbounds(_: AdminDetails = Depends(get_current)):
    """Retrieve inbound configurations grouped by protocol."""
    return await system_operator.get_inbounds()


async def _measure_worker_health(request_coro) -> WorkerHealth:
    start = time.monotonic()
    try:
        await request_coro
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return WorkerHealth(status="ok", response_time_ms=elapsed_ms)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        error_msg = str(exc) or exc.__class__.__name__
        return WorkerHealth(status="down", response_time_ms=elapsed_ms, error=error_msg)


@router.get("/workers/health", response_model=WorkersHealth)
async def get_workers_health(_: AdminDetails = Depends(get_current)):
    if not is_nats_enabled():
        disabled = WorkerHealth(status="disabled")
        return WorkersHealth(scheduler=disabled, node=disabled)

    timeout = 5.0
    scheduler_task = _measure_worker_health(scheduler_nats_client.request("health_check", {}, timeout))
    node_task = _measure_worker_health(node_nats_client.request("health_check", {}, timeout))
    scheduler_health, node_health = await asyncio.gather(scheduler_task, node_task)

    return WorkersHealth(scheduler=scheduler_health, node=node_health)


@router.post(TELEGRAM_WEBHOOK_PATH, include_in_schema=False)
async def webhook_handler(request: Request, X_Telegram_Bot_Api_Secret_Token: str = Header()):
    """Telegram webhook handler"""
    settings: Telegram = await telegram_settings()

    if not settings.enable:
        raise HTTPException(status_code=404, detail="not found")

    if X_Telegram_Bot_Api_Secret_Token != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid secret key")

    bot = get_bot()
    dp = get_dispatcher()

    update_data = await request.json()
    update = Update.model_validate(update_data, context={"bot": bot})
    asyncio.create_task(dp.feed_update(bot, update))
    return JSONResponse(status_code=200, content={"status": "ok"})

import asyncio
from contextlib import asynccontextmanager

from aiocache import caches
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.engine import make_url

from app.core.redis_config import get_redis_config, is_redis_enabled
from app.middlewares import setup_middleware
from app.utils.logger import get_logger
from config import DOCS, RUN_SCHEDULER, SQLALCHEMY_DATABASE_URL, SUBSCRIPTION_PATH

__version__ = "1.9.2"

startup_functions = []
shutdown_functions = []


if is_redis_enabled():
    cfg = get_redis_config()
    caches.set_config(
        {
            "default": {
                "cache": "aiocache.RedisCache",
                "endpoint": cfg["endpoint"],
                "port": cfg["port"],
                "db": cfg["db"],
                "serializer": {"class": "aiocache.serializers.PickleSerializer"},
            }
        }
    )

logger = get_logger()


def _resolve_jobstore_url() -> str:
    url = make_url(SQLALCHEMY_DATABASE_URL)
    driver_map = {
        "sqlite+aiosqlite": "sqlite",
        "postgresql+asyncpg": "postgresql+psycopg",
        "mysql+asyncmy": "mysql+pymysql",
    }

    if url.drivername in driver_map:
        url = url.set(drivername=driver_map[url.drivername])

    return str(url)


def on_startup(func):
    startup_functions.append(func)
    return func


def on_shutdown(func):
    shutdown_functions.append(func)
    return func


@asynccontextmanager
async def lifespan(app: FastAPI):
    for func in startup_functions:
        if callable(func):
            if asyncio.iscoroutinefunction(func):  # Better way to check if it's async
                if "app" in func.__code__.co_varnames:
                    await func(app)
                else:
                    await func()
            else:
                if "app" in func.__code__.co_varnames:
                    func(app)
                else:
                    func()
    yield

    for func in shutdown_functions:
        if callable(func):
            if asyncio.iscoroutinefunction(func):
                if "app" in func.__code__.co_varnames:
                    await func(app)
                else:
                    await func()
            else:
                if "app" in func.__code__.co_varnames:
                    func(app)
                else:
                    func()


app = FastAPI(
    title="PasarGuardAPI",
    description="Unified GUI Censorship Resistant Solution",
    version=__version__,
    lifespan=lifespan,
    openapi_url="/openapi.json" if DOCS else None,
)

try:
    jobstores = {"default": SQLAlchemyJobStore(url=_resolve_jobstore_url())}
except ModuleNotFoundError as exc:
    missing_driver = getattr(exc, "name", "unknown driver")
    raise RuntimeError(
        f"Missing database driver ({missing_driver}) for APScheduler job store. "
        "Install a synchronous driver compatible with your configured SQLALCHEMY_DATABASE_URL."
    ) from exc

scheduler = AsyncIOScheduler(jobstores=jobstores, job_defaults={"max_instances": 30}, timezone="UTC")

setup_middleware(app)

from app import routers, telegram  # noqa
from app.routers import api_router  # noqa

if RUN_SCHEDULER:
    from app import jobs  # noqa

app.include_router(api_router)


def use_route_names_as_operation_ids(app: FastAPI) -> None:
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.name


use_route_names_as_operation_ids(app)


@on_startup
def validate_paths():
    paths = [f"{r.path}/" for r in app.routes]
    paths.append("/api/")
    if f"/{SUBSCRIPTION_PATH}/" in paths:
        raise ValueError(f"you can't use /{SUBSCRIPTION_PATH}/ as subscription path it reserved for {app.title}")


if RUN_SCHEDULER:
    from app.notification.client import start_notification_dispatcher, stop_notification_dispatcher

    on_startup(scheduler.start)
    on_shutdown(scheduler.shutdown)
    on_startup(start_notification_dispatcher)
    on_shutdown(stop_notification_dispatcher)
on_startup(lambda: logger.info(f"PasarGuard v{__version__}"))


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = {}
    for error in exc.errors():
        details[error["loc"][-1]] = error.get("msg")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=jsonable_encoder({"detail": details}),
    )

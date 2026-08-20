import warnings

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import DBAPIError

from app.lifecycle import on_shutdown, on_startup
from app.middlewares import setup_middleware
from app.nats import is_multi_worker, require_nats_if_multiworker
from app.nats.message import MessageTopic
from app.nats.router import router
from app.settings import handle_settings_message
from app.subscription.client_templates import handle_client_template_message
from app.utils.logger import get_logger
from app.version import __version__
from config import runtime_settings, subscription_env_settings

logger = get_logger("app-factory")

# Swagger UI ships no dark theme; hand-tune one instead of the harsher filter-invert hack.
_SWAGGER_DARK_CSS = """
    <style>
        body {
            background-color: #22262b;
            color: #c9d1d9;
        }
        .swagger-ui { color: #c9d1d9; }
        .swagger-ui .topbar { background-color: #1c2024; }
        .swagger-ui .info .title,
        .swagger-ui .info li, .swagger-ui .info p, .swagger-ui .info table,
        .swagger-ui .scheme-container .schemes-title,
        .swagger-ui label, .swagger-ui .opblock-tag,
        .swagger-ui .opblock .opblock-summary-operation-id,
        .swagger-ui .opblock .opblock-summary-path,
        .swagger-ui .opblock .opblock-summary-path__deprecated,
        .swagger-ui .opblock .opblock-summary-description,
        .swagger-ui .parameter__name, .swagger-ui .parameter__type,
        .swagger-ui .parameter__in, .swagger-ui .prop-type,
        .swagger-ui table thead tr td, .swagger-ui table thead tr th,
        .swagger-ui .response-col_status, .swagger-ui .response-col_links,
        .swagger-ui .tab li, .swagger-ui .opblock-description-wrapper p,
        .swagger-ui .btn, .swagger-ui section.models h4,
        .swagger-ui section.models .model-container,
        .swagger-ui .model, .swagger-ui .model-title,
        .swagger-ui .model-toggle:after {
            color: #c9d1d9;
        }
        .swagger-ui .scheme-container,
        .swagger-ui section.models,
        .swagger-ui section.models .model-container,
        .swagger-ui .opblock-tag {
            background-color: #262b31;
            border-color: #3a3f45;
        }
        .swagger-ui .opblock {
            background-color: #262b31;
            border-color: #3a3f45;
        }
        .swagger-ui .opblock .opblock-section-header {
            background-color: #262b31cc;
        }
        .swagger-ui .opblock.opblock-get { border-color: #3a6ea5; background: #1f2b36; }
        .swagger-ui .opblock.opblock-get .opblock-summary-method { background: #3a6ea5; }
        .swagger-ui .opblock.opblock-post { border-color: #3f9142; background: #1f3323; }
        .swagger-ui .opblock.opblock-post .opblock-summary-method { background: #3f9142; }
        .swagger-ui .opblock.opblock-put { border-color: #a3752f; background: #332a1c; }
        .swagger-ui .opblock.opblock-put .opblock-summary-method { background: #a3752f; }
        .swagger-ui .opblock.opblock-delete { border-color: #a5423a; background: #332020; }
        .swagger-ui .opblock.opblock-delete .opblock-summary-method { background: #a5423a; }
        .swagger-ui .opblock.opblock-patch { border-color: #3a9187; background: #1c3230; }
        .swagger-ui .opblock.opblock-patch .opblock-summary-method { background: #3a9187; }
        .swagger-ui input, .swagger-ui select, .swagger-ui textarea {
            background-color: #1c2024;
            color: #c9d1d9;
            border-color: #3a3f45;
        }
        .swagger-ui .btn {
            background-color: #2d333b;
            border-color: #3a3f45;
        }
        .swagger-ui .highlight-code, .swagger-ui .microlight {
            background-color: #1c2024;
        }
        .swagger-ui .body-param__example {
            background-color: #1c2024;
            color: #c9d1d9;
        }
        .swagger-ui .responses-inner h4, .swagger-ui .responses-inner h5 {
            color: #c9d1d9;
        }
        .swagger-ui .model-box {
            background-color: #1c2024;
        }
    </style>
"""


def _setup_swagger_ui(app: FastAPI) -> None:
    if not runtime_settings.docs:
        return

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html() -> HTMLResponse:
        response = get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            swagger_ui_parameters={"docExpansion": "none"},
        )
        html = response.body.decode().replace("</head>", f"{_SWAGGER_DARK_CSS}</head>")
        return HTMLResponse(html)


async def _ignore_worker_sync_message(_: dict):
    return None


async def database_operational_error_handler(request: Request, exc: DBAPIError):
    orig = getattr(exc, "orig", None)
    error_summary = f"{type(orig).__name__}: {orig}" if orig else type(exc).__name__
    logger.warning(f"Database unavailable while handling {request.method} {request.url.path}: {error_summary}")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database temporarily unavailable"},
    )


def _use_route_names_as_operation_ids(app: FastAPI) -> None:
    def _simplify_operation_ids(routes):
        for route in routes:
            if isinstance(route, APIRoute):
                route.operation_id = route.name
            elif type(route).__name__ == "_IncludedRouter" and hasattr(route, "original_router"):
                _simplify_operation_ids(route.original_router.routes)
            elif hasattr(route, "routes"):
                _simplify_operation_ids(route.routes)

    _simplify_operation_ids(app.routes)


def _validate_subscription_path(app: FastAPI) -> None:
    paths = [f"{path}/" for route in app.routes if (path := getattr(route, "path", None)) is not None]
    paths.append("/api/")
    if f"/{subscription_env_settings.path}/" in paths:
        raise ValueError(
            f"you can't use /{subscription_env_settings.path}/ as subscription path it reserved for {app.title}"
        )


def _register_nats_handlers(
    enable_router: bool,
    enable_settings: bool,
    enable_client_templates: bool,
    ignore_host_messages: bool = False,
    enable_node_sync: bool = False,
):
    if enable_router:
        on_startup(router.start)
        on_shutdown(router.stop)
    if enable_settings:
        router.register_handler(MessageTopic.SETTING, handle_settings_message)
    if enable_client_templates:
        router.register_handler(MessageTopic.CLIENT_TEMPLATE, handle_client_template_message)
    if ignore_host_messages:
        router.register_handler(MessageTopic.HOST, _ignore_worker_sync_message)
    if enable_node_sync:
        from app.node.manager_sync import register_node_sync_handler

        register_node_sync_handler()
    elif enable_router:
        # Split roles (e.g. backend/scheduler) still subscribe to worker_sync;
        router.register_handler(MessageTopic.NODE, _ignore_worker_sync_message)


def _register_scheduler_hooks():
    from app.notification.queue_manager import initialize_queues

    on_startup(initialize_queues)

    # APScheduler is needed by node and scheduler roles to run their jobs
    if not (runtime_settings.role.runs_node or runtime_settings.role.runs_scheduler):
        return

    import asyncio
    import contextlib

    from apscheduler.schedulers.base import STATE_PAUSED

    from app.nats.leader import (
        HEARTBEAT_INTERVAL,
        is_job_leader,
        needs_job_leader,
        set_on_leadership_lost,
        start_job_leader,
        stop_job_leader,
    )
    from app.scheduler import scheduler

    started_notifications = {"value": False}
    reclaim_task: dict[str, asyncio.Task | None] = {"task": None}

    async def _resume_jobs_on_leadership_gained():
        if scheduler.state == STATE_PAUSED:
            scheduler.resume()
        elif not scheduler.running:
            scheduler.start()

        if runtime_settings.role.runs_scheduler and not started_notifications["value"]:
            from app.notification.client import start_notification_dispatcher

            await start_notification_dispatcher()
            started_notifications["value"] = True

    async def _reclaim_leadership_loop():
        # start_job_leader = try_become_leader + heartbeat restart
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if is_job_leader():
                return
            if await start_job_leader():
                await _resume_jobs_on_leadership_gained()
                return

    def _ensure_reclaim_task():
        task = reclaim_task["task"]
        if task is not None and not task.done():
            return
        reclaim_task["task"] = asyncio.create_task(_reclaim_leadership_loop())

    async def _cancel_reclaim_task():
        task = reclaim_task["task"]
        reclaim_task["task"] = None
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _pause_jobs_on_leadership_lost():
        if started_notifications["value"]:
            from app.notification.client import stop_notification_dispatcher

            await stop_notification_dispatcher()
            started_notifications["value"] = False
        if scheduler.running:
            scheduler.pause()
        _ensure_reclaim_task()

    set_on_leadership_lost(_pause_jobs_on_leadership_lost)

    async def _start_scheduler_if_leader():
        if await start_job_leader():
            scheduler.start()
        elif needs_job_leader():
            _ensure_reclaim_task()

    on_startup(_start_scheduler_if_leader)

    # Notification dispatcher (consumer loop) is only needed by scheduler role + leader
    if runtime_settings.role.runs_scheduler:
        from app.notification.client import start_notification_dispatcher, stop_notification_dispatcher

        async def _start_notification_dispatcher_if_leader():
            if is_job_leader():
                await start_notification_dispatcher()
                started_notifications["value"] = True

        async def _stop_notification_dispatcher_if_started():
            if started_notifications["value"]:
                await stop_notification_dispatcher()
                started_notifications["value"] = False

        on_startup(_start_notification_dispatcher_if_leader)
        on_shutdown(_stop_notification_dispatcher_if_started)

    async def _stop_scheduler_and_leader():
        await _cancel_reclaim_task()
        if scheduler.running:
            scheduler.shutdown()
        await stop_job_leader()

    on_shutdown(_stop_scheduler_and_leader)


def _register_jobs():
    if not (runtime_settings.role.runs_node or runtime_settings.role.runs_scheduler):
        return
    from app import jobs  # noqa: F401


def _warn_deprecated_role():
    role = runtime_settings.role
    if not role.is_deprecated:
        return
    message = (
        f"ROLE={role.value} is deprecated and will be removed in PasarGuard 7.0.0. "
        "Use ROLE=all-in-one with NATS_ENABLED=1 and UVICORN_WORKERS>1 for multi-worker deployments."
    )
    warnings.warn(message, DeprecationWarning, stacklevel=2)
    logger.warning(message)


def create_app() -> FastAPI:
    from app.lifecycle import lifespan

    # Fail fast before NATS handlers / queues register (covers all-in-one + UVICORN_WORKERS>1).
    require_nats_if_multiworker(is_multi_worker())

    _warn_deprecated_role()

    app = FastAPI(
        title="PasarGuardAPI",
        description="Unified GUI Censorship Resistant Solution",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/openapi.json" if runtime_settings.docs else None,
        docs_url=None,
    )
    _setup_swagger_ui(app)

    setup_middleware(app)

    on_startup(_validate_subscription_path)

    if runtime_settings.role.runs_panel:
        import dashboard
        from app import telegram  # noqa: F401
        from app.routers import api_router

        dashboard.setup_dashboard(app)
        app.include_router(api_router)

    if runtime_settings.role.runs_node:
        from app.node import worker as node_worker  # noqa: F401

    if runtime_settings.role.runs_scheduler:
        from app.nats.scheduler_rpc import start_scheduler_rpc, stop_scheduler_rpc

        on_startup(start_scheduler_rpc)
        on_shutdown(stop_scheduler_rpc)

    enable_router = (
        runtime_settings.role.runs_panel or runtime_settings.role.runs_node or runtime_settings.role.runs_scheduler
    )
    enable_settings = runtime_settings.role.runs_panel or runtime_settings.role.runs_scheduler
    enable_client_templates = runtime_settings.role.runs_panel or runtime_settings.role.runs_scheduler
    ignore_host_messages = not runtime_settings.role.runs_panel
    enable_node_sync = runtime_settings.role.runs_node
    _register_nats_handlers(
        enable_router, enable_settings, enable_client_templates, ignore_host_messages, enable_node_sync
    )
    _register_scheduler_hooks()
    _register_jobs()

    _use_route_names_as_operation_ids(app)

    on_startup(lambda: logger.info(f"PasarGuard v{__version__} ({runtime_settings.role.value})"))

    @app.exception_handler(RequestValidationError)
    def validation_exception_handler(request: Request, exc: RequestValidationError):
        details = {}
        for error in exc.errors():
            details[error["loc"][-1]] = error.get("msg")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=jsonable_encoder({"detail": details}),
        )

    app.add_exception_handler(DBAPIError, database_operational_error_handler)

    from app.operation.permissions import LimitExceeded, PermissionDenied

    @app.exception_handler(PermissionDenied)
    async def permission_denied_handler(request: Request, exc: PermissionDenied):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.detail},
        )

    @app.exception_handler(LimitExceeded)
    async def limit_exceeded_handler(request: Request, exc: LimitExceeded):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.detail},
        )

    return app

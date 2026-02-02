from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.lifecycle import on_shutdown, on_startup
from app.nats import is_nats_enabled
from app.middlewares import setup_middleware
from app.nats.message import MessageTopic
from app.nats.router import router
from app.settings import handle_settings_message
from app.utils.logger import get_logger
from app.version import __version__
from config import DOCS, MULTI_WORKER, RUN_SCHEDULER, SUBSCRIPTION_PATH


logger = get_logger("app-factory")


def _use_route_names_as_operation_ids(app: FastAPI) -> None:
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.name


def _register_nats_handlers(enable_router: bool, enable_settings: bool):
    if enable_router:
        on_startup(router.start)
        on_shutdown(router.stop)
    if enable_settings:
        router.register_handler(MessageTopic.SETTING, handle_settings_message)


def _register_scheduler_hooks(role: str):
    if not RUN_SCHEDULER:
        return

    from app.scheduler import scheduler

    if role in ("node-worker", "scheduler"):
        on_startup(scheduler.start)
        on_shutdown(scheduler.shutdown)

    if role == "scheduler":
        from app.notification.client import start_notification_dispatcher, stop_notification_dispatcher
        from app.notification.queue_manager import initialize_queue, shutdown_queue

        on_startup(initialize_queue)
        on_startup(start_notification_dispatcher)
        on_shutdown(stop_notification_dispatcher)
        on_shutdown(shutdown_queue)


def _register_jobs(role: str):
    if not RUN_SCHEDULER:
        return
    if role in ("node-worker", "scheduler"):
        from app import jobs  # noqa: F401


def create_app(role: str = "panel") -> FastAPI:
    from app.lifecycle import lifespan

    all_in_one = (not MULTI_WORKER) and role == "panel"
    enable_panel = role == "panel" or all_in_one
    enable_node_worker = role == "node-worker" or all_in_one
    enable_scheduler = role == "scheduler" or all_in_one

    if not all_in_one and role != "panel" and not is_nats_enabled():
        raise RuntimeError("NATS must be enabled when running node-worker or scheduler roles.")

    app = FastAPI(
        title="PasarGuardAPI",
        description="Unified GUI Censorship Resistant Solution",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/openapi.json" if DOCS else None,
    )

    setup_middleware(app)

    def _validate_paths():
        paths = [f"{r.path}/" for r in app.routes]
        paths.append("/api/")
        if f"/{SUBSCRIPTION_PATH}/" in paths:
            raise ValueError(f"you can't use /{SUBSCRIPTION_PATH}/ as subscription path it reserved for {app.title}")

    on_startup(_validate_paths)

    if enable_panel:
        import dashboard
        from app import telegram  # noqa: F401
        from app.routers import api_router

        dashboard.setup_dashboard(app)
        app.include_router(api_router)

    if enable_node_worker:
        from app.node import worker as node_worker  # noqa: F401

    enable_router = enable_panel or enable_node_worker
    enable_settings = enable_panel or enable_scheduler
    _register_nats_handlers(enable_router, enable_settings)
    _register_scheduler_hooks(role if not all_in_one else "scheduler")
    _register_jobs(role if not all_in_one else "scheduler")

    _use_route_names_as_operation_ids(app)

    role_label = "all-in-one" if all_in_one else role
    on_startup(lambda: logger.info(f"PasarGuard v{__version__} ({role_label})"))

    @app.exception_handler(RequestValidationError)
    def validation_exception_handler(request: Request, exc: RequestValidationError):
        details = {}
        for error in exc.errors():
            details[error["loc"][-1]] = error.get("msg")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=jsonable_encoder({"detail": details}),
        )

    return app

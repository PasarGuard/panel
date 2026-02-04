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
from config import DOCS, ROLE, SUBSCRIPTION_PATH


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


def _register_scheduler_hooks():
    # Notification queues must be initialized by any role that uses them
    # (backend/all-in-one produce, scheduler/all-in-one consume)
    if ROLE.runs_panel or ROLE.runs_scheduler:
        from app.notification.queue_manager import initialize_queues

        on_startup(initialize_queues)

    # APScheduler is needed by node and scheduler roles to run their jobs
    if not (ROLE.runs_node or ROLE.runs_scheduler):
        return

    from app.scheduler import scheduler

    on_startup(scheduler.start)
    on_shutdown(scheduler.shutdown)

    # Notification dispatcher (consumer loop) is only needed by scheduler role
    if not ROLE.runs_scheduler:
        return

    from app.notification.client import start_notification_dispatcher, stop_notification_dispatcher

    on_startup(start_notification_dispatcher)
    on_shutdown(stop_notification_dispatcher)


def _register_jobs():
    if not (ROLE.runs_node or ROLE.runs_scheduler):
        return
    from app import jobs  # noqa: F401


def create_app() -> FastAPI:
    from app.lifecycle import lifespan

    if ROLE.requires_nats and not is_nats_enabled():
        raise RuntimeError("NATS must be enabled for backend / node / scheduler roles.")

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

    if ROLE.runs_panel:
        import dashboard
        from app import telegram  # noqa: F401
        from app.routers import api_router

        dashboard.setup_dashboard(app)
        app.include_router(api_router)

    if ROLE.runs_node:
        from app.node import worker as node_worker  # noqa: F401

    if ROLE.runs_scheduler:
        from app.nats.scheduler_rpc import start_scheduler_rpc, stop_scheduler_rpc

        on_startup(start_scheduler_rpc)
        on_shutdown(stop_scheduler_rpc)

    enable_router = ROLE.runs_panel or ROLE.runs_node
    enable_settings = ROLE.runs_panel or ROLE.runs_scheduler
    _register_nats_handlers(enable_router, enable_settings)
    _register_scheduler_hooks()
    _register_jobs()

    _use_route_names_as_operation_ids(app)

    on_startup(lambda: logger.info(f"PasarGuard v{__version__} ({ROLE.value})"))

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

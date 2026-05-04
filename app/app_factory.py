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
from app.subscription.client_templates import handle_client_template_message
from app.utils.logger import get_logger
from app.version import __version__
from config import runtime_settings, subscription_env_settings


logger = get_logger("app-factory")


def _use_route_names_as_operation_ids(app: FastAPI) -> None:
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.name


def _register_nats_handlers(enable_router: bool, enable_settings: bool, enable_client_templates: bool):
    if enable_router:
        on_startup(router.start)
        on_shutdown(router.stop)
    if enable_settings:
        router.register_handler(MessageTopic.SETTING, handle_settings_message)
    if enable_client_templates:
        router.register_handler(MessageTopic.CLIENT_TEMPLATE, handle_client_template_message)


def _register_scheduler_hooks():
    from app.notification.queue_manager import initialize_queues

    on_startup(initialize_queues)

    # APScheduler is needed by node and scheduler roles to run their jobs
    if not (runtime_settings.role.runs_node or runtime_settings.role.runs_scheduler):
        return

    from app.scheduler import scheduler

    on_startup(scheduler.start)
    on_shutdown(scheduler.shutdown)

    # Notification dispatcher (consumer loop) is only needed by scheduler role
    if not runtime_settings.role.runs_scheduler:
        return

    from app.notification.client import start_notification_dispatcher, stop_notification_dispatcher

    on_startup(start_notification_dispatcher)
    on_shutdown(stop_notification_dispatcher)


def _register_jobs():
    if not (runtime_settings.role.runs_node or runtime_settings.role.runs_scheduler):
        return
    from app import jobs  # noqa: F401


def create_app() -> FastAPI:
    from app.lifecycle import lifespan

    if runtime_settings.role.requires_nats and not is_nats_enabled():
        raise RuntimeError("NATS must be enabled for backend / node / scheduler roles.")

    app = FastAPI(
        title="PasarGuardAPI",
        description="Unified GUI Censorship Resistant Solution",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/openapi.json" if runtime_settings.docs else None,
    )

    setup_middleware(app)

    def _validate_paths():
        paths = [f"{r.path}/" for r in app.routes]
        paths.append("/api/")
        if f"/{subscription_env_settings.path}/" in paths:
            raise ValueError(
                f"you can't use /{subscription_env_settings.path}/ as subscription path it reserved for {app.title}"
            )

    on_startup(_validate_paths)

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
    _register_nats_handlers(enable_router, enable_settings, enable_client_templates)
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

    return app

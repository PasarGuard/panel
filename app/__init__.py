from app.app_factory import create_app
from app.lifecycle import lifespan, on_shutdown, on_startup
from app.scheduler import scheduler
from app.utils.logger import get_logger
from app.version import __version__

logger = get_logger()

__all__ = [
    "__version__",
    "create_app",
    "lifespan",
    "logger",
    "on_shutdown",
    "on_startup",
    "scheduler",
]

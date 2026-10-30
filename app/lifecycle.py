import asyncio
import inspect
from contextlib import asynccontextmanager

from app.utils.logger import get_logger

startup_functions = []
shutdown_functions = []
_shutdown_priorities = {}
logger = get_logger("lifecycle")


def on_startup(func):
    if func not in startup_functions:
        startup_functions.append(func)
    return func


def on_shutdown(func, *, priority: int = 0):
    if func not in shutdown_functions:
        shutdown_functions.append(func)
    _shutdown_priorities[func] = priority
    return func


def _accepts_app(func) -> bool:
    try:
        return "app" in inspect.signature(func).parameters
    except TypeError, ValueError:
        return False


async def _invoke(func, app):
    if not callable(func):
        return
    accepts_app = _accepts_app(func)
    if asyncio.iscoroutinefunction(func):
        if accepts_app:
            await func(app=app)
        else:
            await func()
    else:
        if accepts_app:
            func(app=app)
        else:
            func()


@asynccontextmanager
async def lifespan(app):
    try:
        for func in startup_functions:
            await _invoke(func, app)
        yield
    finally:
        # Jobs release their ownership before dependencies close. A failed
        # notification flush must not prevent other resources from closing.
        for func in sorted(shutdown_functions, key=lambda item: _shutdown_priorities.get(item, 0)):
            try:
                await _invoke(func, app)
            except Exception:
                logger.warning("Shutdown hook failed: %s", getattr(func, "__name__", func), exc_info=True)

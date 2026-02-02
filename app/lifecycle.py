import asyncio
import inspect
from contextlib import asynccontextmanager


startup_functions = []
shutdown_functions = []


def on_startup(func):
    startup_functions.append(func)
    return func


def on_shutdown(func):
    shutdown_functions.append(func)
    return func


def _accepts_app(func) -> bool:
    try:
        return "app" in inspect.signature(func).parameters
    except (TypeError, ValueError):
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
    for func in startup_functions:
        await _invoke(func, app)
    yield

    for func in shutdown_functions:
        await _invoke(func, app)

import asyncio
from contextlib import asynccontextmanager


startup_functions = []
shutdown_functions = []


def on_startup(func):
    startup_functions.append(func)
    return func


def on_shutdown(func):
    shutdown_functions.append(func)
    return func


@asynccontextmanager
async def lifespan(app):
    for func in startup_functions:
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

import asyncio
import inspect
import logging
import math
import sys
from contextlib import asynccontextmanager
from enum import IntEnum
from threading import Lock

startup_functions = []
shutdown_functions = []
_shutdown_phases = {}
_lifespan_lock = Lock()
_lingering_cleanup = set()
_shutdown_timeout = 30.0
_hook_timeout = 5.0


class ShutdownPhase(IntEnum):
    QUIESCE = 10
    PRODUCERS = 20
    SEAL_QUEUES = 25
    DRAIN = 30
    TRANSPORTS = 40


def configure_shutdown(*, timeout, hook_timeout):
    global _shutdown_timeout, _hook_timeout
    if not all(math.isfinite(value) and value > 0 for value in (timeout, hook_timeout)):
        raise ValueError("Shutdown timeouts must be finite and positive")
    _shutdown_timeout, _hook_timeout = timeout, hook_timeout


def on_startup(func):
    if func not in startup_functions:
        startup_functions.append(func)
    return func


def on_shutdown(func=None, *, phase=ShutdownPhase.PRODUCERS):
    if func is None:
        return lambda callback: on_shutdown(callback, phase=phase)
    if func not in shutdown_functions:
        shutdown_functions.append(func)
    # Deduplication must not move an explicitly phased hook back to the default.
    if func not in _shutdown_phases or phase != ShutdownPhase.PRODUCERS:
        _shutdown_phases[func] = phase
    return func


def ordered_shutdown_functions():
    # Stable within each phase, independent of import/startup registration timing.
    return sorted(shutdown_functions, key=lambda func: _shutdown_phases.get(func, ShutdownPhase.PRODUCERS))


def _accepts_app(func) -> bool:
    try:
        return "app" in inspect.signature(func).parameters
    except TypeError, ValueError:
        return False


async def _invoke(func, app):
    if not callable(func):
        return
    result = func(app=app) if _accepts_app(func) else func()
    if inspect.isawaitable(result):
        await result


def _cleanup_finished(task):
    _lingering_cleanup.discard(task)
    if not task.cancelled():
        error = task.exception()
        if error is not None:
            logging.getLogger(__name__).error("Late cleanup failure (%s)", type(error).__name__)


async def _shutdown(app):
    errors = []
    hooks = ordered_shutdown_functions()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _shutdown_timeout
    for index, func in enumerate(hooks):
        # Reserve a share for every later hook, including transport close. A slow
        # flush must not consume the entire budget and skip all later cleanup.
        remaining = deadline - loop.time()
        budget = min(_hook_timeout, max(0, remaining) / (len(hooks) - index))
        if budget <= 0:
            errors.append(TimeoutError("Application shutdown budget exhausted"))
            break
        task = asyncio.create_task(_invoke(func, app), name=f"shutdown:{getattr(func, '__name__', 'hook')}")
        try:
            done, _ = await asyncio.wait({task}, timeout=budget * 0.8)
        except asyncio.CancelledError as exc:
            task.cancel()
            _lingering_cleanup.add(task)
            task.add_done_callback(_cleanup_finished)
            errors.append(exc)
            continue
        if task not in done:
            task.cancel()
            # Reserve the last share for cooperative finally blocks (e.g. NAK)
            # before subsequent transport hooks close their connections.
            try:
                await asyncio.wait({task}, timeout=min(budget * 0.2, max(0, deadline - loop.time())))
            except asyncio.CancelledError as exc:
                errors.append(exc)
            _lingering_cleanup.add(task)
            task.add_done_callback(_cleanup_finished)
            error = TimeoutError(f"Shutdown hook exceeded its budget: {getattr(func, '__name__', 'hook')}")
            logging.getLogger(__name__).error("%s", error)
            errors.append(error)
            # Do not await cancellation indefinitely: a hook can suppress it.
            continue
        try:
            task.result()
        except BaseException as exc:
            logging.getLogger(__name__).exception("Shutdown hook failed: %r", func)
            errors.append(exc)
    return errors


@asynccontextmanager
async def lifespan(app):
    if any(not task.done() for task in _lingering_cleanup):
        raise RuntimeError("Previous cleanup is still running; restart the process")
    if not _lifespan_lock.acquire(blocking=False):
        raise RuntimeError("Only one application lifespan may run per process")
    try:
        for func in startup_functions:
            await _invoke(func, app)
        yield
    finally:
        original_error = sys.exception()
        try:
            errors = await _shutdown(app)
        finally:
            _lifespan_lock.release()
        if errors and original_error is None:
            raise BaseExceptionGroup("Application shutdown failed", errors)

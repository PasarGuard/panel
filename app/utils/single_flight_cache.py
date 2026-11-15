"""Process-local cache for zero-argument async loaders (settings, templates, keys).

The loaders open their own database session. Request handlers often call them
after their first query, while they already hold a pooled connection. With a
plain cache every concurrent miss asks the pool for a second connection; once
the holders fill the pool nobody can return one, and all of them wait out
pool_timeout. Here only one caller runs the loader and the rest await it, and
``refresh()`` reloads in place so readers never see an empty cache after a save.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from app.utils.logger import get_logger

logger = get_logger("single-flight-cache")

_MISSING = object()


class SingleFlightCache[T]:
    def __init__(self, loader: Callable[[], Awaitable[T]]):
        functools.update_wrapper(self, loader)
        # Still an awaitable getter for inspect and unittest.mock (patch() picks AsyncMock).
        inspect.markcoroutinefunction(self)
        self._loader = loader
        self._value: T | object = _MISSING
        self._generation = 0
        self._inflight: asyncio.Task[T] | None = None

    async def __call__(self) -> T:
        value = self._value
        if value is not _MISSING:
            return value
        # Shielded: a cancelled caller (client gone) must not cancel the shared load.
        return await asyncio.shield(self._load_task())

    def _load_task(self) -> asyncio.Task[T]:
        task = self._inflight
        if task is not None and not task.done() and task.get_loop() is asyncio.get_running_loop():
            return task

        generation = self._generation

        async def _load() -> T:
            value = await self._loader()
            # A clear/refresh that landed mid-load means this value may predate the change.
            if self._generation == generation:
                self._value = value
            return value

        task = asyncio.create_task(_load(), name=f"cache-load:{self.__qualname__}")

        def _forget(done_task: asyncio.Task[T]) -> None:
            if self._inflight is done_task:
                self._inflight = None
            if not done_task.cancelled():
                done_task.exception()

        task.add_done_callback(_forget)
        self._inflight = task
        return task

    def clear(self) -> None:
        self._generation += 1
        self._value = _MISSING
        self._inflight = None

    async def refresh(self) -> None:
        """Reload now; readers keep the previous value until the new one is stored."""
        self._generation += 1
        self._inflight = None
        generation = self._generation
        task = self._load_task()
        while True:
            try:
                await asyncio.shield(task)
            except Exception as exc:
                if self._generation == generation:
                    # Never keep serving the old value after a failed reload: the next read loads lazily.
                    self._value = _MISSING
                    logger.warning(
                        f"Reloading {self.__qualname__} failed, next read will retry: {type(exc).__name__}: {exc}"
                    )
                    return
            # A newer refresh replaced this load (e.g. the NATS message right after a local save):
            # wait for it too, even if this one failed, so the caller returns only once the latest value is stored.
            if self._generation == generation or (task := self._inflight) is None:
                return
            generation = self._generation


def single_flight_cached[T](loader: Callable[[], Awaitable[T]]) -> SingleFlightCache[T]:
    return SingleFlightCache(loader)


_shielded_tasks: set[asyncio.Task] = set()


async def run_shielded[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to the end even if the caller is cancelled (post-commit cache sync must not stop half-way)."""
    task = asyncio.create_task(coro)
    _shielded_tasks.add(task)
    task.add_done_callback(_shielded_tasks.discard)
    return await asyncio.shield(task)

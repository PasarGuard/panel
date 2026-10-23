"""A pool of its own for the work that renders admin-written templates.

Rendering is CPU-bound Python that cannot be interrupted, only bounded (see limits.py). On the default executor, a
burst of heavy renders would queue up behind the same threads everything else offloads to. Here it can only make
subscriptions slower or, past the backlog, refuse them: `RenderPool.run` raises `TemplatesBusy` and the caller answers 503,
which clients retry.

Checking a template in the editor is rendering too, with many sample hosts. It has a pool of its own, so an admin who
validates in a loop can only get refused themselves, not the subscriptions of everyone.
"""

import asyncio
import functools
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from config import template_settings


class TemplatesBusy(Exception):
    pass


class RenderPool:
    def __init__(self, workers: int, backlog: int):
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="jinja")
        # Renders running plus waiting. A slot is given back when its thread is done, not when the caller stops
        # waiting, so the limit holds for renders that outlive their request.
        self._slots = asyncio.Semaphore(workers + backlog)

    async def _run[T](self, func: Callable[[], T]) -> T:
        try:
            return await asyncio.get_running_loop().run_in_executor(self._executor, func)
        finally:
            self._slots.release()

    @staticmethod
    def _forget(task: asyncio.Task) -> None:
        if not task.cancelled():
            task.exception()  # retrieved, so a failure nobody waits for any more is not logged as lost

    async def run[T](self, func: Callable[..., T], /, *args, **kwargs) -> T:
        if self._slots.locked():
            raise TemplatesBusy("too many templates are being rendered")
        await self._slots.acquire()  # free, so it does not wait
        # A task of its own, so the thread's slot is given back when it is done even if the caller stopped waiting
        task = asyncio.ensure_future(self._run(functools.partial(func, *args, **kwargs)))
        task.add_done_callback(self._forget)
        try:
            return await asyncio.wait_for(asyncio.shield(task), template_settings.render_timeout)
        except TimeoutError:
            raise TemplatesBusy("rendering took too long") from None


subscription_pool = RenderPool(template_settings.render_workers, template_settings.render_backlog)
validation_pool = RenderPool(1, 2)

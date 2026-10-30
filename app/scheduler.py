import asyncio

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class JobExecutor(AsyncIOExecutor):
    """Cancel and settle scheduled coroutines before handing their lease to a sibling."""

    async def drain(self) -> None:
        current = asyncio.current_task()
        pending = [future for future in self._pending_futures if future is not current and not future.done()]
        for future in pending:
            future.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


scheduler = AsyncIOScheduler(executors={"default": JobExecutor()}, job_defaults={"max_instances": 30}, timezone="UTC")


async def drain_jobs() -> None:
    """Pause submission and settle every executor's already-running jobs."""
    if scheduler.running:
        scheduler.pause()
        for executor in scheduler._executors.values():
            if isinstance(executor, JobExecutor):
                await executor.drain()

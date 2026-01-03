import asyncio
import json
import signal
from typing import Awaitable, Callable

from nats.js.api import DiscardPolicy, StreamConfig
from nats.js.errors import BadRequestError, TimeoutError

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_jetstream_context
from app.nats.contracts import JobMessage, JobType
from app.utils.logger import get_logger

logger = get_logger("job-worker")


Handler = Callable[[JobMessage], Awaitable[None]]


class JobWorker:
    """Minimal JetStream-based job worker skeleton."""

    def __init__(
        self,
        *,
        subject: str = "panel.jobs.>",
        stream_name: str = "PANEL_JOBS",
        durable: str = "panel-worker",
        batch_size: int = 10,
    ):
        self._subject = subject
        self._stream_name = stream_name
        self._durable = durable
        self._batch_size = batch_size
        self._handlers: dict[str, Handler] = {}

        self._nc = None
        self._js = None
        self._sub = None
        self._poll_task: asyncio.Task | None = None
        self._running = False

    def register_handler(self, job_type: JobType | str, handler: Handler):
        self._handlers[str(job_type)] = handler
        logger.debug("Registered handler for job type %s", job_type)

    async def _ensure_stream(self):
        if not self._js:
            return

        try:
            await self._js.add_stream(
                StreamConfig(
                    name=self._stream_name,
                    subjects=[self._subject],
                    discard=DiscardPolicy.Old,
                )
            )
        except BadRequestError:
            # Stream already exists
            pass
        except Exception as exc:  # pragma: no cover - defensive log
            logger.warning("Failed to ensure JetStream stream: %s", exc)

    async def start(self):
        if not is_nats_enabled():
            raise RuntimeError("NATS is disabled; enable NATS_ENABLED to start worker.")

        self._nc = await create_nats_client()
        if not self._nc:
            raise RuntimeError("Failed to connect to NATS.")

        self._js = await get_jetstream_context(self._nc)
        await self._ensure_stream()

        self._sub = await self._js.pull_subscribe(
            self._subject,
            durable=self._durable,
            stream=self._stream_name,
        )

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Worker started; consuming %s on stream %s", self._subject, self._stream_name)

    async def stop(self):
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        if self._nc:
            await self._nc.close()

        logger.info("Worker stopped")

    async def _handle_message(self, msg):
        try:
            payload = json.loads(msg.data.decode())
            job = JobMessage.model_validate(payload)
        except Exception as exc:
            logger.error("Failed to parse job message: %s", exc)
            await msg.ack()
            return

        handler = self._handlers.get(job.type)
        if not handler:
            logger.warning("No handler registered for job type %s", job.type)
            await msg.ack()
            return

        try:
            await handler(job)
            await msg.ack()
        except Exception as exc:
            logger.error("Handler error for job %s (%s): %s", job.job_id, job.type, exc)
            await msg.nak()

    async def _poll_loop(self):
        while self._running:
            try:
                msgs = await self._sub.fetch(self._batch_size, timeout=1)
            except TimeoutError:
                continue
            except Exception as exc:
                logger.error("Fetch error: %s", exc)
                await asyncio.sleep(1)
                continue

            for msg in msgs:
                await self._handle_message(msg)


async def _noop_handler(job: JobMessage):
    logger.info("Received job %s (%s) - stub handler", job.job_id, job.type)


async def main():
    worker = JobWorker()
    worker.register_handler(JobType.SCHEDULED_TASK, _noop_handler)
    worker.register_handler(JobType.NOTIFICATION_FLUSH, _noop_handler)

    await worker.start()

    # Graceful shutdown hooks
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _stop(*_: object):
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _stop)

    await stop_event.wait()
    await worker.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

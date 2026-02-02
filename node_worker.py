import asyncio
import signal
import config as app_config  # noqa: E402

app_config.RUN_SCHEDULER = True
app_config.NODE_ROLE = "node-worker"
app_config.IS_NODE_WORKER = True

from app import create_app  # noqa: E402
from app.lifecycle import lifespan  # noqa: E402
from app.nats import is_nats_enabled  # noqa: E402
from app.utils.logger import get_logger  # noqa: E402

logger = get_logger("node-worker")


app = create_app(role="node-worker")


async def main():
    if not is_nats_enabled():
        logger.warning("NATS is disabled; node worker requires NATS for remote operations.")

    stop_event = asyncio.Event()

    def handle_signal():
        stop_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, handle_signal)
    loop.add_signal_handler(signal.SIGTERM, handle_signal)

    async with lifespan(app):
        try:
            logger.info("Node worker started...")
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("Node worker shutting down...")


if __name__ == "__main__":
    try:
        if hasattr(asyncio, "run"):
            asyncio.run(main())
        else:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass

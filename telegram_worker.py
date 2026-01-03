import asyncio
import os
import signal

# Ensure the bot is not auto-registered in the FastAPI app when running standalone
os.environ.setdefault("TELEGRAM_EMBEDDED", "0")

from app.nats.broadcast import start_broadcast_client, stop_broadcast_client  # noqa: E402
from app.telegram import shutdown_telegram_bot, startup_telegram_bot  # noqa: E402
from app.utils.logger import get_logger  # noqa: E402


logger = get_logger("telegram-worker")


async def main():
    await start_broadcast_client()
    await startup_telegram_bot()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _stop(*_: object):
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            # add_signal_handler not available on some platforms (e.g., Windows)
            pass

    await stop_event.wait()

    await shutdown_telegram_bot()
    await stop_broadcast_client()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

import asyncio

import config as app_config  # noqa: E402

app_config.RUN_SCHEDULER = True
app_config.NODE_ROLE = "node-worker"
app_config.IS_NODE_WORKER = True

from app import app, lifespan  # noqa: E402
from app.nats import is_nats_enabled  # noqa: E402
from app.utils.logger import get_logger  # noqa: E402

logger = get_logger("node-worker")


async def main():
    if not is_nats_enabled():
        logger.warning("NATS is disabled; node worker requires NATS for remote operations.")

    async with lifespan(app):
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

import asyncio
from asyncio import Lock

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter, TelegramUnauthorizedError
from python_socks._errors import ProxyConnectionError

from app import on_shutdown, on_startup
from app.models.settings import RunMethod, Telegram
from app.settings import telegram_settings
from app.utils.logger import get_logger
from app.nats import is_nats_enabled

from .handlers import include_routers
from .middlewares import setup_middlewares

logger = get_logger("telegram-bot")


class TelegramBotManager:
    def __init__(self):
        self._bot: Bot | None = None
        self._polling_task: asyncio.Task | None = None
        self._lock = Lock()
        self._dp = Dispatcher()
        self._handlers_registered = False
        self._shutdown_in_progress = False
        self._stop_requested = False
        self._settings_key: tuple | None = None

    def get_bot(self) -> Bot | None:
        return self._bot

    def get_dispatcher(self) -> Dispatcher:
        return self._dp

    @staticmethod
    def _settings_key_from_model(settings: Telegram | None) -> tuple | None:
        if not settings:
            return None
        return (
            settings.enable,
            settings.token,
            settings.proxy_url,
            settings.method,
            settings.webhook_url,
            settings.webhook_secret,
        )

    async def sync_from_settings(self, force: bool = False, is_initiator: bool = False):
        settings: Telegram = await telegram_settings()
        async with self._lock:
            if self._stop_requested:
                return

            new_key = self._settings_key_from_model(settings)
            if not force and new_key == self._settings_key:
                return

            await self._shutdown_locked()

            if settings and settings.enable:
                await self._start_locked(settings, is_initiator=is_initiator)

            self._settings_key = new_key

    async def shutdown(self):
        async with self._lock:
            self._stop_requested = True
            await self._shutdown_locked()

    async def _start_locked(self, settings: Telegram, is_initiator: bool = False):
        if settings.method == RunMethod.LONGPOLLING and is_nats_enabled():
            logger.warning(
                "Long polling is not supported in multi-worker mode, skipping bot start. "
                "Please use webhook method or disable NATS and set UVICORN_WORKERS=1."
            )
            return

        logger.info("Telegram bot starting")
        session = AiohttpSession(proxy=settings.proxy_url)
        self._bot = Bot(token=settings.token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

        if not self._handlers_registered:
            try:
                # register handlers
                include_routers(self._dp)
                # register middlewares
                setup_middlewares(self._dp)
                self._handlers_registered = True
            except RuntimeError:
                pass

        try:
            if settings.method == RunMethod.LONGPOLLING:
                self._polling_task = asyncio.create_task(self._dp.start_polling(self._bot, handle_signals=False))
            else:
                # register webhook (only the initiator worker calls set_webhook to avoid rate limits)
                webhook_address = f"{settings.webhook_url}/api/tghook"
                logger.info(webhook_address)
                if is_initiator:
                    await self._bot.set_webhook(
                        webhook_address,
                        secret_token=settings.webhook_secret,
                        allowed_updates=["message", "callback_query", "inline_query"],
                        drop_pending_updates=True,
                    )
                    logger.info("Telegram bot started successfully.")
                else:
                    logger.info("Telegram bot dispatcher ready (webhook set by initiator worker).")
        except (
            TelegramNetworkError,
            ProxyConnectionError,
            TelegramBadRequest,
            TelegramUnauthorizedError,
        ) as err:
            if hasattr(err, "message"):
                logger.error(err.message)
            else:
                logger.error(err)

    async def _shutdown_locked(self):
        if self._shutdown_in_progress:
            return
        self._shutdown_in_progress = True
        try:
            if isinstance(self._bot, Bot):
                logger.info("Shutting down telegram bot")
                try:
                    if self._polling_task is not None and not self._polling_task.done():
                        logger.info("stopping long polling")
                        # Force stop the dispatcher first
                        await self._dp.stop_polling()
                        # Cancel the polling task
                        self._polling_task.cancel()
                    else:
                        await self._bot.delete_webhook(drop_pending_updates=True)
                except (
                    TelegramNetworkError,
                    TelegramRetryAfter,
                    ProxyConnectionError,
                    TelegramUnauthorizedError,
                ) as err:
                    if hasattr(err, "message"):
                        logger.error(err.message)
                    else:
                        logger.error(err)

                if self._bot.session:
                    await self._bot.session.close()

                self._bot = None
                self._polling_task = None
                logger.info("Telegram bot shut down successfully.")
        finally:
            self._shutdown_in_progress = False


telegram_bot_manager = TelegramBotManager()


def get_bot():
    return telegram_bot_manager.get_bot()


def get_dispatcher():
    return telegram_bot_manager.get_dispatcher()


async def startup_telegram_bot():
    await telegram_bot_manager.sync_from_settings(force=True, is_initiator=True)


async def shutdown_telegram_bot():
    await telegram_bot_manager.shutdown()


on_startup(startup_telegram_bot)
on_shutdown(shutdown_telegram_bot)

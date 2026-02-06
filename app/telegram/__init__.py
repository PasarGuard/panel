import asyncio
import hashlib
from asyncio import Lock

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter, TelegramUnauthorizedError
from nats.js.kv import KeyValue
from python_socks._errors import ProxyConnectionError

from app import on_shutdown, on_startup
from app.models.settings import RunMethod, Telegram
from app.settings import telegram_settings
from app.utils.logger import get_logger
from app.nats import is_nats_enabled
from app.nats.client import setup_nats_kv
from config import NATS_TELEGRAM_KV_BUCKET

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
        self._kv: KeyValue | None = None
        self._nats_conn = None

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

    async def _try_claim_webhook_initiator(self, settings: Telegram) -> bool:
        """
        Determine if this worker should call set_webhook.

        In single-worker mode (NATS disabled): always return True.
        In multi-worker mode (NATS enabled): use KV store to coordinate.
          - Compute a fingerprint of current webhook settings.
          - Get the last-set fingerprint from KV.
          - If missing or different: this is the initiator, set KV and return True.
          - If same: another worker already set it, return False.
        """
        if not is_nats_enabled():
            return True

        try:
            # Set up KV connection if not already done
            if not self._kv:
                self._nats_conn, js, self._kv = await setup_nats_kv(NATS_TELEGRAM_KV_BUCKET)
                if not self._kv:
                    logger.warning("NATS KV unavailable, allowing this worker to set webhook")
                    return True

            # Compute a fingerprint of the webhook settings
            settings_bytes = f"{settings.token}:{settings.webhook_url}:{settings.webhook_secret}".encode()
            fingerprint = hashlib.sha256(settings_bytes).hexdigest()

            # Try to get the last-set fingerprint
            try:
                entry = await self._kv.get("webhook_set")
                last_fingerprint = entry.value.decode() if entry else None
            except Exception:
                last_fingerprint = None

            # If the last fingerprint matches, skip
            if last_fingerprint == fingerprint:
                logger.info("Webhook already set by another worker, skipping set_webhook")
                return False

            # Otherwise, claim initiator role and update KV
            try:
                await self._kv.put("webhook_set", fingerprint.encode())
                logger.info("Claimed webhook initiator role, will call set_webhook")
                return True
            except Exception as e:
                logger.warning(f"Failed to update webhook fingerprint in KV: {e}, proceeding anyway")
                return True

        except Exception as e:
            logger.warning(f"KV coordination failed: {e}, allowing this worker to set webhook")
            return True

    async def sync_from_settings(self, force: bool = False):
        settings: Telegram = await telegram_settings()
        async with self._lock:
            if self._stop_requested:
                return

            new_key = self._settings_key_from_model(settings)
            if not force and new_key == self._settings_key:
                return

            await self._shutdown_locked()

            if settings and settings.enable:
                # Determine if this worker should call set_webhook
                is_initiator = (
                    await self._try_claim_webhook_initiator(settings) if settings.method == RunMethod.WEBHOOK else False
                )
                await self._start_locked(settings, is_initiator=is_initiator)

            self._settings_key = new_key

    async def shutdown(self):
        async with self._lock:
            self._stop_requested = True
            await self._shutdown_locked()
            # Close NATS KV connection if one was opened
            if self._nats_conn:
                try:
                    await self._nats_conn.close()
                except Exception:
                    pass
                self._nats_conn = None
                self._kv = None

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
            TelegramRetryAfter,
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
    await telegram_bot_manager.sync_from_settings(force=True)


async def shutdown_telegram_bot():
    await telegram_bot_manager.shutdown()


on_startup(startup_telegram_bot)
on_shutdown(shutdown_telegram_bot)

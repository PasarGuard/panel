import asyncio
import hashlib
import time
from asyncio import Lock
from contextlib import nullcontext

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from nats.js.kv import KeyValue

from app import on_shutdown, on_startup
from app.db import GetDB
from app.db.crud.settings import get_settings
from app.models.settings import RunMethod, Telegram
from app.nats import is_nats_enabled
from app.nats.client import setup_nats_kv
from app.nats.kv_cas import kv_get_json, kv_put_json
from app.nats.lease import kv_lease
from app.utils.logger import get_logger
from config import nats_settings

from .fsm_storage import NatsFSMStorage
from .handlers import include_routers
from .middlewares import setup_middlewares
from .session import NativeTLSAiohttpSession

logger = get_logger("telegram-bot")


class TelegramBotManager:
    def __init__(self):
        self._bot: Bot | None = None
        self._polling_task: asyncio.Task | None = None
        self._lock = Lock()
        self._dp = self._create_dispatcher()
        self._handlers_registered = False
        self._shutdown_in_progress = False
        self._stop_requested = False
        self._settings_key: tuple | None = None
        self._kv: KeyValue | None = None
        self._nats_conn = None
        self._retry_task: asyncio.Task | None = None
        self._webhook_verified_until = 0.0
        self._last_webhook_token: str | None = None

    @staticmethod
    def _create_dispatcher() -> Dispatcher:
        if is_nats_enabled():
            storage = NatsFSMStorage(nats_settings.telegram_kv_bucket)
            return Dispatcher(storage=storage, events_isolation=storage.create_isolation())
        return Dispatcher(storage=MemoryStorage())

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

    @staticmethod
    async def _read_settings() -> Telegram:
        """Webhook coordination must use the committed settings, not a worker's cache."""
        async with GetDB() as db:
            row = await get_settings(db)
            return Telegram.model_validate(row.telegram)

    async def _ensure_webhook_kv(self):
        if self._nats_conn is not None and self._nats_conn.is_closed:
            self._kv = self._nats_conn = None
        if self._kv is None:
            self._nats_conn, _, self._kv = await setup_nats_kv(nats_settings.telegram_kv_bucket)
        if self._kv is None:
            raise RuntimeError("Shared Telegram webhook coordination is unavailable")
        return self._kv

    @staticmethod
    def _webhook_fingerprint(settings: Telegram) -> str:
        value = f"{settings.enable}:{settings.token}:{settings.webhook_url}:{settings.webhook_secret}"
        return hashlib.sha256(value.encode()).hexdigest()

    async def _configure_webhook(self, settings: Telegram) -> None:
        """Serialize registration and record only a successful, verified outcome."""
        kv = await self._ensure_webhook_kv() if is_nats_enabled() else None
        async with kv_lease(kv, "webhook_control") if kv is not None else nullcontext():
            current = await self._read_settings()
            if self._settings_key_from_model(current) != self._settings_key_from_model(settings):
                raise RuntimeError("Telegram settings changed during registration")
            fingerprint = self._webhook_fingerprint(settings)
            receipt, _ = await kv_get_json(kv, "webhook_state_v2") if kv is not None else (None, 0)
            address = f"{settings.webhook_url}/api/tghook"
            verified = False
            if receipt is not None and receipt.get("fingerprint") == fingerprint:
                async with asyncio.timeout(10):
                    info = await self._bot.get_webhook_info()
                verified = info.url == address
            if not verified:
                async with asyncio.timeout(10):
                    await self._bot.set_webhook(
                        address,
                        secret_token=settings.webhook_secret,
                        allowed_updates=["message", "callback_query", "inline_query"],
                        drop_pending_updates=False,
                    )
            self._last_webhook_token = settings.token
            if kv is not None:
                await kv_put_json(kv, "webhook_state_v2", {"fingerprint": fingerprint})
            self._webhook_verified_until = time.monotonic() + 60

    async def _delete_obsolete_webhook(self, settings: Telegram) -> None:
        """Delete only a bot no longer selected by the committed panel settings."""
        if self._polling_task is not None:
            return
        old_token = self._last_webhook_token or (
            self._settings_key[1] if self._settings_key is not None else settings.token
        )
        if not old_token:
            return
        if settings.enable and settings.method == RunMethod.WEBHOOK and settings.token == old_token:
            return
        kv = await self._ensure_webhook_kv() if is_nats_enabled() else None
        async with kv_lease(kv, "webhook_control") if kv is not None else nullcontext():
            current = await self._read_settings()
            if current.enable and current.method == RunMethod.WEBHOOK and current.token == old_token:
                return
            fingerprint = hashlib.sha256(f"disabled:{old_token}".encode()).hexdigest()
            receipt, _ = await kv_get_json(kv, "webhook_state_v2") if kv is not None else (None, 0)
            if receipt is not None and receipt.get("fingerprint") == fingerprint:
                self._last_webhook_token = None
                return
            bot = self._bot
            temporary = bot is None or bot.token != old_token
            if temporary:
                bot = Bot(token=old_token, session=NativeTLSAiohttpSession(proxy=settings.proxy_url))
            try:
                async with asyncio.timeout(10):
                    await bot.delete_webhook(drop_pending_updates=False)
                self._last_webhook_token = None
                if kv is not None:
                    await kv_put_json(kv, "webhook_state_v2", {"fingerprint": fingerprint})
            finally:
                if temporary:
                    await bot.session.close()

    def _schedule_retry(self) -> None:
        if self._stop_requested or (self._retry_task is not None and not self._retry_task.done()):
            return
        self._retry_task = asyncio.create_task(self._retry_settings(), name="telegram-settings-retry")

    async def _retry_settings(self) -> None:
        """Retry a failed registration without turning a Telegram outage into an API startup failure."""
        try:
            while not self._stop_requested:
                await asyncio.sleep(5)
                await self.sync_from_settings()
                if self._settings_key is not None:
                    return
        finally:
            if self._retry_task is asyncio.current_task():
                self._retry_task = None

    async def sync_from_settings(self, force: bool = False):
        async with self._lock:
            if self._stop_requested:
                return
            try:
                settings = await self._read_settings()
                new_key = self._settings_key_from_model(settings)
                if not force and new_key == self._settings_key:
                    if (
                        settings.enable
                        and settings.method == RunMethod.WEBHOOK
                        and time.monotonic() >= self._webhook_verified_until
                    ):
                        await self._configure_webhook(settings)
                    return
                await self._delete_obsolete_webhook(settings)
                await self._shutdown_locked()
                if settings.enable:
                    await self._start_locked(settings)
                self._settings_key = new_key
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed set_webhook never leaves a successful fingerprint or
                # settings marker behind; another worker or this retry can repair it.
                self._settings_key = None
                logger.warning("Telegram settings synchronization failed; retrying", exc_info=True)
                self._schedule_retry()

    async def shutdown(self):
        self._stop_requested = True
        if self._retry_task is not None:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
            self._retry_task = None
        async with self._lock:
            self._stop_requested = True
            await self._shutdown_locked()
            try:
                await self._dp.fsm.close()
            except Exception:
                pass
            # Close NATS KV connection if one was opened
            if self._nats_conn:
                try:
                    await self._nats_conn.close()
                except Exception:
                    pass
                self._nats_conn = None
                self._kv = None

    async def _start_long_polling(self):
        retry_period = 30
        logger.info("Starting long polling")
        while True:
            try:
                await self._dp.start_polling(self._bot, handle_signals=False)
                logger.info("Long polling stopped")
                return

            except asyncio.CancelledError:
                logger.info("Long polling task canceled")
                return

            except Exception as err:
                logger.warning(f"Long polling failed: {err}. Retrying in {retry_period} seconds")

            await asyncio.sleep(retry_period)

    async def _start_locked(self, settings: Telegram):
        if settings.method == RunMethod.LONGPOLLING and is_nats_enabled():
            logger.warning(
                "Long polling is not supported in multi-worker mode, skipping bot start. "
                "Please use webhook method or disable NATS and set UVICORN_WORKERS=1."
            )
            return

        logger.info("Telegram bot starting")
        session = NativeTLSAiohttpSession(proxy=settings.proxy_url)
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

        if settings.method == RunMethod.LONGPOLLING:
            self._polling_task = asyncio.create_task(self._start_long_polling())
        else:
            await self._configure_webhook(settings)

    async def _shutdown_locked(self):
        if self._shutdown_in_progress:
            return
        self._shutdown_in_progress = True
        try:
            if isinstance(self._bot, Bot):
                logger.info("Shutting down telegram bot")
                if self._polling_task is not None:
                    logger.info("Stopping long polling")
                    try:
                        # Force stop the dispatcher first
                        await self._dp.stop_polling()
                    except RuntimeError:
                        # If polling was not started
                        pass

                    # Cancel the polling task
                    self._polling_task.cancel()
                    await asyncio.gather(self._polling_task, return_exceptions=True)

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

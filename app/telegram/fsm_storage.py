import asyncio
import hashlib
import json
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any, cast

import nats.js.errors as nats_js_errors
from aiogram.exceptions import DataNotDictLikeError
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import (
    BaseEventIsolation,
    BaseStorage,
    DefaultKeyBuilder,
    KeyBuilder,
    StateType,
    StorageKey,
)
from aiogram.fsm.storage.memory import MemoryStorage
from nats.js.kv import KeyValue

from app.nats import is_nats_enabled
from app.nats.client import setup_nats_kv
from app.utils.logger import get_logger

logger = get_logger("telegram-fsm")

DEFAULT_LOCK_TTL_SECONDS = 60.0
DEFAULT_LOCK_RETRY_DELAY_SECONDS = 0.05
DEFAULT_CONNECT_RETRY_BACKOFF_SECONDS = 10.0

_JsonLoads = Callable[..., Any]
_JsonDumps = Callable[..., str]


class NatsFSMStorage(BaseStorage):
    """
    Aiogram FSM storage backed by NATS KV with in-memory fallback.

    Data model follows aiogram's built-in storages:
    - state and data are stored as separate records
    - event isolation is delegated to NatsEventIsolation
    """

    def __init__(
        self,
        bucket_name: str,
        key_builder: KeyBuilder | None = None,
        json_loads: _JsonLoads = json.loads,
        json_dumps: _JsonDumps = json.dumps,
        key_prefix: str = "fsm",
    ) -> None:
        if key_builder is None:
            key_builder = DefaultKeyBuilder(
                prefix="fsm",
                with_bot_id=True,
                with_business_connection_id=True,
                with_destiny=True,
            )

        self._memory = MemoryStorage()
        self._bucket_name = bucket_name
        self._key_prefix = key_prefix
        self.key_builder = key_builder
        self.json_loads = json_loads
        self.json_dumps = json_dumps

        self._nc = None
        self._kv: KeyValue | None = None
        self._connect_lock = asyncio.Lock()
        self._next_connect_try_at = 0.0

        self._nats_enabled = is_nats_enabled()

    def create_isolation(
        self,
        lock_ttl: float = DEFAULT_LOCK_TTL_SECONDS,
        retry_delay: float = DEFAULT_LOCK_RETRY_DELAY_SECONDS,
    ) -> "NatsEventIsolation":
        return NatsEventIsolation(
            storage=self,
            key_builder=self.key_builder,
            lock_ttl=lock_ttl,
            retry_delay=retry_delay,
        )

    @staticmethod
    def _normalize_state(state: StateType = None) -> str | None:
        return cast(str | None, state.state if isinstance(state, State) else state)

    def _to_nats_key(self, raw_key: str, part: str) -> str:
        digest = hashlib.sha256(raw_key.encode()).hexdigest()
        return f"{self._key_prefix}.{part}.{digest}"

    def build_kv_key(self, key: StorageKey, part: str, key_builder: KeyBuilder | None = None) -> str:
        builder = key_builder or self.key_builder
        raw_key = builder.build(key, part)
        return self._to_nats_key(raw_key, part)

    async def ensure_kv(self) -> KeyValue | None:
        if not self._nats_enabled:
            return None

        if self._kv:
            return self._kv

        now = time.monotonic()
        if now < self._next_connect_try_at:
            return None

        async with self._connect_lock:
            if self._kv:
                return self._kv

            now = time.monotonic()
            if now < self._next_connect_try_at:
                return None

            try:
                self._nc, _, self._kv = await setup_nats_kv(self._bucket_name)
            except Exception as exc:
                logger.warning(f"Failed to initialize NATS KV for Telegram FSM: {exc}")
                self._kv = None

            if self._kv:
                self._next_connect_try_at = 0.0
                return self._kv

            self._next_connect_try_at = time.monotonic() + DEFAULT_CONNECT_RETRY_BACKOFF_SECONDS
            logger.warning("NATS KV unavailable for Telegram FSM, using in-memory fallback")
            return None

    async def _safe_get(self, kv_key: str) -> KeyValue.Entry | None:
        kv = await self.ensure_kv()
        if not kv:
            return None

        try:
            return await kv.get(kv_key)
        except nats_js_errors.KeyNotFoundError, nats_js_errors.KeyDeletedError:
            return None
        except Exception as exc:
            logger.warning(f"Failed to read Telegram FSM record from NATS KV: {exc}")
            return None

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        normalized_state = self._normalize_state(state)
        await self._memory.set_state(key, normalized_state)

        kv = await self.ensure_kv()
        if not kv:
            return

        kv_key = self.build_kv_key(key, "state")
        if normalized_state is None:
            try:
                await kv.delete(kv_key)
            except Exception:
                pass
            return

        try:
            await kv.put(kv_key, normalized_state.encode("utf-8"))
        except Exception as exc:
            logger.warning(f"Failed to write Telegram FSM state to NATS KV: {exc}")

    async def get_state(self, key: StorageKey) -> str | None:
        entry = await self._safe_get(self.build_kv_key(key, "state"))
        if entry and entry.value is not None:
            try:
                value = entry.value.decode("utf-8")
            except Exception as exc:
                logger.warning(f"Failed to decode Telegram FSM state from NATS KV: {exc}")
            else:
                await self._memory.set_state(key, value)
                return value

        return await self._memory.get_state(key)

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, dict):
            msg = f"Data must be a dict or dict-like object, got {type(data).__name__}"
            raise DataNotDictLikeError(msg)

        normalized_data = data.copy()
        await self._memory.set_data(key, normalized_data)

        kv = await self.ensure_kv()
        if not kv:
            return

        kv_key = self.build_kv_key(key, "data")
        if not normalized_data:
            try:
                await kv.delete(kv_key)
            except Exception:
                pass
            return

        try:
            payload = self.json_dumps(normalized_data)
            if isinstance(payload, bytes):
                encoded = payload
            else:
                encoded = payload.encode("utf-8")
        except TypeError:
            logger.warning("Telegram FSM data is not JSON-serializable; skipped NATS KV sync")
            return

        try:
            await kv.put(kv_key, encoded)
        except Exception as exc:
            logger.warning(f"Failed to write Telegram FSM data to NATS KV: {exc}")

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        entry = await self._safe_get(self.build_kv_key(key, "data"))
        if entry and entry.value is not None:
            try:
                raw_value = entry.value.decode("utf-8")
                payload = self.json_loads(raw_value)
            except Exception as exc:
                logger.warning(f"Failed to decode Telegram FSM data from NATS KV: {exc}")
            else:
                if isinstance(payload, dict):
                    await self._memory.set_data(key, payload)
                    return payload.copy()

                logger.warning("Invalid Telegram FSM data payload in NATS KV, expected dict")

        return await self._memory.get_data(key)

    async def close(self) -> None:
        await self._memory.close()

        if self._nc:
            try:
                await self._nc.close()
            except Exception:
                pass

        self._nc = None
        self._kv = None
        self._next_connect_try_at = 0.0


class NatsEventIsolation(BaseEventIsolation):
    def __init__(
        self,
        storage: NatsFSMStorage,
        key_builder: KeyBuilder | None = None,
        lock_ttl: float = DEFAULT_LOCK_TTL_SECONDS,
        retry_delay: float = DEFAULT_LOCK_RETRY_DELAY_SECONDS,
    ) -> None:
        if key_builder is None:
            key_builder = storage.key_builder

        self.storage = storage
        self.key_builder = key_builder
        self.lock_ttl = lock_ttl
        self.retry_delay = retry_delay
        self._local_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @staticmethod
    def _build_lock_payload(token: str, expires_at: float) -> bytes:
        return json.dumps({"token": token, "expires_at": expires_at}).encode("utf-8")

    @staticmethod
    def _parse_lock_payload(value: bytes | None) -> tuple[str, float] | None:
        if not value:
            return None

        try:
            payload = json.loads(value.decode("utf-8"))
        except Exception:
            return None

        token = payload.get("token")
        expires_at = payload.get("expires_at")

        if not isinstance(token, str):
            return None

        try:
            expires_at_value = float(expires_at)
        except TypeError, ValueError:
            return None

        return token, expires_at_value

    async def _acquire_distributed_lock(self, kv: KeyValue, lock_key: str) -> str:
        token = uuid.uuid4().hex

        while True:
            now = time.time()
            payload = self._build_lock_payload(token, now + self.lock_ttl)

            try:
                await kv.create(lock_key, payload)
                return token
            except nats_js_errors.KeyWrongLastSequenceError:
                pass
            except Exception as exc:
                logger.warning(f"Failed to create Telegram FSM lock in NATS KV: {exc}")
                await asyncio.sleep(self.retry_delay)
                continue

            try:
                entry = await kv.get(lock_key)
            except nats_js_errors.KeyNotFoundError, nats_js_errors.KeyDeletedError:
                await asyncio.sleep(self.retry_delay)
                continue
            except Exception as exc:
                logger.warning(f"Failed to read Telegram FSM lock from NATS KV: {exc}")
                await asyncio.sleep(self.retry_delay)
                continue

            lock_info = self._parse_lock_payload(entry.value)
            is_expired = lock_info is None or lock_info[1] <= now
            if is_expired:
                try:
                    await kv.update(lock_key, payload, last=entry.revision)
                    return token
                except nats_js_errors.KeyWrongLastSequenceError:
                    pass
                except Exception as exc:
                    logger.warning(f"Failed to steal expired Telegram FSM lock in NATS KV: {exc}")

            await asyncio.sleep(self.retry_delay)

    async def _release_distributed_lock(self, kv: KeyValue, lock_key: str, token: str) -> None:
        try:
            entry = await kv.get(lock_key)
        except nats_js_errors.KeyNotFoundError, nats_js_errors.KeyDeletedError:
            return
        except Exception as exc:
            logger.warning(f"Failed to read Telegram FSM lock for release from NATS KV: {exc}")
            return

        lock_info = self._parse_lock_payload(entry.value)
        if not lock_info or lock_info[0] != token:
            return

        try:
            await kv.delete(lock_key, last=entry.revision)
        except nats_js_errors.KeyWrongLastSequenceError:
            pass
        except Exception as exc:
            logger.warning(f"Failed to release Telegram FSM lock in NATS KV: {exc}")

    @asynccontextmanager
    async def lock(self, key: StorageKey) -> AsyncGenerator[None, None]:
        lock_key = self.storage.build_kv_key(key, "lock", key_builder=self.key_builder)
        kv = await self.storage.ensure_kv()

        if not kv:
            local_lock = self._local_locks[lock_key]
            async with local_lock:
                yield
            return

        token = await self._acquire_distributed_lock(kv, lock_key)
        try:
            yield
        finally:
            await self._release_distributed_lock(kv, lock_key, token)

    async def close(self) -> None:
        self._local_locks.clear()

import hashlib
import json
from asyncio import Lock
from collections.abc import Mapping
from typing import Any

from aiogram.exceptions import DataNotDictLikeError
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from nats.js.kv import KeyValue

from app.nats import is_nats_enabled
from app.nats.client import setup_nats_kv
from app.utils.logger import get_logger

logger = get_logger("telegram-fsm")


class NatsBackedMemoryStorage(BaseStorage):
    """
    Memory FSM storage with optional NATS KV synchronization.

    Local memory remains the source of truth for process-local behavior,
    while NATS KV enables cross-worker state/data sharing when available.
    """

    def __init__(self, bucket_name: str):
        self._memory = MemoryStorage()
        self._bucket_name = bucket_name

        self._nc = None
        self._kv: KeyValue | None = None

        self._connect_lock = Lock()
        self._connect_attempted = False
        self._nats_sync_enabled = is_nats_enabled()

    @staticmethod
    def _normalize_state(state: StateType = None) -> str | None:
        return state.state if isinstance(state, State) else state

    @staticmethod
    def _normalize_data(data: Any) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _build_kv_key(key: StorageKey) -> str:
        raw_key = (
            f"{key.bot_id}:{key.chat_id}:{key.user_id}:"
            f"{key.thread_id}:{key.business_connection_id}:{key.destiny}"
        )
        return f"fsm.{hashlib.sha256(raw_key.encode()).hexdigest()}"

    async def _ensure_kv(self) -> KeyValue | None:
        if not self._nats_sync_enabled:
            return None

        if self._kv:
            return self._kv

        if self._connect_attempted:
            return None

        async with self._connect_lock:
            if self._kv:
                return self._kv
            if self._connect_attempted:
                return None

            self._connect_attempted = True
            try:
                self._nc, _, self._kv = await setup_nats_kv(self._bucket_name)
            except Exception as exc:
                logger.warning(f"Failed to initialize NATS KV for FSM storage: {exc}")
                self._kv = None

            if not self._kv:
                logger.warning("NATS KV unavailable for FSM storage, falling back to in-memory FSM")

            return self._kv

    async def _load_record(self, key: StorageKey) -> dict[str, Any] | None:
        kv = await self._ensure_kv()
        if not kv:
            return None

        try:
            entry = await kv.get(self._build_kv_key(key))
        except Exception as exc:
            logger.warning(f"Failed to read FSM data from NATS KV: {exc}")
            return None

        if not entry:
            return None

        try:
            payload = json.loads(entry.value.decode())
        except Exception as exc:
            logger.warning(f"Failed to decode FSM payload from NATS KV: {exc}")
            return None

        state = payload.get("state")
        if state is not None and not isinstance(state, str):
            state = str(state)

        return {
            "state": state,
            "data": self._normalize_data(payload.get("data")),
        }

    async def _save_record(self, key: StorageKey, state: str | None, data: Mapping[str, Any]) -> None:
        kv = await self._ensure_kv()
        if not kv:
            return

        key_name = self._build_kv_key(key)
        normalized_data = dict(data)

        if state is None and not normalized_data:
            try:
                await kv.delete(key_name)
            except Exception:
                pass
            return

        try:
            payload = json.dumps({"state": state, "data": normalized_data}, ensure_ascii=False).encode()
        except TypeError:
            logger.warning("FSM data is not JSON-serializable; skipping NATS sync for this key")
            return

        try:
            await kv.put(key_name, payload)
        except Exception as exc:
            logger.warning(f"Failed to write FSM data to NATS KV: {exc}")

    async def _hydrate_memory(self, key: StorageKey, record: dict[str, Any]) -> None:
        await self._memory.set_state(key, record.get("state"))
        await self._memory.set_data(key, self._normalize_data(record.get("data")))

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        normalized_state = self._normalize_state(state)
        await self._memory.set_state(key, normalized_state)
        data = await self._memory.get_data(key)
        await self._save_record(key, normalized_state, data)

    async def get_state(self, key: StorageKey) -> str | None:
        record = await self._load_record(key)
        if record is not None:
            await self._hydrate_memory(key, record)
        return await self._memory.get_state(key)

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, dict):
            msg = f"Data must be a dict or dict-like object, got {type(data).__name__}"
            raise DataNotDictLikeError(msg)

        await self._memory.set_data(key, data)
        state = await self._memory.get_state(key)
        await self._save_record(key, state, data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        record = await self._load_record(key)
        if record is not None:
            await self._hydrate_memory(key, record)
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
        self._connect_attempted = False

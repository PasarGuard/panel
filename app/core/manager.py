import asyncio
import json
import uuid
from asyncio import Lock
from copy import deepcopy

import redis.asyncio as redis
from aiocache import cached, caches

from app import on_shutdown, on_startup
from app.core.abstract_core import AbstractCore
from app.core.redis_config import get_redis_config, is_redis_enabled
from app.core.xray import XRayConfig
from app.db import GetDB
from app.db.crud.core import get_core_configs
from app.db.models import CoreConfig
from app.utils.logger import get_logger
from config import CORE_PUBSUB_CHANNEL, MULTI_WORKER


class CoreManager:
    STATE_CACHE_KEY = "core_manager:state"

    def __init__(self):
        self._cores: dict[int, AbstractCore] = {}
        self._lock = Lock()
        self._inbounds: list[str] = []
        self._inbounds_by_tag = {}
        self._redis_enabled = is_redis_enabled()
        self._multi_worker = MULTI_WORKER
        self._cache = caches.get("default") if self._redis_enabled else None
        self._redis: redis.Redis | None = None
        self._listener_task: asyncio.Task | None = None
        self._logger = get_logger("core-manager")
        self._worker_id = uuid.uuid4().hex
        self._update_core_impl = (
            self._update_core_redis if (self._redis_enabled and self._multi_worker) else self._update_core_local
        )
        self._remove_core_impl = (
            self._remove_core_redis if (self._redis_enabled and self._multi_worker) else self._remove_core_local
        )

    def _get_redis_client(self) -> redis.Redis | None:
        if not self._redis_enabled:
            return None
        if not self._redis:
            cfg = get_redis_config()
            self._redis = redis.Redis(host=cfg["endpoint"], port=cfg["port"], db=cfg["db"])
        return self._redis

    async def _snapshot_state(self) -> dict:
        async with self._lock:
            return {
                "cores": deepcopy(self._cores),
                "inbounds": deepcopy(self._inbounds),
                "inbounds_by_tag": deepcopy(self._inbounds_by_tag),
            }

    async def _persist_state(self):
        if not self._redis_enabled:
            return
        state = await self._snapshot_state()
        await self._cache.set(self.STATE_CACHE_KEY, state)

    async def _load_state_from_cache(self) -> bool:
        if not self._redis_enabled:
            return False

        cached_state = await self._cache.get(self.STATE_CACHE_KEY)
        if not cached_state:
            return False

        async with self._lock:
            self._cores = cached_state.get("cores", {})
            self._inbounds = cached_state.get("inbounds", [])
            self._inbounds_by_tag = cached_state.get("inbounds_by_tag", {})

        await self.get_inbounds.cache.clear()
        await self.get_inbounds_by_tag.cache.clear()
        return True

    async def _reload_from_cache(self):
        loaded = await self._load_state_from_cache()
        if loaded:
            self._logger.debug("CoreManager state reloaded from Redis cache")

    def _core_payload_from_db(self, db_core_config: CoreConfig) -> dict:
        return {
            "id": db_core_config.id,
            "config": db_core_config.config,
            "exclude_inbound_tags": list(db_core_config.exclude_inbound_tags or []),
            "fallbacks_inbound_tags": list(db_core_config.fallbacks_inbound_tags or []),
        }

    async def _apply_core_payload(self, payload: dict):
        try:
            core_id = payload["id"]
            config = payload["config"]
        except Exception:
            await self._reload_from_cache()
            return

        exclude_tags = set(payload.get("exclude_inbound_tags") or [])
        fallback_tags = set(payload.get("fallbacks_inbound_tags") or [])

        class _PayloadCore:
            def __init__(self, cid, cfg, exclude, fallbacks):
                self.id = cid
                self.config = cfg
                self.exclude_inbound_tags = exclude
                self.fallbacks_inbound_tags = fallbacks

        await self._update_core_local(_PayloadCore(core_id, config, exclude_tags, fallback_tags))

    async def _publish_invalidation(self, message: dict):
        if not (self._redis_enabled and self._multi_worker):
            return

        client = self._get_redis_client()
        if not client:
            return

        try:
            message = {**message, "sender_id": self._worker_id}
            await client.publish(CORE_PUBSUB_CHANNEL, json.dumps(message))
        except Exception as exc:  # pragma: no cover - best-effort publish
            self._logger.warning(f"Failed to publish core update: {exc}")

    async def _listen_for_updates(self):
        client = self._get_redis_client()
        if not client:
            return

        pubsub = client.pubsub()
        await pubsub.subscribe(CORE_PUBSUB_CHANNEL)

        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode()

                try:
                    payload = json.loads(data)
                except Exception:
                    await self._reload_from_cache()
                    continue

                if payload.get("sender_id") == self._worker_id:
                    continue

                action = payload.get("action")
                if action == "remove":
                    core_id = payload.get("core_id")
                    if core_id:
                        await self._remove_core_local(int(core_id))
                    else:
                        await self._reload_from_cache()
                elif action == "update":
                    core_payload = payload.get("core")
                    if core_payload:
                        await self._apply_core_payload(core_payload)
                    else:
                        await self._reload_from_cache()
                else:
                    await self._reload_from_cache()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - long-running listener
            self._logger.error(f"CoreManager pubsub listener stopped: {exc}")

    async def _ensure_listener(self):
        if not (self._redis_enabled and self._multi_worker):
            return

        if self._listener_task and not self._listener_task.done():
            return

        self._listener_task = asyncio.create_task(self._listen_for_updates())

    @staticmethod
    def validate_core(
        config: dict, exclude_inbounds: set[str] | None = None, fallbacks_inbounds: set[str] | None = None
    ):
        exclude_inbounds = exclude_inbounds or set()
        fallbacks_inbounds = fallbacks_inbounds or set()
        return XRayConfig(config, exclude_inbounds.copy(), fallbacks_inbounds.copy())

    async def initialize(self, db):
        cached_loaded = await self._load_state_from_cache()
        if cached_loaded:
            await self._ensure_listener()
            return

        core_configs, _ = await get_core_configs(db)
        backends: dict[int, AbstractCore] = {}
        for config in core_configs:
            backend_config = self.validate_core(
                config.config, config.exclude_inbound_tags, config.fallbacks_inbound_tags
            )
            backends[config.id] = backend_config

        async with self._lock:
            self._cores = backends

        await self.update_inbounds()
        await self._persist_state()
        await self._ensure_listener()

    async def update_inbounds(self):
        async with self._lock:
            new_inbounds = {}
            for core in self._cores.values():
                new_inbounds.update(core.inbounds_by_tag)

            self._inbounds_by_tag = new_inbounds
            self._inbounds = list(self._inbounds_by_tag.keys())

            await self.get_inbounds.cache.clear()
            await self.get_inbounds_by_tag.cache.clear()

    async def _update_core_local(self, db_core_config: CoreConfig):
        backend_config = self.validate_core(
            db_core_config.config, db_core_config.exclude_inbound_tags, db_core_config.fallbacks_inbound_tags
        )

        async with self._lock:
            self._cores.update({db_core_config.id: backend_config})

        await self.update_inbounds()
        await self._persist_state()

    async def _update_core_redis(self, db_core_config: CoreConfig):
        await self._update_core_local(db_core_config)
        await self._publish_invalidation(
            {"action": "update", "core": self._core_payload_from_db(db_core_config)}
        )

    async def update_core(self, db_core_config: CoreConfig):
        await self._update_core_impl(db_core_config)

    async def _remove_core_local(self, core_id: int):
        async with self._lock:
            core = self._cores.get(core_id, None)
            if core:
                del self._cores[core_id]
            else:
                return

        await self.update_inbounds()
        await self._persist_state()

    async def _remove_core_redis(self, core_id: int):
        await self._remove_core_local(core_id)
        await self._publish_invalidation({"action": "remove", "core_id": core_id})

    async def remove_core(self, core_id: int):
        await self._remove_core_impl(core_id)

    async def get_core(self, core_id: int) -> AbstractCore | None:
        async with self._lock:
            core = self._cores.get(core_id, None)

            if not core:
                core = self._cores.get(1)

            return core

    @cached()
    async def get_inbounds(self) -> list[str]:
        async with self._lock:
            return deepcopy(self._inbounds)

    @cached()
    async def get_inbounds_by_tag(self) -> dict:
        async with self._lock:
            return deepcopy(self._inbounds_by_tag)

    async def get_inbound_by_tag(self, tag) -> dict:
        async with self._lock:
            inbound = self._inbounds_by_tag.get(tag, None)
            if not inbound:
                return None
            return deepcopy(inbound)


core_manager = CoreManager()


@on_startup
async def init_core_manager():
    async with GetDB() as db:
        await core_manager.initialize(db)


@on_shutdown
async def shutdown_core_manager():
    task = core_manager._listener_task
    if task and not task.done():
        task.cancel()

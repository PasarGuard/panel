import pickle
from asyncio import Lock
from copy import deepcopy

import nats
from nats.js import api
from nats.js.kv import KeyValue
from aiocache import cached

from app import on_shutdown, on_startup
from app.core.abstract_core import AbstractCore
from app.nats import is_nats_enabled
from app.nats.client import setup_nats_kv
from app.nats.message import MessageTopic
from app.nats.router import router
from app.core.xray import XRayConfig
from app.db import GetDB
from app.db.crud.core import get_core_configs
from app.db.models import CoreConfig
from app.utils.logger import get_logger
from config import MULTI_WORKER


class CoreManager:
    STATE_CACHE_KEY = "state"
    KV_BUCKET_NAME = "core_manager_state"

    def __init__(self):
        self._cores: dict[int, AbstractCore] = {}
        self._lock = Lock()
        self._inbounds: list[str] = []
        self._inbounds_by_tag = {}
        self._nats_enabled = is_nats_enabled()
        self._multi_worker = MULTI_WORKER
        self._nc: nats.NATS | None = None
        self._js: api.JetStreamContext | None = None
        self._kv: KeyValue | None = None
        self._logger = get_logger("core-manager")
        self._update_core_impl = (
            self._update_core_nats if (self._nats_enabled and self._multi_worker) else self._update_core_local
        )
        self._remove_core_impl = (
            self._remove_core_nats if (self._nats_enabled and self._multi_worker) else self._remove_core_local
        )

    async def _snapshot_state(self) -> dict:
        async with self._lock:
            return {
                "cores": deepcopy(self._cores),
                "inbounds": deepcopy(self._inbounds),
                "inbounds_by_tag": deepcopy(self._inbounds_by_tag),
            }

    async def _persist_state(self):
        if not self._kv:
            return
        state = await self._snapshot_state()
        # Serialize state using pickle (same as Redis implementation)
        state_bytes = pickle.dumps(state)
        await self._kv.put(self.STATE_CACHE_KEY, state_bytes)

    async def _load_state_from_cache(self) -> bool:
        if not self._kv:
            return False

        try:
            entry = await self._kv.get(self.STATE_CACHE_KEY)
            if not entry:
                return False

            # Deserialize state using pickle (same as Redis implementation)
            cached_state = pickle.loads(entry.value)
            async with self._lock:
                self._cores = cached_state.get("cores", {})
                self._inbounds = cached_state.get("inbounds", [])
                self._inbounds_by_tag = cached_state.get("inbounds_by_tag", {})

            await self.get_inbounds.cache.clear()
            await self.get_inbounds_by_tag.cache.clear()
            return True
        except Exception:
            return False

    async def _reload_from_cache(self):
        loaded = await self._load_state_from_cache()
        if loaded:
            self._logger.debug("CoreManager state reloaded from JetStream KV cache")

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

    async def _handle_core_message(self, data: dict):
        """Handle incoming core messages from router."""
        action = data.get("action")
        if action == "remove":
            core_id = data.get("core_id")
            if core_id:
                await self._remove_core_local(int(core_id))
            else:
                await self._reload_from_cache()
        elif action == "update":
            core_payload = data.get("core")
            if core_payload:
                await self._apply_core_payload(core_payload)
            else:
                await self._reload_from_cache()
        else:
            await self._reload_from_cache()

    async def _publish_invalidation(self, message: dict):
        """Publish core update message via global router."""
        await router.publish(MessageTopic.CORE, message)

    @staticmethod
    def validate_core(
        config: dict, exclude_inbounds: set[str] | None = None, fallbacks_inbounds: set[str] | None = None
    ):
        exclude_inbounds = exclude_inbounds or set()
        fallbacks_inbounds = fallbacks_inbounds or set()
        return XRayConfig(config, exclude_inbounds.copy(), fallbacks_inbounds.copy())

    async def initialize(self, db):
        # Register handler with global router
        router.register_handler(MessageTopic.CORE, self._handle_core_message)

        # Initialize NATS if enabled
        if self._nats_enabled:
            self._nc, self._js, self._kv = await setup_nats_kv(self.KV_BUCKET_NAME)

        cached_loaded = await self._load_state_from_cache()
        if cached_loaded:
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

    async def _update_core_nats(self, db_core_config: CoreConfig):
        # Validate core before publishing (but don't update locally)
        # All workers (including this one) will update via listener
        self.validate_core(
            db_core_config.config, db_core_config.exclude_inbound_tags, db_core_config.fallbacks_inbound_tags
        )
        await self._publish_invalidation({"action": "update", "core": self._core_payload_from_db(db_core_config)})

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

    async def _remove_core_nats(self, core_id: int):
        # Don't remove locally - all workers (including this one) will remove via listener
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
    # Close NATS connection
    if core_manager._nc:
        await core_manager._nc.close()

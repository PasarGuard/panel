import json
from asyncio import Lock
from copy import deepcopy
from typing import ClassVar

import nats
from nats.js.client import JetStreamContext
from nats.js.kv import KeyValue

from app import on_shutdown, on_startup
from app.core.abstract_core import AbstractCore
from app.core.wireguard import WireGuardConfig
from app.core.xray import XRayConfig
from app.db import AsyncSession, GetDB
from app.db.crud.core import get_core_configs
from app.db.models import CoreConfig, CoreType
from app.models.core import CoreListQuery
from app.nats import is_multi_worker, is_nats_enabled
from app.nats.client import setup_nats_kv
from app.nats.message import MessageTopic
from app.nats.router import router
from app.utils.logger import get_logger


class CoreManager:
    STATE_CACHE_KEY = "state"
    KV_BUCKET_NAME = "core_manager_state"
    CORE_CLASSES: ClassVar[dict] = {
        CoreType.xray: XRayConfig,
        CoreType.wg: WireGuardConfig,
    }

    def __init__(self):
        self._cores: dict[int, AbstractCore] = {}
        self._lock = Lock()
        self._inbounds: list[str] = []
        self._inbounds_by_tag = {}
        self._nats_enabled = is_nats_enabled()
        self._multi_worker = is_multi_worker()
        self._nc: nats.NATS | None = None
        self._js: JetStreamContext | None = None
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
                "cores": {k: v.to_json() for k, v in self._cores.items()},
                "inbounds": list(self._inbounds),
                "inbounds_by_tag": dict(self._inbounds_by_tag),
            }

    async def _persist_state(self):
        # Keep publishing snapshots for older workers during rolling upgrades.
        # Current workers always read committed configs from the database.
        if not self._kv:
            return
        state = await self._snapshot_state()
        try:
            state_bytes = json.dumps(state).encode("utf-8")
            await self._kv.put(self.STATE_CACHE_KEY, state_bytes)
        except Exception as exc:
            self._logger.warning(f"Failed to persist core state to NATS KV: {exc}")

    async def reload(self, core_ids: set[int] | None = None):
        async with GetDB() as db:
            await self._refresh_from_db(db, core_ids)

    def _core_payload_from_db(self, db_core_config: CoreConfig) -> dict:
        return {
            "id": db_core_config.id,
            "type": db_core_config.type,
            "config": db_core_config.config,
            "exclude_inbound_tags": list(db_core_config.exclude_inbound_tags or []),
            "fallbacks_inbound_tags": list(db_core_config.fallbacks_inbound_tags or []),
        }

    @classmethod
    def _normalize_type(cls, type: CoreType | None) -> CoreType:
        if not type:
            return CoreType.xray
        return type

    def _get_core_class(self, type: CoreType | None):
        normalized_type = self._normalize_type(type)
        return self.CORE_CLASSES[normalized_type]

    async def _handle_core_message(self, data: dict):
        """Treat messages as invalidations; delayed payloads must not undo newer edits."""
        payload = data.get("core")
        core_id = payload.get("id") if isinstance(payload, dict) else data.get("core_id")
        await self.reload({int(core_id)} if core_id is not None else None)

    async def _publish_invalidation(self, message: dict):
        """Publish core update message via global router."""
        await router.publish(MessageTopic.CORE, message)

    def validate_core(
        self,
        config: dict,
        exclude_inbounds: set[str] | None = None,
        fallbacks_inbounds: set[str] | None = None,
        type: CoreType | None = None,
    ):
        exclude_inbounds = exclude_inbounds or set()
        fallbacks_inbounds = fallbacks_inbounds or set()
        core_class = self._get_core_class(type)
        return core_class(config, exclude_inbounds.copy(), fallbacks_inbounds.copy())

    async def initialize(self, db):
        # Register handler with global router
        router.register_handler(MessageTopic.CORE, self._handle_core_message)

        # Initialize NATS if enabled
        if self._nats_enabled:
            self._nc, self._js, self._kv = await setup_nats_kv(self.KV_BUCKET_NAME)

        await self._refresh_from_db(db)
        await self._persist_state()

    async def _refresh_from_db(
        self, db: AsyncSession, core_ids: list[int] | set[int] | None = None
    ) -> dict[int, AbstractCore]:
        if core_ids is not None and not core_ids:
            return {}
        # Refresh cores and their inbound index together with other cache mutations.
        # A failed DB read leaves the cache intact.
        async with self._lock:
            core_configs, _ = await get_core_configs(
                db, CoreListQuery(ids=list(core_ids) if core_ids is not None else None)
            )
            cores: dict[int, AbstractCore] = {}
            for config in core_configs:
                try:
                    cores[config.id] = self.validate_core(
                        config.config,
                        config.exclude_inbound_tags,
                        config.fallbacks_inbound_tags,
                        config.type,
                    )
                except Exception as exc:
                    self._logger.error(
                        "Skipping broken core id=%s name=%r type=%s: %s",
                        config.id,
                        getattr(config, "name", None),
                        config.type,
                        exc,
                    )
            if core_ids is None:
                self._cores = cores
            else:
                for core_id in core_ids:
                    self._cores.pop(core_id, None)
                self._cores.update(cores)
            self._update_inbounds_locked()
            return {core_id: deepcopy(core) for core_id, core in cores.items()}

    async def update_inbounds(self):
        async with self._lock:
            self._update_inbounds_locked()

    def _update_inbounds_locked(self):
        new_inbounds = {}
        for core in self._cores.values():
            new_inbounds.update(core.inbounds_by_tag)

        self._inbounds_by_tag = new_inbounds
        self._inbounds = list(self._inbounds_by_tag.keys())

    async def _update_core_local(self, db_core_config: CoreConfig, core_config: AbstractCore | None = None):
        if core_config is None:
            try:
                core_config = self.validate_core(
                    db_core_config.config,
                    db_core_config.exclude_inbound_tags,
                    db_core_config.fallbacks_inbound_tags,
                    db_core_config.type,
                )
            except Exception as exc:
                self._logger.error(
                    "Skipping broken core id=%s type=%s: %s",
                    getattr(db_core_config, "id", None),
                    getattr(db_core_config, "type", None),
                    exc,
                )
                return

        async with self._lock:
            self._cores.update({db_core_config.id: core_config})
            self._update_inbounds_locked()

        await self._persist_state()

    async def _update_core_nats(self, db_core_config: CoreConfig, core_config: AbstractCore | None = None):
        # Publish only after the committed config is available locally.
        await self._update_core_local(db_core_config, core_config)
        try:
            await self._publish_invalidation({"action": "update", "core": self._core_payload_from_db(db_core_config)})
        except Exception as exc:
            self._logger.warning(f"Failed to publish core update via NATS: {exc}")

    async def update_core(self, db_core_config: CoreConfig, core_config: AbstractCore | None = None):
        await self._update_core_impl(db_core_config, core_config)

    async def _remove_core_local(self, core_id: int):
        async with self._lock:
            core = self._cores.get(core_id, None)
            if core:
                del self._cores[core_id]
            else:
                return
            self._update_inbounds_locked()

        await self._persist_state()

    async def _remove_core_nats(self, core_id: int):
        # Persist local removal (and KV snapshot) before broadcasting.
        await self._remove_core_local(core_id)

        try:
            await self._publish_invalidation({"action": "remove", "core_id": core_id})
        except Exception as exc:
            self._logger.warning(f"Failed to publish core remove via NATS: {exc}")

    async def remove_core(self, core_id: int):
        await self._remove_core_impl(core_id)

    async def get_core(self, core_id: int) -> AbstractCore | None:
        async with self._lock:
            return deepcopy(self._cores.get(core_id))

    async def get_cores(
        self, core_ids: list[int] | set[int] | None = None, *, db: AsyncSession | None = None
    ) -> dict[int, AbstractCore]:
        if db is not None:
            return await self._refresh_from_db(db, core_ids)
        async with self._lock:
            if core_ids is None:
                return {core_id: deepcopy(core) for core_id, core in self._cores.items()}
            return {core_id: deepcopy(core) for core_id, core in self._cores.items() if core_id in core_ids}

    async def get_inbounds(self) -> list[str]:
        async with self._lock:
            return list(self._inbounds)

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

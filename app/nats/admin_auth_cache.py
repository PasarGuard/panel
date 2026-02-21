import asyncio
from datetime import datetime, timezone

import nats
from nats.js.kv import KeyValue

from app.db import GetDB
from app.db.crud.admin import get_admins_for_auth_cache
from app.lifecycle import on_shutdown, on_startup
from app.models.admin import AdminAuthKVEntry, AdminAuthKVIndex
from app.nats import is_nats_enabled
from app.nats.client import setup_nats_kv
from app.utils.logger import get_logger
from config import NATS_ADMIN_AUTH_KV_BUCKET, ROLE


class AdminAuthCacheError(Exception):
    pass


class AdminAuthCacheUnavailableError(AdminAuthCacheError):
    pass


class AdminAuthCacheCorruptedError(AdminAuthCacheError):
    pass


class AdminAuthCacheService:
    KEY_PREFIX = "admin_auth."
    INDEX_KEY = "admin_auth._index"

    def __init__(self):
        self._nats_enabled = is_nats_enabled()
        self._writer_enabled = ROLE.runs_scheduler
        self._reader_enabled = ROLE.runs_panel
        self._nc: nats.NATS | None = None
        self._kv: KeyValue | None = None
        self._connect_lock = asyncio.Lock()
        self._kv_write_lock = asyncio.Lock()
        self._logger = get_logger("admin-auth-cache")

    @classmethod
    def _admin_key(cls, username: str) -> str:
        return f"{cls.KEY_PREFIX}{username}"

    @staticmethod
    def _is_key_not_found(exc: Exception) -> bool:
        exc_name = exc.__class__.__name__
        if exc_name == "KeyNotFoundError":
            return True
        return "key not found" in str(exc).lower()

    async def _ensure_kv(self) -> bool:
        if self._kv:
            return True

        async with self._connect_lock:
            if self._kv:
                return True

            try:
                self._nc, _, self._kv = await setup_nats_kv(NATS_ADMIN_AUTH_KV_BUCKET)
            except Exception as exc:
                self._logger.warning(f"Failed to setup admin auth KV: {exc}")
                self._kv = None
                self._nc = None

            return self._kv is not None

    async def _load_index(self) -> AdminAuthKVIndex | None:
        if not self._kv:
            raise AdminAuthCacheUnavailableError("Admin auth KV client is not ready")

        try:
            entry = await self._kv.get(self.INDEX_KEY)
        except Exception as exc:
            if self._is_key_not_found(exc):
                return None
            raise AdminAuthCacheUnavailableError("Failed to read admin auth index from KV") from exc

        if not entry or not entry.value:
            return None

        try:
            return AdminAuthKVIndex.model_validate_json(entry.value.decode("utf-8"))
        except Exception as exc:
            raise AdminAuthCacheCorruptedError("Admin auth index in KV is corrupted") from exc

    async def refresh_now(self):
        if not self._writer_enabled:
            return
        if not await self._ensure_kv():
            raise AdminAuthCacheUnavailableError("Admin auth KV bucket is unavailable")
        if not self._kv:
            raise AdminAuthCacheUnavailableError("Admin auth KV bucket is unavailable")

        async with GetDB() as db:
            db_admins = await get_admins_for_auth_cache(db)

        generated_at = datetime.now(timezone.utc)
        old_index = await self._load_index()
        old_usernames = set(old_index.usernames if old_index else [])
        new_usernames: set[str] = set()

        async with self._kv_write_lock:
            for admin in db_admins:
                key = self._admin_key(admin.username)
                cache_entry = AdminAuthKVEntry(
                    id=admin.id,
                    username=admin.username,
                    is_sudo=admin.is_sudo,
                    is_disabled=admin.is_disabled,
                    password_reset_at=admin.password_reset_at,
                    updated_at=generated_at,
                )
                await self._kv.put(key, cache_entry.model_dump_json().encode("utf-8"))
                new_usernames.add(admin.username)

            stale_usernames = old_usernames - new_usernames
            for username in stale_usernames:
                try:
                    await self._kv.delete(self._admin_key(username))
                except Exception:
                    continue

            new_index = AdminAuthKVIndex(usernames=sorted(new_usernames), generated_at=generated_at)
            await self._kv.put(self.INDEX_KEY, new_index.model_dump_json().encode("utf-8"))
        self._logger.debug(f"Admin auth KV refreshed with {len(new_usernames)} admins")

    async def _update_index_for_username(self, username: str, remove: bool):
        if not self._kv:
            raise AdminAuthCacheUnavailableError("Admin auth KV bucket is unavailable")

        try:
            index = await self._load_index()
            usernames = set(index.usernames if index else [])
        except AdminAuthCacheCorruptedError:
            usernames = set()

        if remove:
            usernames.discard(username)
        else:
            usernames.add(username)

        new_index = AdminAuthKVIndex(usernames=sorted(usernames), generated_at=datetime.now(timezone.utc))
        await self._kv.put(self.INDEX_KEY, new_index.model_dump_json().encode("utf-8"))

    async def upsert_admin_entry(
        self,
        *,
        admin_id: int,
        username: str,
        is_sudo: bool,
        is_disabled: bool,
        password_reset_at,
    ):
        if not self._nats_enabled:
            return
        if not await self._ensure_kv():
            raise AdminAuthCacheUnavailableError("Admin auth KV bucket is unavailable")
        if not self._kv:
            raise AdminAuthCacheUnavailableError("Admin auth KV bucket is unavailable")

        payload = AdminAuthKVEntry(
            id=admin_id,
            username=username,
            is_sudo=is_sudo,
            is_disabled=is_disabled,
            password_reset_at=password_reset_at,
            updated_at=datetime.now(timezone.utc),
        )
        async with self._kv_write_lock:
            await self._kv.put(self._admin_key(username), payload.model_dump_json().encode("utf-8"))
            await self._update_index_for_username(username=username, remove=False)

    async def delete_admin_entry(self, username: str):
        if not self._nats_enabled:
            return
        if not await self._ensure_kv():
            raise AdminAuthCacheUnavailableError("Admin auth KV bucket is unavailable")
        if not self._kv:
            raise AdminAuthCacheUnavailableError("Admin auth KV bucket is unavailable")

        async with self._kv_write_lock:
            try:
                await self._kv.delete(self._admin_key(username))
            except Exception as exc:
                if not self._is_key_not_found(exc):
                    raise
            await self._update_index_for_username(username=username, remove=True)

    async def start(self):
        if not self._nats_enabled:
            return
        if not (self._reader_enabled or self._writer_enabled):
            return

        await self._ensure_kv()

    async def stop(self):
        if self._nc:
            try:
                await self._nc.close()
            except Exception:
                pass

        self._kv = None
        self._nc = None

    async def get_admin(self, username: str) -> AdminAuthKVEntry:
        if not self._nats_enabled:
            raise AdminAuthCacheUnavailableError("NATS is disabled for admin auth cache")
        if not await self._ensure_kv():
            raise AdminAuthCacheUnavailableError("Admin auth KV bucket is unavailable")
        if not self._kv:
            raise AdminAuthCacheUnavailableError("Admin auth KV bucket is unavailable")

        index = await self._load_index()
        if not index:
            raise AdminAuthCacheUnavailableError("Admin auth cache is not initialized yet")

        try:
            entry = await self._kv.get(self._admin_key(username))
        except Exception as exc:
            if self._is_key_not_found(exc):
                raise AdminAuthCacheUnavailableError("Admin auth cache entry is missing") from exc
            raise AdminAuthCacheUnavailableError("Failed to read admin auth cache entry") from exc

        if not entry or not entry.value:
            raise AdminAuthCacheUnavailableError("Admin auth cache entry is empty")

        try:
            return AdminAuthKVEntry.model_validate_json(entry.value.decode("utf-8"))
        except Exception as exc:
            raise AdminAuthCacheCorruptedError("Admin auth cache entry is corrupted") from exc


admin_auth_cache_service = AdminAuthCacheService()


async def upsert_admin_auth_entry(db_admin):
    await admin_auth_cache_service.upsert_admin_entry(
        admin_id=db_admin.id,
        username=db_admin.username,
        is_sudo=db_admin.is_sudo,
        is_disabled=db_admin.is_disabled,
        password_reset_at=db_admin.password_reset_at,
    )


async def delete_admin_auth_entry(username: str):
    await admin_auth_cache_service.delete_admin_entry(username)


@on_startup
async def startup_admin_auth_cache():
    await admin_auth_cache_service.start()


@on_shutdown
async def shutdown_admin_auth_cache():
    await admin_auth_cache_service.stop()

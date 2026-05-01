from app.db import AsyncSession
from app.db.crud.hwid import (
    HWIDDecision,
    add_hwid_device,
    delete_all_hwid_devices,
    delete_hwid_device,
    enforce_hwid_device_limit,
    get_hwid_top_users,
    get_hwid_stats,
    list_hwid_devices,
)
from app.db.models import User
from app.models.admin import AdminDetails
from app.models.settings import Subscription as SubscriptionSettings
from app.operation import BaseOperation


class HWIDOperation(BaseOperation):
    async def enforce_subscription_hwid(
        self,
        db: AsyncSession,
        *,
        user: User,
        subscription_settings: SubscriptionSettings,
        hwid: str | None,
        device_os: str | None,
        os_version: str | None,
        device_model: str | None,
        user_agent: str | None,
        request_ip: str | None,
    ) -> HWIDDecision:
        if not subscription_settings.hwid_device_limit_enabled:
            return HWIDDecision(allowed=True)
        if user.hwid_limit_disabled:
            return HWIDDecision(allowed=True)

        limit = user.hwid_device_limit
        if limit is None:
            limit = subscription_settings.hwid_fallback_device_limit
        if not limit or limit <= 0:
            return HWIDDecision(allowed=True)

        return await enforce_hwid_device_limit(
            db,
            user=user,
            hwid=hwid,
            device_os=device_os,
            os_version=os_version,
            device_model=device_model,
            user_agent=user_agent,
            request_ip=request_ip,
            limit=limit,
        )

    async def list_devices(
        self, db: AsyncSession, admin: AdminDetails, *, offset: int = 0, limit: int = 50, user_id: int | None = None
    ):
        if user_id is not None:
            db_user = await self.get_validated_user_by_id(db, user_id, admin, load_usage_logs=False)
            user_id = db_user.id
        elif not admin.is_sudo:
            await self.raise_error("You're not allowed", 403)
        return await list_hwid_devices(db, offset=offset, limit=limit, user_id=user_id)

    async def stats(self, db: AsyncSession, admin: AdminDetails):
        if not admin.is_sudo:
            await self.raise_error("You're not allowed", 403)
        return await get_hwid_stats(db)

    async def delete_device(self, db: AsyncSession, admin: AdminDetails, *, user_id: int, hwid_hash: str) -> int:
        db_user = await self.get_validated_user_by_id(db, user_id, admin, load_usage_logs=False)
        return await delete_hwid_device(db, user_id=db_user.id, hwid_hash=hwid_hash)

    async def delete_all_devices(self, db: AsyncSession, admin: AdminDetails, *, user_id: int) -> int:
        db_user = await self.get_validated_user_by_id(db, user_id, admin, load_usage_logs=False)
        return await delete_all_hwid_devices(db, user_id=db_user.id)

    async def add_device(self, db: AsyncSession, admin: AdminDetails, *, user_id: int, **payload):
        db_user = await self.get_validated_user_by_id(db, user_id, admin, load_usage_logs=False)
        try:
            return await add_hwid_device(db, user_id=db_user.id, **payload)
        except ValueError as exc:
            await self.raise_error(str(exc), 400)

    async def top_users(self, db: AsyncSession, admin: AdminDetails, *, limit: int = 20):
        if not admin.is_sudo:
            await self.raise_error("You're not allowed", 403)
        return await get_hwid_top_users(db, limit=limit)


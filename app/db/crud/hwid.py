from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HWIDUserDevice, User
from config import HWID_HASH_SALT

_HWID_MAX_LEN = 256
_DEVICE_OS_MAX_LEN = 64
_OS_VERSION_MAX_LEN = 64
_DEVICE_MODEL_MAX_LEN = 128
_USER_AGENT_MAX_LEN = 512
_REQUEST_IP_MAX_LEN = 64


def _clamp(value: str | None, max_len: int) -> str | None:
    if not value:
        return None
    return value.strip()[:max_len] or None


def normalize_hwid(value: str) -> str:
    return value.strip()


def hash_hwid(hwid: str) -> str:
    # Expects normalized HWID input.
    digest = hmac.new(HWID_HASH_SALT.encode("utf-8"), hwid.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


@dataclass
class HWIDDecision:
    allowed: bool
    max_devices_reached: bool = False
    missing_hwid: bool = False


async def enforce_hwid_device_limit(
    db: AsyncSession,
    *,
    user: User,
    hwid: str | None,
    device_os: str | None,
    os_version: str | None,
    device_model: str | None,
    user_agent: str | None,
    request_ip: str | None,
    limit: int,
) -> HWIDDecision:
    if not hwid:
        return HWIDDecision(allowed=False, missing_hwid=True)

    normalized_hwid = normalize_hwid(hwid)
    if not normalized_hwid or len(normalized_hwid) > _HWID_MAX_LEN:
        return HWIDDecision(allowed=False, missing_hwid=True)

    hwid_hash = hash_hwid(normalized_hwid)
    now = datetime.now(timezone.utc)

    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    should_commit = False
    decision = HWIDDecision(allowed=True)
    async with tx_ctx:
        # Force a row-level write lock to serialize per-user registrations.
        # This is more reliable across dialects than relying on FOR UPDATE semantics.
        await db.execute(update(User).where(User.id == user.id).values(id=User.id))

        existing = (
            await db.execute(
                select(HWIDUserDevice).where(HWIDUserDevice.user_id == user.id, HWIDUserDevice.hwid_hash == hwid_hash)
            )
        ).scalar_one_or_none()

        if existing:
            existing.last_seen_at = now
            existing.device_os = _clamp(device_os, _DEVICE_OS_MAX_LEN)
            existing.os_version = _clamp(os_version, _OS_VERSION_MAX_LEN)
            existing.device_model = _clamp(device_model, _DEVICE_MODEL_MAX_LEN)
            existing.user_agent = _clamp(user_agent, _USER_AGENT_MAX_LEN)
            existing.request_ip = _clamp(request_ip, _REQUEST_IP_MAX_LEN)
            existing.updated_at = now
            should_commit = True
            decision = HWIDDecision(allowed=True)
        else:
            count_stmt = select(func.count(HWIDUserDevice.id)).where(HWIDUserDevice.user_id == user.id)
            existing_count = int((await db.execute(count_stmt)).scalar_one() or 0)
            if existing_count >= limit:
                decision = HWIDDecision(allowed=False, max_devices_reached=True)
            else:
                db.add(
                    HWIDUserDevice(
                        user_id=user.id,
                        hwid_hash=hwid_hash,
                        device_os=_clamp(device_os, _DEVICE_OS_MAX_LEN),
                        os_version=_clamp(os_version, _OS_VERSION_MAX_LEN),
                        device_model=_clamp(device_model, _DEVICE_MODEL_MAX_LEN),
                        user_agent=_clamp(user_agent, _USER_AGENT_MAX_LEN),
                        request_ip=_clamp(request_ip, _REQUEST_IP_MAX_LEN),
                        updated_at=now,
                    )
                )
                should_commit = True
                decision = HWIDDecision(allowed=True)

    if should_commit:
        await db.commit()
    return decision


async def list_hwid_devices(
    db: AsyncSession, *, offset: int = 0, limit: int = 50, user_id: int | None = None
) -> tuple[list[dict], int]:
    stmt = select(HWIDUserDevice, User.username).join(User, User.id == HWIDUserDevice.user_id, isouter=True)
    if user_id is not None:
        stmt = stmt.where(HWIDUserDevice.user_id == user_id)
    count_stmt = select(func.count(HWIDUserDevice.id))
    if user_id is not None:
        count_stmt = count_stmt.where(HWIDUserDevice.user_id == user_id)
    count = int((await db.execute(count_stmt)).scalar() or 0)
    stmt = stmt.order_by(desc(HWIDUserDevice.last_seen_at)).offset(offset).limit(limit)
    rows = (await db.execute(stmt)).all()
    items: list[dict] = []
    for device, username in rows:
        items.append(
            {
                "id": device.id,
                "user_id": device.user_id,
                "username": username,
                "hwid_hash": device.hwid_hash,
                "device_os": device.device_os,
                "os_version": device.os_version,
                "device_model": device.device_model,
                "user_agent": device.user_agent,
                "request_ip": device.request_ip,
                "first_seen_at": device.first_seen_at,
                "last_seen_at": device.last_seen_at,
                "created_at": device.created_at,
                "updated_at": device.updated_at,
            }
        )
    return items, count


async def add_hwid_device(
    db: AsyncSession,
    *,
    user_id: int,
    hwid: str,
    device_os: str | None = None,
    os_version: str | None = None,
    device_model: str | None = None,
    user_agent: str | None = None,
    request_ip: str | None = None,
) -> tuple[dict, bool]:
    normalized_hwid = normalize_hwid(hwid)
    if not normalized_hwid or len(normalized_hwid) > _HWID_MAX_LEN:
        raise ValueError("Invalid HWID")

    hwid_hash = hash_hwid(normalized_hwid)
    now = datetime.now(timezone.utc)

    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    async with tx_ctx:
        await db.execute(update(User).where(User.id == user_id).values(id=User.id))

        existing = (
            await db.execute(
                select(HWIDUserDevice).where(HWIDUserDevice.user_id == user_id, HWIDUserDevice.hwid_hash == hwid_hash)
            )
        ).scalar_one_or_none()

        if existing:
            existing.last_seen_at = now
            existing.device_os = _clamp(device_os, _DEVICE_OS_MAX_LEN)
            existing.os_version = _clamp(os_version, _OS_VERSION_MAX_LEN)
            existing.device_model = _clamp(device_model, _DEVICE_MODEL_MAX_LEN)
            existing.user_agent = _clamp(user_agent, _USER_AGENT_MAX_LEN)
            existing.request_ip = _clamp(request_ip, _REQUEST_IP_MAX_LEN)
            existing.updated_at = now
            device = existing
            created = False
        else:
            device = HWIDUserDevice(
                user_id=user_id,
                hwid_hash=hwid_hash,
                device_os=_clamp(device_os, _DEVICE_OS_MAX_LEN),
                os_version=_clamp(os_version, _OS_VERSION_MAX_LEN),
                device_model=_clamp(device_model, _DEVICE_MODEL_MAX_LEN),
                user_agent=_clamp(user_agent, _USER_AGENT_MAX_LEN),
                request_ip=_clamp(request_ip, _REQUEST_IP_MAX_LEN),
                updated_at=now,
            )
            db.add(device)
            await db.flush()
            created = True

        username = (
            await db.execute(select(User.username).where(User.id == user_id))
        ).scalar_one_or_none()

    await db.commit()
    return (
        {
            "id": device.id,
            "user_id": device.user_id,
            "username": username,
            "hwid_hash": device.hwid_hash,
            "device_os": device.device_os,
            "os_version": device.os_version,
            "device_model": device.device_model,
            "user_agent": device.user_agent,
            "request_ip": device.request_ip,
            "first_seen_at": device.first_seen_at,
            "last_seen_at": device.last_seen_at,
            "created_at": device.created_at,
            "updated_at": device.updated_at,
        },
        created,
    )


async def delete_hwid_device(db: AsyncSession, *, user_id: int, hwid_hash: str) -> int:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    async with tx_ctx:
        result = await db.execute(
            delete(HWIDUserDevice).where(HWIDUserDevice.user_id == user_id, HWIDUserDevice.hwid_hash == hwid_hash)
        )
    await db.commit()
    return int(result.rowcount or 0)


async def delete_all_hwid_devices(db: AsyncSession, *, user_id: int) -> int:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    async with tx_ctx:
        result = await db.execute(delete(HWIDUserDevice).where(HWIDUserDevice.user_id == user_id))
    await db.commit()
    return int(result.rowcount or 0)


async def get_hwid_stats(db: AsyncSession) -> dict[str, int]:
    total_devices = int((await db.execute(select(func.count(HWIDUserDevice.id)))).scalar() or 0)
    users_with_devices = int(
        (
            await db.execute(
                select(func.count(func.distinct(HWIDUserDevice.user_id)))
            )
        ).scalar()
        or 0
    )
    return {"total_devices": total_devices, "users_with_devices": users_with_devices}


async def get_hwid_top_users(db: AsyncSession, *, limit: int = 20) -> list[dict]:
    stmt = (
        select(HWIDUserDevice.user_id, User.username, func.count(HWIDUserDevice.id).label("devices_count"))
        .join(User, User.id == HWIDUserDevice.user_id, isouter=True)
        .group_by(HWIDUserDevice.user_id, User.username)
        .order_by(desc("devices_count"))
        .limit(max(1, limit))
    )
    rows = (await db.execute(stmt)).all()
    return [{"user_id": user_id, "username": username or "", "devices_count": int(devices_count or 0)} for user_id, username, devices_count in rows]


from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.db import AsyncSession, get_db
from app.db.models import Admin, ProxyHost
from app.models.admin import AdminDetails
from app.models.my_hosts import MyHostItem, MyHostsUpdate
from app.subscription.config_cache import clear_sub_config_cache

from .authentication import get_current

router = APIRouter(tags=["My Hosts"], prefix="/api/my-hosts")


def _item(host: ProxyHost, override: dict | None, order: int) -> MyHostItem:
    override = override or {}
    remark = override.get("remark")
    if not isinstance(remark, str) or not remark.strip():
        remark = None
    return MyHostItem(
        host_id=host.id,
        remark=remark or host.remark,
        original_remark=host.remark,
        inbound_tag=host.inbound_tag,
        priority=host.priority,
        order=order,
        is_disabled=bool(host.is_disabled or override.get("disabled")),
    )


async def _list_hosts(db: AsyncSession, admin: AdminDetails) -> list[MyHostItem]:
    hosts = (
        await db.execute(select(ProxyHost).order_by(ProxyHost.priority.asc(), ProxyHost.id.asc()))
    ).scalars().all()
    db_admin = await db.get(Admin, admin.id)
    overrides = (db_admin.my_hosts if db_admin is not None else None) or {}
    items = []
    for host in hosts:
        override = overrides.get(str(host.id), {})
        override_order = override.get("order")
        order = override_order if isinstance(override_order, int) else host.priority
        items.append(_item(host, override, order))
    items.sort(key=lambda item: (item.order, item.priority, item.host_id))
    return items


@router.get("", response_model=list[MyHostItem])
async def get_my_hosts(db: AsyncSession = Depends(get_db), admin: AdminDetails = Depends(get_current)):
    """List hosts with this admin's names, order and enabled state."""
    return await _list_hosts(db, admin)


@router.put("", response_model=list[MyHostItem])
async def update_my_hosts(
    body: MyHostsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(get_current),
):
    """Save the full host list in display order. Only affects this admin's users."""
    ids = [item.host_id for item in body.hosts]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Duplicate host ids")
    if ids:
        existing = set((await db.execute(select(ProxyHost.id).where(ProxyHost.id.in_(ids)))).scalars().all())
        missing = [host_id for host_id in ids if host_id not in existing]
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown host ids: {missing}")

    db_admin = await db.get(Admin, admin.id)
    if db_admin is None:
        raise HTTPException(status_code=404, detail="Admin not found")
    overrides: dict[str, dict] = {}
    for order, item in enumerate(body.hosts):
        remark = (item.remark or "").strip()
        overrides[str(item.host_id)] = {
            "remark": remark or None,
            "order": order,
            "disabled": item.is_disabled,
        }
    db_admin.my_hosts = overrides or None
    await db.commit()
    admin.my_hosts = db_admin.my_hosts
    clear_sub_config_cache()
    return await _list_hosts(db, admin)


@router.post("/reset", response_model=list[MyHostItem])
async def reset_my_hosts(
    order_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(get_current),
):
    """Reset names/visibility, or only the custom order."""
    db_admin = await db.get(Admin, admin.id)
    if db_admin is None:
        raise HTTPException(status_code=404, detail="Admin not found")
    if order_only and db_admin.my_hosts:
        cleaned = {}
        for host_id, override in db_admin.my_hosts.items():
            next_override = dict(override)
            next_override.pop("order", None)
            if next_override.get("remark") or next_override.get("disabled"):
                cleaned[host_id] = next_override
        db_admin.my_hosts = cleaned or None
    else:
        db_admin.my_hosts = None
    await db.commit()
    admin.my_hosts = db_admin.my_hosts
    clear_sub_config_cache()
    return await _list_hosts(db, admin)

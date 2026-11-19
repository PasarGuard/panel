from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base, ProxyHost
from app.models.host import HostPriorityUpdate
from app.operation import OperatorType
from app.operation.host import HostOperation


@pytest.mark.asyncio
async def test_reordering_preserves_stored_fragment_settings(monkeypatch):
    from app.operation import host as module

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    fragment = {
        "xray": {"packets": "tlshello", "length": "10-20", "interval": "5-10"},
        "sing_box": {"fragment": True, "record_fragment": True},
    }
    original = deepcopy(fragment)
    monkeypatch.setattr(module.host_manager, "add_hosts", AsyncMock())
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            hosts = [
                ProxyHost(
                    remark=name,
                    priority=index,
                    port=443,
                    path=None,
                    allowinsecure=None,
                    fragment_settings=deepcopy(fragment),
                    alpn=[],
                    status=[],
                )
                for index, name in enumerate(("first", "second"))
            ]
            db.add_all(hosts)
            await db.commit()
            await HostOperation(OperatorType.API).update_priorities(
                db,
                [HostPriorityUpdate(id=host.id, priority=1 - index) for index, host in enumerate(hosts)],
                SimpleNamespace(username="test"),
            )
            db.expire_all()
            stored = (await db.execute(select(ProxyHost).order_by(ProxyHost.id))).scalars().all()
            assert [host.priority for host in stored] == [1, 0]
            assert [host.fragment_settings for host in stored] == [original, original]
    finally:
        await engine.dispose()

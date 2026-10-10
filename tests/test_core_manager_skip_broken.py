from types import SimpleNamespace

import pytest

from app.core.manager import CoreManager
from app.db.models import CoreType
from app.utils.crypto import generate_wireguard_keypair


@pytest.mark.asyncio
async def test_initialize_skips_broken_cores(monkeypatch):
    """A bad xray/wg config must not abort startup — only that core is skipped."""
    manager = CoreManager()
    manager._nats_enabled = False

    private_key, _ = generate_wireguard_keypair()
    good = SimpleNamespace(
        id=1,
        name="ok",
        type=CoreType.wg,
        config={
            "interface_name": "wg0",
            "private_key": private_key,
            "listen_port": 51820,
            "address": ["10.0.0.1/24"],
        },
        exclude_inbound_tags=set(),
        fallbacks_inbound_tags=set(),
    )
    broken = SimpleNamespace(
        id=2,
        name="broken",
        type=CoreType.wg,
        config={"interface_name": "", "private_key": "nope", "listen_port": 0, "address": []},
        exclude_inbound_tags=set(),
        fallbacks_inbound_tags=set(),
    )

    async def fake_get_core_configs(db, query):
        return [good, broken], 2

    async def noop_persist():
        return None

    monkeypatch.setattr("app.core.manager.get_core_configs", fake_get_core_configs)
    monkeypatch.setattr(manager, "_persist_state", noop_persist)

    await manager.initialize(db=None)

    cores = await manager.get_cores()
    assert set(cores) == {1}
    assert 2 not in cores

import asyncio

import pytest

from app.core.hosts import HostManager
from app.models.subscription import SubscriptionInboundData
from app.nats.router import router

HOST_ID = 987654


def _entry(address: str) -> SubscriptionInboundData:
    return SubscriptionInboundData.model_construct(remark="echo", inbound_tag="echo", address=[address])


@pytest.fixture
def published(monkeypatch):
    messages: list[dict] = []

    async def capture(topic, data):
        messages.append(data)

    monkeypatch.setattr(router, "publish", capture)
    return messages


def _cached_address(manager: HostManager):
    cached = manager._hosts.get(HOST_ID)
    return None if cached is None else cached.address


def test_own_echoed_stale_add_does_not_overwrite_newer_local_edit(published):
    async def scenario():
        manager = HostManager()
        await manager._publish({"action": "add", "host": {"id": HOST_ID, "data": _entry("stale.example")}})
        await manager._add_prepared_hosts_local([(HOST_ID, _entry("newer.example"))], manager._next_stamp())
        for message in published:
            await manager._handle_host_message(message)
        return _cached_address(manager)

    assert asyncio.run(scenario()) == ["newer.example"]


def test_own_echoed_stale_remove_does_not_drop_newer_local_edit(published):
    async def scenario():
        manager = HostManager()
        await manager._publish({"action": "remove", "host_id": HOST_ID})
        await manager._add_prepared_hosts_local([(HOST_ID, _entry("newer.example"))], manager._next_stamp())
        for message in published:
            await manager._handle_host_message(message)
        return _cached_address(manager)

    assert asyncio.run(scenario()) == ["newer.example"]


def test_message_from_another_worker_is_still_applied(published):
    async def scenario():
        sender = HostManager()
        receiver = HostManager()
        await sender._publish({"action": "add", "host": {"id": HOST_ID, "data": _entry("remote.example")}})
        for message in published:
            await receiver._handle_host_message(message)
        added = _cached_address(receiver)
        published.clear()
        await sender._publish({"action": "remove", "host_id": HOST_ID})
        for message in published:
            await receiver._handle_host_message(message)
        return added, _cached_address(receiver)

    assert asyncio.run(scenario()) == (["remote.example"], None)


def test_remove_from_another_worker_does_not_beat_newer_local_refresh(published):
    async def scenario():
        sender = HostManager()
        receiver = HostManager()
        refresh_stamp = receiver._next_stamp()
        await sender._publish({"action": "remove", "host_id": HOST_ID})
        for message in published:
            await receiver._handle_host_message(message)
        await receiver._add_prepared_hosts_local([(HOST_ID, _entry("refreshed.example"))], refresh_stamp)
        return _cached_address(receiver)

    assert asyncio.run(scenario()) == ["refreshed.example"]


def test_local_remove_still_beats_older_local_refresh(published):
    async def scenario():
        manager = HostManager()
        refresh_stamp = manager._next_stamp()
        await manager._remove_host_local(HOST_ID)
        await manager._add_prepared_hosts_local([(HOST_ID, _entry("stale.example"))], refresh_stamp)
        return _cached_address(manager)

    assert asyncio.run(scenario()) is None


def test_each_setup_takes_a_fresh_origin(published, monkeypatch):
    async def scenario():
        manager = HostManager()
        inherited = manager._origin

        async def no_cache():
            return True

        monkeypatch.setattr(manager, "_load_state_from_cache", no_cache)
        monkeypatch.setattr(router, "register_handler", lambda topic, handler: None)
        await manager.setup(None)
        return inherited, manager._origin

    inherited, current = asyncio.run(scenario())
    assert current != inherited


def test_older_local_refresh_still_applies_after_stale_add_from_another_worker(published):
    async def scenario():
        sender = HostManager()
        receiver = HostManager()
        older_stamp = receiver._next_stamp()
        newer_stamp = receiver._next_stamp()
        await receiver._add_prepared_hosts_local([(HOST_ID, _entry("fresh-newer.example"))], newer_stamp)
        await sender._publish({"action": "add", "host": {"id": HOST_ID, "data": _entry("stale-remote.example")}})
        for message in published:
            await receiver._handle_host_message(message)
        await receiver._add_prepared_hosts_local([(HOST_ID, _entry("fresh-older.example"))], older_stamp)
        return _cached_address(receiver)

    assert asyncio.run(scenario()) == ["fresh-older.example"]


def test_older_local_refresh_still_applies_after_stale_remove_from_another_worker(published):
    async def scenario():
        sender = HostManager()
        receiver = HostManager()
        older_stamp = receiver._next_stamp()
        newer_stamp = receiver._next_stamp()
        await receiver._add_prepared_hosts_local([(HOST_ID, _entry("fresh-newer.example"))], newer_stamp)
        await sender._publish({"action": "remove", "host_id": HOST_ID})
        for message in published:
            await receiver._handle_host_message(message)
        await receiver._add_prepared_hosts_local([(HOST_ID, _entry("fresh-older.example"))], older_stamp)
        return _cached_address(receiver)

    assert asyncio.run(scenario()) == ["fresh-older.example"]

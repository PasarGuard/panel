"""worker_sync messages sent while NATS is down are lost: a reconnect must rebuild the state from the database."""

import asyncio
import logging

import pytest

from app.nats.message import MessageTopic, NatsMessage
from app.nats.router import NatsMessageRouter


def _router(monkeypatch: pytest.MonkeyPatch) -> NatsMessageRouter:
    router = NatsMessageRouter()
    monkeypatch.setattr(router, "RESYNC_DELAY", 0.05)
    monkeypatch.setattr(router, "RESYNC_JITTER", 0)
    monkeypatch.setattr(router, "RESYNC_RETRY_DELAY", 0.05)
    return router


async def _settle(router: NatsMessageRouter):
    while router._resync_task and not router._resync_task.done():
        await asyncio.wait_for(asyncio.shield(router._resync_task), timeout=5)


async def test_reconnect_reloads_every_registered_topic_cores_first(monkeypatch):
    router = _router(monkeypatch)
    calls = []
    for topic in (MessageTopic.NODE, MessageTopic.SETTING, MessageTopic.HOST, MessageTopic.CORE):

        async def _resync(topic=topic):
            calls.append(topic)

        router.register_resync_handler(topic, _resync)

    await router._on_reconnected()
    await _settle(router)

    # Hosts are prepared from the core inbounds, so cores must be reloaded first
    assert calls == [MessageTopic.CORE, MessageTopic.HOST, MessageTopic.SETTING, MessageTopic.NODE]


async def test_reconnect_burst_runs_one_resync(monkeypatch):
    router = _router(monkeypatch)
    calls = []

    async def _resync():
        calls.append(1)

    router.register_resync_handler(MessageTopic.HOST, _resync)

    for _ in range(5):
        await router._on_reconnected()
    await _settle(router)

    assert calls == [1]


async def test_reconnect_during_resync_runs_it_once_more(monkeypatch):
    router = _router(monkeypatch)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def _resync():
        calls.append(1)
        started.set()
        await release.wait()

    router.register_resync_handler(MessageTopic.HOST, _resync)

    await router._on_reconnected()
    await asyncio.wait_for(started.wait(), timeout=5)
    # Messages could have been lost again after the database was read
    for _ in range(3):
        await router._on_reconnected()
    release.set()
    await _settle(router)

    assert calls == [1, 1]


async def test_failed_resync_is_retried(monkeypatch):
    router = _router(monkeypatch)
    calls = []

    async def _resync():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database is down")

    router.register_resync_handler(MessageTopic.HOST, _resync)

    await router._on_reconnected()
    await _settle(router)

    assert calls == [1, 1]


async def test_only_failed_topics_are_retried_without_repeating_the_traceback(monkeypatch, caplog):
    router = _router(monkeypatch)
    calls = []

    def _handler(topic, failures):
        async def _resync():
            calls.append(topic)
            if calls.count(topic) <= failures:
                raise RuntimeError(f"{topic.value} is down")

        return _resync

    router.register_resync_handler(MessageTopic.SETTING, _handler(MessageTopic.SETTING, 0))
    router.register_resync_handler(MessageTopic.NODE, _handler(MessageTopic.NODE, 3))

    with caplog.at_level(logging.WARNING, logger="nats-router"):
        await router._on_reconnected()
        await _settle(router)

    assert calls == [MessageTopic.SETTING, *[MessageTopic.NODE] * 4]
    node_errors = [r for r in caplog.records if "node" in r.getMessage()]
    # The first failure carries the traceback, the repeats are one line each
    assert [bool(r.exc_info) for r in node_errors] == [True, False, False]


async def test_hosts_are_reloaded_again_when_cores_failed(monkeypatch):
    router = _router(monkeypatch)
    calls = []

    async def _cores():
        calls.append(MessageTopic.CORE)
        if calls.count(MessageTopic.CORE) == 1:
            raise RuntimeError("database is down")

    async def _hosts():
        calls.append(MessageTopic.HOST)

    router.register_resync_handler(MessageTopic.CORE, _cores)
    router.register_resync_handler(MessageTopic.HOST, _hosts)

    await router._on_reconnected()
    await _settle(router)

    # Hosts are prepared from core inbounds, so they follow a late core reload
    assert calls == [MessageTopic.CORE, MessageTopic.HOST, MessageTopic.CORE, MessageTopic.HOST]


class _FakeMsg:
    def __init__(self, topic: MessageTopic, data: dict):
        self.data = NatsMessage(topic=topic, data=data).model_dump_json().encode()


class _FakeSub:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()

    @property
    async def messages(self):
        while True:
            yield await self.queue.get()


class _FakeNC:
    def __init__(self):
        self.sub = _FakeSub()

    async def subscribe(self, subject):
        return self.sub

    async def close(self):
        pass


async def test_message_received_during_resync_is_applied_after_it(monkeypatch):
    router = _router(monkeypatch)
    nc = _FakeNC()
    router._nc = nc
    state = {"remark": "old"}
    resync_reading = asyncio.Event()
    release = asyncio.Event()
    handled = asyncio.Event()

    async def _resync():
        snapshot = "db-before-change"
        resync_reading.set()
        await release.wait()
        state["remark"] = snapshot

    async def _handle(data):
        state["remark"] = data["remark"]
        handled.set()

    router.register_handler(MessageTopic.HOST, _handle)
    router.register_resync_handler(MessageTopic.HOST, _resync)
    listener = asyncio.create_task(router._listen())
    try:
        await router._on_reconnected()
        await asyncio.wait_for(resync_reading.wait(), timeout=5)
        await nc.sub.queue.put(_FakeMsg(MessageTopic.HOST, {"remark": "newer"}))
        await asyncio.sleep(0.05)
        assert not handled.is_set()
        release.set()
        await asyncio.wait_for(handled.wait(), timeout=5)
        await _settle(router)
    finally:
        listener.cancel()
        await asyncio.gather(listener, return_exceptions=True)

    assert state["remark"] == "newer"


async def test_router_without_nats_never_connects_or_resyncs(monkeypatch):
    router = _router(monkeypatch)
    monkeypatch.setattr("app.nats.router.nats_settings.enabled", False)

    async def _no_client(**kwargs):
        raise AssertionError("must not connect without NATS")

    monkeypatch.setattr("app.nats.router.create_nats_client", _no_client)

    await router.start()
    await router.publish(MessageTopic.HOST, {"action": "add"})

    assert router._listener_task is None
    assert router._resync_task is None


@pytest.mark.parametrize(
    ("resynced", "message_topic", "waits"),
    [
        (MessageTopic.NODE, MessageTopic.HOST, False),
        (MessageTopic.NODE, MessageTopic.NODE, True),
        (MessageTopic.HOST, MessageTopic.CORE, True),
    ],
)
async def test_resync_holds_only_messages_of_the_same_state(monkeypatch, resynced, message_topic, waits):
    router = _router(monkeypatch)
    nc = _FakeNC()
    router._nc = nc
    resyncing = asyncio.Event()
    release = asyncio.Event()
    handled = asyncio.Event()

    async def _resync():
        resyncing.set()
        await release.wait()

    async def _handle(data):
        handled.set()

    router.register_handler(message_topic, _handle)
    router.register_resync_handler(resynced, _resync)
    listener = asyncio.create_task(router._listen())
    try:
        await router._on_reconnected()
        await asyncio.wait_for(resyncing.wait(), timeout=5)
        await nc.sub.queue.put(_FakeMsg(message_topic, {}))
        await asyncio.sleep(0.1)
        # Attaching nodes can take long; host, core and setting changes must not queue up behind it
        assert handled.is_set() is not waits
        release.set()
        await asyncio.wait_for(handled.wait(), timeout=5)
        await _settle(router)
    finally:
        listener.cancel()
        await asyncio.gather(listener, return_exceptions=True)

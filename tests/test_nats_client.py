"""NATS clients reconnect without a limit, but only after the first connect succeeded."""

import asyncio
import logging

import nats
import pytest
from nats import errors as nats_errors

from app.nats import client as nats_client


@pytest.fixture
def nats_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(nats_client, "is_nats_enabled", lambda: True)
    monkeypatch.setattr(nats_client, "get_nats_config", lambda: {"url": "nats://127.0.0.1:1"})


@pytest.fixture
def fake_connect(monkeypatch: pytest.MonkeyPatch, nats_enabled):
    captured = {}

    async def _connect(self, servers, **options):
        captured.update(options)
        self.options = {"max_reconnect_attempts": options.get("max_reconnect_attempts", 60)}
        self._status = nats.NATS.CONNECTED

    monkeypatch.setattr(nats.NATS, "connect", _connect)
    return captured


async def test_first_connect_to_unreachable_nats_fails_in_finite_time(monkeypatch, nats_enabled):
    connect = nats.NATS.connect

    async def _small_budget(self, servers, **options):
        # The real client against a closed port; only the default budget is shrunk to keep the test short
        options.setdefault("max_reconnect_attempts", 2)
        options.setdefault("reconnect_time_wait", 0)
        options.setdefault("connect_timeout", 0.5)
        return await connect(self, servers, **options)

    monkeypatch.setattr(nats.NATS, "connect", _small_budget)

    # An unlimited budget here made the startup hang forever while NATS was down
    with pytest.raises(nats_errors.NoServersError):
        await asyncio.wait_for(nats_client.create_nats_client(), timeout=30)


async def test_reconnect_budget_is_unlimited_once_connected(fake_connect):
    reconnects = []

    async def _on_reconnect():
        reconnects.append(1)

    nc = await nats_client.create_nats_client(reconnected_cb=_on_reconnect)

    assert "max_reconnect_attempts" not in fake_connect
    # The default budget of 60 attempts closed the client for good after ~2 minutes of outage
    assert nc.options["max_reconnect_attempts"] == -1
    await fake_connect["reconnected_cb"]()
    assert reconnects == [1]


def _warnings(caplog):
    return [r for r in caplog.records if r.name.endswith("nats-client") and r.levelno >= logging.WARNING]


async def test_failed_reconnect_attempts_are_logged_at_debug(fake_connect, caplog):
    nc = await nats_client.create_nats_client()
    nc._status = nats.NATS.RECONNECTING

    with caplog.at_level(logging.DEBUG):
        await fake_connect["error_cb"](ConnectionRefusedError("connect failed"))
        await fake_connect["error_cb"](TimeoutError())
    assert not _warnings(caplog)
    assert not [r for r in caplog.records if r.exc_info]


async def test_refused_login_is_a_warning_even_while_reconnecting(fake_connect, caplog):
    nc = await nats_client.create_nats_client()

    for status in (nats.NATS.RECONNECTING, nats.NATS.CONNECTING, nats.NATS.CONNECTED):
        nc._status = status
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            await fake_connect["error_cb"](nats_errors.AuthorizationError())
        assert len(_warnings(caplog)) == 1, status


async def test_network_errors_of_the_first_connect_are_warnings(monkeypatch, nats_enabled, caplog):
    async def _connect(self, servers, **options):
        self._status = nats.NATS.CONNECTING
        with caplog.at_level(logging.DEBUG):
            await options["error_cb"](ConnectionRefusedError("connect failed"))
        raise nats_errors.NoServersError

    monkeypatch.setattr(nats.NATS, "connect", _connect)

    with pytest.raises(nats_errors.NoServersError):
        await nats_client.create_nats_client()
    assert len(_warnings(caplog)) == 1


async def test_errors_on_a_live_connection_are_warnings(fake_connect, caplog):
    await nats_client.create_nats_client()

    with caplog.at_level(logging.DEBUG):
        await fake_connect["error_cb"](nats_errors.SlowConsumerError(subject="s", reply="", sid=1, sub=None))
    assert len(_warnings(caplog)) == 1

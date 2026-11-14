import asyncio
from typing import ClassVar

import pytest

from app.subscription import config_cache
from app.subscription.config_cache import (
    clear_sub_config_cache,
    get_or_create_sub_config,
    get_sub_config,
    make_sub_config_key,
)


class User:
    id = 42
    expire = None
    status = "active"
    data_limit = None
    inbounds: ClassVar[list[str]] = ["wg0"]

    class Proxy:
        class WireGuard:
            private_key = "private-a"
            peer_ips: ClassVar[list[str]] = ["10.0.0.2/32"]

            def model_dump_json(self):
                return f"{self.private_key}:{self.peer_ips}"

        wireguard = WireGuard()

        def model_dump_json(self):
            return self.wireguard.model_dump_json()

    proxy_settings = Proxy()


@pytest.fixture(autouse=True)
def clean_cache():
    clear_sub_config_cache()
    yield
    clear_sub_config_cache()


def test_wireguard_cache_key_changes_when_peer_state_changes():
    user = User()
    first = make_sub_config_key(user, "wireguard", False, False)
    user.proxy_settings.wireguard.peer_ips = ["10.0.0.3/32"]
    second = make_sub_config_key(user, "wireguard", False, False)
    assert first != second


@pytest.mark.asyncio
async def test_concurrent_renders_are_single_flight():
    calls = 0

    async def render():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return b"config"

    key = make_sub_config_key(User(), "wireguard", False, False)
    results = await asyncio.gather(*(get_or_create_sub_config(key, render) for _ in range(12)))

    assert calls == 1
    assert results == [b"config"] * 12
    assert get_sub_config(key) == b"config"


@pytest.mark.parametrize("config_format", ["wireguard", "clash_meta", "links"])
def test_cache_generation_invalidation_changes_keys(config_format: str):
    user = User()
    first = make_sub_config_key(user, config_format, False, False)
    clear_sub_config_cache()
    second = make_sub_config_key(user, config_format, False, False)
    assert first != second


@pytest.mark.parametrize("config_format", ["clash_meta", "links"])
def test_proxy_settings_changes_invalidate_non_wireguard_keys(config_format: str):
    user = User()
    user.proxy_settings = User.Proxy()
    user.proxy_settings.wireguard = User.Proxy.WireGuard()
    first = make_sub_config_key(user, config_format, False, False)
    user.proxy_settings.wireguard.private_key = "private-b"
    second = make_sub_config_key(user, config_format, False, False)
    assert first != second


def test_used_traffic_only_affects_wireguard_key():
    user = User()
    user.used_traffic = 100
    wg_first = make_sub_config_key(user, "wireguard", False, False)
    clash_first = make_sub_config_key(user, "clash_meta", False, False)

    user.used_traffic = 200
    assert make_sub_config_key(user, "wireguard", False, False) != wg_first
    assert make_sub_config_key(user, "clash_meta", False, False) == clash_first


@pytest.mark.asyncio
async def test_cancelled_waiters_do_not_leak_inflight_entry():
    started = asyncio.Event()
    finish = asyncio.Event()

    async def slow_render():
        started.set()
        await finish.wait()
        return "clash-payload"

    key = make_sub_config_key(User(), "clash_meta", False, False)
    waiter_one = asyncio.create_task(get_or_create_sub_config(key, slow_render))
    waiter_two = asyncio.create_task(get_or_create_sub_config(key, slow_render))

    await started.wait()
    assert key in config_cache._inflight

    waiter_one.cancel()
    waiter_two.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_one
    with pytest.raises(asyncio.CancelledError):
        await waiter_two

    finish.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert key not in config_cache._inflight
    assert get_sub_config(key) == "clash-payload"


@pytest.mark.asyncio
async def test_failed_render_is_not_cached_and_cleans_up_inflight_on_cancel():
    started = asyncio.Event()
    fail_now = asyncio.Event()

    async def failing_render():
        started.set()
        await fail_now.wait()
        raise ValueError("render failed")

    key = make_sub_config_key(User(), "links", False, False)
    waiter = asyncio.create_task(get_or_create_sub_config(key, failing_render))
    await started.wait()

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    fail_now.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert key not in config_cache._inflight
    assert get_sub_config(key) is None


@pytest.mark.asyncio
async def test_inflight_render_invalidated_by_clear_is_not_cached():
    started = asyncio.Event()
    finish = asyncio.Event()
    user = User()

    async def slow_render():
        started.set()
        await finish.wait()
        return "stale-payload"

    old_key = make_sub_config_key(user, "clash_meta", False, False)
    waiter = asyncio.create_task(get_or_create_sub_config(old_key, slow_render))
    await started.wait()

    clear_sub_config_cache()
    new_key = make_sub_config_key(user, "clash_meta", False, False)
    assert new_key != old_key

    finish.set()
    assert await waiter == "stale-payload"
    assert old_key not in config_cache._inflight
    assert get_sub_config(old_key) is None
    assert get_sub_config(new_key) is None

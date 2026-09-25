import asyncio
from typing import ClassVar

import pytest

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


def test_cache_generation_invalidation_changes_keys():
    user = User()
    first = make_sub_config_key(user, "wireguard", False, False)
    clear_sub_config_cache()
    second = make_sub_config_key(user, "wireguard", False, False)
    assert first != second

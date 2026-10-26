"""Rendering runs in a pool of its own that refuses work beyond its backlog, and validation uses many hosts."""

import asyncio
import threading

import pytest

from app.models.client_template import ClientTemplateType
from app.operation.client_template import InvalidTemplateContent, check_template_content
from app.subscription.host_refs import sample_host_refs
from app.templates import pool
from app.templates.pool import RenderPool, TemplatesBusy, subscription_pool, validation_pool


@pytest.fixture
def one_worker_no_backlog():
    render_pool = RenderPool(workers=1, backlog=0)
    yield render_pool
    render_pool._executor.shutdown(wait=True)


async def wait_until(event: threading.Event):
    while not event.is_set():
        await asyncio.sleep(0.001)


@pytest.mark.asyncio
async def test_a_full_pool_refuses_new_work_until_a_render_finishes(one_worker_no_backlog):
    started, release = threading.Event(), threading.Event()

    def block():
        started.set()
        release.wait(5)
        return "done"

    first = asyncio.create_task(one_worker_no_backlog.run(block))
    await wait_until(started)

    with pytest.raises(TemplatesBusy):
        await one_worker_no_backlog.run(lambda: "refused")

    release.set()
    assert await first == "done"
    assert await one_worker_no_backlog.run(lambda: "accepted") == "accepted"


@pytest.mark.asyncio
async def test_validating_in_a_loop_does_not_take_the_subscriptions_pool():
    release = threading.Event()
    running = [asyncio.create_task(validation_pool.run(release.wait, 5)) for _ in range(3)]
    await asyncio.sleep(0.05)

    with pytest.raises(TemplatesBusy):
        await validation_pool.run(lambda: "refused")
    assert await subscription_pool.run(lambda: "served") == "served"

    release.set()
    await asyncio.gather(*running)


@pytest.mark.asyncio
async def test_a_slow_render_times_out_but_keeps_its_slot_until_it_is_done(one_worker_no_backlog, monkeypatch):
    monkeypatch.setattr(pool.template_settings, "render_timeout", 0.05)
    started, release = threading.Event(), threading.Event()

    def block():
        started.set()
        release.wait(5)

    with pytest.raises(TemplatesBusy):
        await one_worker_no_backlog.run(block)
    assert started.is_set()

    # The thread is still running, so the pool does not pretend to have room
    with pytest.raises(TemplatesBusy):
        await one_worker_no_backlog.run(lambda: None)

    release.set()
    for _ in range(200):
        try:
            assert await one_worker_no_backlog.run(lambda: "free again") == "free again"
            break
        except TemplatesBusy:
            await asyncio.sleep(0.01)
    else:
        pytest.fail("the slot was never given back")


@pytest.mark.asyncio
async def test_errors_of_a_render_reach_the_caller(one_worker_no_backlog):
    def fail():
        raise ValueError("bad template")

    with pytest.raises(ValueError, match="bad template"):
        await one_worker_no_backlog.run(fail)
    assert await one_worker_no_backlog.run(lambda: 1) == 1


def test_sample_hosts_cover_every_prefix_and_end_with_one_without_access():
    hosts = sample_host_refs(["de", "nl"], 10)

    assert len(hosts) == 10
    assert [h.tag_prefix for h in hosts[:3]] == ["", "de", "nl"]
    assert [h.tag_prefix for h in hosts[3:6]] == ["", "de", "nl"]
    assert [h.available for h in hosts] == [True] * 9 + [False]
    assert len({h.tag for h in hosts}) == 10
    assert len(sample_host_refs([], 0)) == 2


QUADRATIC = (
    '{"inbounds": [{"tag": "in"}], "outbounds": [{"tag": "out"}]'
    "{% for a in hosts %}{% for b in hosts %}{% endfor %}{% endfor %}}"
)


def test_a_template_too_heavy_for_the_real_number_of_hosts_is_refused():
    check_template_content(ClientTemplateType.xray_subscription, QUADRATIC, use_jinja=True)

    with pytest.raises(InvalidTemplateContent, match="800 sample hosts"):
        check_template_content(ClientTemplateType.xray_subscription, QUADRATIC, host_count=800, use_jinja=True)

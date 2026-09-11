"""NATS user synchronization integration tests. Set NATS_SERVER_BINARY or install nats-server."""

import asyncio
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import nats
import pytest
import pytest_asyncio
from nats.js.errors import KeyNotFoundError
from PasarGuardNodeBridge.common.service_pb2 import User

from app.nats.kv_cleanup import compact_deleted_keys
from app.node.nats_memory import NatsUserSyncStore


@pytest_asyncio.fixture(loop_scope="function")
async def jetstream(tmp_path):
    binary = os.environ.get("NATS_SERVER_BINARY") or shutil.which("nats-server")
    if not binary:
        pytest.skip("Set NATS_SERVER_BINARY to run JetStream integration tests")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = await asyncio.to_thread(
        subprocess.Popen,
        [binary, "-js", "-a", "127.0.0.1", "-p", str(port), "-sd", str(tmp_path / "nats")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    nc = None
    try:
        async with asyncio.timeout(10):
            while True:
                try:
                    _reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError("Test NATS server exited during startup")
                    await asyncio.sleep(0.02)
        url = f"nats://127.0.0.1:{port}"
        nc = await nats.connect(url)
        js = nc.jetstream()
        bucket = "sync_" + uuid4().hex
        kv = await js.create_key_value(bucket=bucket)

        async def restart():
            nonlocal process
            process.terminate()
            await asyncio.to_thread(process.wait, timeout=10)
            process = await asyncio.to_thread(
                subprocess.Popen,
                process.args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            async with asyncio.timeout(10):
                while not nc.is_connected or nc.stats["reconnects"] == 0:
                    await asyncio.sleep(0.02)

        yield SimpleNamespace(nc=nc, js=js, kv=kv, bucket=bucket, process=process, url=url, restart=restart)
    finally:
        if nc is not None:
            await nc.close()
        process.terminate()
        await asyncio.to_thread(process.wait, timeout=10)


async def wait_for_keys(store, prefix, count, timeout=10):
    async with asyncio.timeout(timeout):
        while len(await store._key_index.keys(prefix)) != count:
            await asyncio.sleep(0.005)


async def test_idle_polls_do_not_create_consumers_or_send_requests(jetstream):
    stores = [NatsUserSyncStore(jetstream.kv) for _ in range(4)]
    try:
        # Seed deletion markers for completed claims.
        for number in range(300):
            await jetstream.kv.put(f"c.{number % 8}.{number}", b"{}")
            await jetstream.kv.delete(f"c.{number % 8}.{number}")
        for store in stores:
            assert await store.claim_users("0", "warmup", 10, 30) == []
        before = await jetstream.js.stream_info(f"KV_{jetstream.bucket}")
        sent = jetstream.nc.stats["out_msgs"]
        for _ in range(20):
            results = await asyncio.gather(
                *(
                    store.claim_users(str(node), str(worker), 10, 30)
                    for worker, store in enumerate(stores)
                    for node in range(8)
                )
            )
            assert all(result == [] for result in results)
        assert jetstream.nc.stats["out_msgs"] == sent
        after = await jetstream.js.stream_info(f"KV_{jetstream.bucket}")
        assert before.state.consumer_count == after.state.consumer_count == 4
        assert all(store._key_index._keys == {} for store in stores)
    finally:
        await asyncio.gather(*(store.close() for store in stores))


async def test_concurrent_workers_claim_each_update_once(jetstream):
    stores = [NatsUserSyncStore(jetstream.kv) for _ in range(4)]
    users = [User(email=f"user{i}", inbounds=["in"]) for i in range(80)]
    try:
        await stores[0].enqueue_users("1", users)
        await asyncio.gather(*(wait_for_keys(store, "p.1.", 80) for store in stores))
        batches = await asyncio.gather(
            *(store.claim_users("1", str(worker), 80, 30) for worker, store in enumerate(stores))
        )
        emails = [item.user.email for batch in batches for item in batch]
        assert len(emails) == len(set(emails)) == 80
        await asyncio.gather(
            *(store.ack_users("1", [item.token for item in batch]) for store, batch in zip(stores, batches))
        )
        for store in stores:
            await wait_for_keys(store, "p.1.", 0)
            await wait_for_keys(store, "c.1.", 0)
            assert await store.claim_users("1", "idle", 80, 30) == []
    finally:
        await asyncio.gather(*(store.close() for store in stores))


async def test_live_enqueue_and_expired_claim_recovery(jetstream):
    first = NatsUserSyncStore(jetstream.kv)
    second = NatsUserSyncStore(jetstream.kv)
    try:
        assert await second.claim_users("1", "other", 10, 30) == []
        await first.enqueue_users("1", [User(email="recover", inbounds=["in"])])
        await wait_for_keys(second, "p.1.", 1)
        claimed = await first.claim_users("1", "crashed", 10, 0)
        assert len(claimed) == 1
        await wait_for_keys(second, "p.1.", 0)
        await wait_for_keys(second, "c.1.", 1)
        recovered = await second.claim_users("1", "replacement", 10, 30)
        assert [item.user.email for item in recovered] == ["recover"]
    finally:
        await first.close()
        await second.close()


async def test_enqueue_is_claimable_even_when_watch_notifications_are_delayed(jetstream):
    gate = asyncio.Event()
    real_watch = jetstream.kv.watch

    class DelayedWatcher:
        def __init__(self, watcher):
            self.watcher = watcher

        def __aiter__(self):
            return self

        async def __anext__(self):
            update = await self.watcher.__anext__()
            if update is not None:
                await gate.wait()
            return update

        async def stop(self):
            await self.watcher.stop()

    async def delayed_watch(*args, **kwargs):
        return DelayedWatcher(await real_watch(*args, **kwargs))

    jetstream.kv.watch = delayed_watch
    store = NatsUserSyncStore(jetstream.kv)
    try:
        assert await store.claim_users("1", "local", 10, 30) == []
        await store.enqueue_users("1", [User(email="immediate")])
        claimed = await store.claim_users("1", "local", 10, 30)
        assert [item.user.email for item in claimed] == ["immediate"]
        await store.requeue_users("1", claimed)
        assert [item.user.email for item in await store.claim_users("1", "local", 10, 30)] == ["immediate"]
    finally:
        await store.close()


async def test_compaction_keeps_pending_and_concurrently_recreated_values(jetstream):
    kv = jetstream.kv
    await kv.put("p.1.live", b"pending")
    await kv.put("p.1.race", b"old")
    await kv.delete("p.1.race")
    await kv.put("c.1.completed", b"old claim")
    await kv.delete("c.1.completed")
    assert await compact_deleted_keys(jetstream.js, jetstream.bucket) == 0  # grace period
    original_purge = jetstream.js.purge_stream

    async def recreate_before_purge(stream, **kwargs):
        if kwargs["subject"].endswith("p.1.race"):
            await kv.put("p.1.race", b"new update")
        return await original_purge(stream, **kwargs)

    jetstream.js.purge_stream = recreate_before_purge
    assert await compact_deleted_keys(jetstream.js, jetstream.bucket, older_than=0) == 2
    assert (await kv.get("p.1.live")).value == b"pending"
    assert (await kv.get("p.1.race")).value == b"new update"
    with pytest.raises(KeyNotFoundError):
        await kv.get("c.1.completed")
    assert (await jetstream.js.stream_info(f"KV_{jetstream.bucket}")).state.messages == 2


async def test_watcher_resumes_after_network_disconnect(jetstream):
    nc = await nats.connect(jetstream.url, reconnect_time_wait=0.05)
    store = NatsUserSyncStore(await nc.jetstream().key_value(jetstream.bucket))
    try:
        assert await store.claim_users("1", "reader", 10, 30) == []
        # Drop only this client's TCP transport; the writer remains connected.
        nc._transport.close()
        await jetstream.kv.put("p.1.new", b'{"email":"new","user":"CgNuZXc="}')
        async with asyncio.timeout(10):
            while nc.stats["reconnects"] == 0:
                await asyncio.sleep(0.02)
        await wait_for_keys(store, "p.1.", 1)
        assert [item.user.email for item in await store.claim_users("1", "reader", 10, 30)] == ["new"]
    finally:
        await store.close()
        with contextlib.suppress(Exception):
            await nc.close()


async def test_four_python_processes_deliver_every_update_once(jetstream):
    writer = NatsUserSyncStore(jetstream.kv)
    expected = {f"node{node}-user{user}" for node in range(4) for user in range(250)}
    for node in range(4):
        await writer.enqueue_users(str(node), [User(email=f"node{node}-user{user}") for user in range(250)])
    processes = []
    try:
        for worker in range(4):
            processes.append(
                await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(Path(__file__).with_name("nats_sync_process_worker.py")),
                    jetstream.url,
                    jetstream.bucket,
                    str(worker),
                    "4",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            )
        async with asyncio.timeout(75):
            results = await asyncio.gather(*(process.communicate() for process in processes))
        emails = []
        for process, (stdout, stderr) in zip(processes, results):
            assert process.returncode == 0, stderr.decode(errors="replace")
            emails.extend(json.loads(stdout))
        assert len(emails) == len(expected)
        assert set(emails) == expected
        assert await writer.claim_users("0", "verify", 50, 120) == []
        await compact_deleted_keys(jetstream.js, jetstream.bucket, older_than=0)
        assert (await jetstream.js.stream_info(f"KV_{jetstream.bucket}")).state.messages == 0
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
                await process.wait()
        await writer.close()


async def test_server_restart_preserves_pending_work_and_watch_updates(jetstream):
    store = NatsUserSyncStore(jetstream.kv)
    try:
        await store.enqueue_users("1", [User(email="before-restart")])
        await wait_for_keys(store, "p.1.", 1)
        await jetstream.restart()
        # A separate store writes after reconnect so the reader must receive a
        # watch notification, rather than using its own immediate-write hint.
        writer = NatsUserSyncStore(jetstream.kv)
        try:
            await writer.enqueue_users("1", [User(email="after-restart")])
        finally:
            await writer.close()
        # nats-py checks heartbeat activity every 10 seconds and the first
        # check clears the initial active flag. Allow two activity checks.
        await wait_for_keys(store, "p.1.", 2, timeout=30)
        claimed = await store.claim_users("1", "restarted", 10, 30)
        assert {item.user.email for item in claimed} == {"before-restart", "after-restart"}
        await store.ack_users("1", [item.token for item in claimed])
        await wait_for_keys(store, "c.1.", 0)
    finally:
        await store.close()


async def test_repeated_sync_compaction_and_idle_keep_resources_bounded(jetstream):
    store = NatsUserSyncStore(jetstream.kv)
    stream = f"KV_{jetstream.bucket}"
    try:
        for cycle in range(20):
            users = [User(email=f"cycle{cycle}-user{number}") for number in range(50)]
            await store.enqueue_users("1", users)
            claimed = await store.claim_users("1", "worker", 100, 30)
            assert {item.user.email for item in claimed} == {user.email for user in users}
            await store.ack_users("1", [item.token for item in claimed])
            await wait_for_keys(store, "p.1.", 0)
            await wait_for_keys(store, "c.1.", 0)
            assert store._key_index._keys == {}
            assert store._key_index._local_puts == {}
            await compact_deleted_keys(jetstream.js, jetstream.bucket, older_than=0)
            assert (await jetstream.js.stream_info(stream)).state.messages == 0

        sent = jetstream.nc.stats["out_msgs"]
        # Longer than the live watcher's inactive threshold. It must remain
        # live while unused, and short-lived compaction consumers must expire.
        await asyncio.sleep(35)
        assert await store.claim_users("1", "idle", 100, 30) == []
        assert jetstream.nc.stats["out_msgs"] == sent
        assert (await jetstream.js.stream_info(stream)).state.consumer_count == 1
        await store.enqueue_users("1", [User(email="after-idle")])
        assert [item.user.email for item in await store.claim_users("1", "worker", 100, 30)] == ["after-idle"]
    finally:
        await store.close()


async def test_live_index_survives_consumer_recreation(jetstream):
    store = NatsUserSyncStore(jetstream.kv)
    try:
        assert await store.claim_users("1", "reader", 10, 30) == []
        consumers = await jetstream.js.consumers_info(f"KV_{jetstream.bucket}")
        assert len(consumers) == 1
        await jetstream.js.delete_consumer(f"KV_{jetstream.bucket}", consumers[0].name)
        writer = NatsUserSyncStore(jetstream.kv)
        try:
            await writer.enqueue_users("1", [User(email="after-consumer-loss")])
        finally:
            await writer.close()
        async with asyncio.timeout(30):
            while not await store._key_index.keys("p.1."):
                await asyncio.sleep(0.05)
        assert [item.user.email for item in await store.claim_users("1", "reader", 10, 30)] == ["after-consumer-loss"]
    finally:
        await store.close()

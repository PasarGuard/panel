"""Benchmark NATS queue discovery using bucket scans, prefix scans, and a live index.

Starts an isolated loopback NATS server for each mode.
Run with DEBUG=false and --nats-server /path/to/nats-server.
"""

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import nats
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nats.kv_cas import kv_list_keys
from app.node.nats_memory import NatsUserSyncStore


async def benchmark(args, mode):
    with tempfile.TemporaryDirectory(prefix="pasarguard-nats-bench-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = await asyncio.to_thread(
            subprocess.Popen,
            [args.nats_server, "-js", "-a", "127.0.0.1", "-p", str(port), "-sd", directory],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        stores = []
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
                            raise RuntimeError("NATS server exited during startup")
                        await asyncio.sleep(0.02)
            nc = await nats.connect(f"nats://127.0.0.1:{port}")
            js = nc.jetstream()
            kv = await js.create_key_value(bucket="queue")

            async def seed(number):
                key = f"c.{number % args.nodes}.{number}"
                await kv.put(key, b"{}")
                await kv.delete(key)

            for offset in range(0, args.tombstones, 32):
                await asyncio.gather(*(seed(i) for i in range(offset, min(offset + 32, args.tombstones))))
            if mode == "live_index":
                stores = [NatsUserSyncStore(kv) for _ in range(args.workers)]
                await asyncio.gather(*(store.claim_users("0", str(i), 10, 30) for i, store in enumerate(stores)))

            async def poll(worker, node):
                if mode == "live_index":
                    assert await stores[worker].claim_users(str(node), str(worker), 10, 30) == []
                    return
                for prefix in (f"c.{node}.", f"p.{node}."):
                    if mode == "bucket_scan":
                        try:
                            keys = await kv.keys()
                        except nats.js.errors.NoKeysError:
                            keys = []
                        assert not [key for key in keys if key.startswith(prefix)]
                    else:
                        assert await kv_list_keys(kv, prefix) == []

            server = psutil.Process(process.pid)
            before_cpu = server.cpu_times()
            client_cpu = time.process_time()
            before_stats = dict(nc.stats)
            start = time.perf_counter()
            for _ in range(args.rounds):
                await asyncio.gather(*(poll(w, n) for w in range(args.workers) for n in range(args.nodes)))
            elapsed = time.perf_counter() - start
            client_cpu = time.process_time() - client_cpu
            after_cpu = server.cpu_times()
            traffic = {key: nc.stats[key] - before_stats[key] for key in ("in_msgs", "out_msgs", "in_bytes")}
            info = await js.stream_info("KV_queue")
            return {
                "mode": mode,
                "empty_claim_calls": args.workers * args.nodes * args.rounds,
                "wall_seconds": round(elapsed, 4),
                "python_cpu_seconds": round(client_cpu, 4),
                "nats_cpu_seconds": round(after_cpu.user + after_cpu.system - before_cpu.user - before_cpu.system, 4),
                "nats_rss_mib": round(server.memory_info().rss / 1024**2, 2),
                "consumers": info.state.consumer_count,
                **traffic,
            }
        finally:
            await asyncio.gather(*(store.close() for store in stores))
            if nc is not None:
                await nc.close()
            process.terminate()
            await asyncio.to_thread(process.wait, timeout=10)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nats-server", default=os.environ.get("NATS_SERVER_BINARY") or shutil.which("nats-server"))
    parser.add_argument("--nodes", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--tombstones", type=int, default=2000)
    parser.add_argument("--mode", nargs="+", choices=("bucket_scan", "prefix_scan", "live_index"))
    args = parser.parse_args()
    if not args.nats_server:
        parser.error("Pass --nats-server or set NATS_SERVER_BINARY")
    print(json.dumps({"scenario": vars(args)}), flush=True)
    for mode in args.mode or ("bucket_scan", "prefix_scan", "live_index"):
        print(json.dumps(await benchmark(args, mode)), flush=True)


if __name__ == "__main__":
    asyncio.run(main())

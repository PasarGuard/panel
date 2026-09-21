"""Independent Python worker used by the real NATS integration tests."""

import asyncio
import json
import sys
from pathlib import Path

import nats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.node.nats_memory import NatsUserSyncStore


async def main():
    url, bucket, worker_id, node_count = sys.argv[1:]
    nc = await nats.connect(url)
    store = NatsUserSyncStore(await nc.jetstream().key_value(bucket))
    emails = []
    try:
        async with asyncio.timeout(60):
            # All inputs are seeded before process startup. An empty complete
            # pass means remaining work belongs to one of the other processes.
            while True:
                progress = False
                for node in range(int(node_count)):
                    claimed = await store.claim_users(str(node), worker_id, 50, 120)
                    emails.extend(item.user.email for item in claimed)
                    await store.ack_users(str(node), [item.token for item in claimed])
                    progress |= bool(claimed)
                if not progress:
                    break
        print(json.dumps(emails), flush=True)
    finally:
        await store.close()
        await nc.close()


if __name__ == "__main__":
    asyncio.run(main())

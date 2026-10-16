"""Durable receipt ledger and atomic accounting, independent of node RPCs."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import bindparam, delete, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import Admin, Node, System, UsageReceipt, UsageStream, User
from app.jobs._usage_queries import (
    build_node_usage_upsert,
    build_node_user_usage_upsert,
    build_online_at_updates,
    build_user_traffic_update,
)


def chunks(items, size=400):
    for index in range(0, len(items), size):
        yield items[index : index + size]


@dataclass(frozen=True)
class Receipt:
    kind: str
    node_id: int
    collection_epoch: str
    receipt_id: str
    payload: dict

    @classmethod
    def create(
        cls, kind, node_id, collection_epoch, stats, history, coefficient=1.0, *, receipt_id=None, collected_at=None
    ):
        # Node-generated IDs survive transport retries and leadership changes.
        if receipt_id is not None:
            receipt_id = str(UUID(receipt_id))
        return cls(
            kind,
            node_id,
            collection_epoch,
            receipt_id or str(uuid4()),
            {
                "version": 1,
                "collected_at": (collected_at or datetime.now(UTC)).isoformat(),
                "stats": stats,
                "history": history,
                "coefficient": coefficient,
            },
        )


class StaleUsageCollection(Exception):
    """Cleanup fenced this collection; recollect the node's durable pending receipt."""


class UsageStore:
    def __init__(self, transaction, dialect):
        self.transaction = transaction
        self.dialect = dialect
        self.table = UsageReceipt.__table__
        self.streams = UsageStream.__table__

    def _insert_once(self, table, **values):
        factory = {"mysql": mysql_insert, "postgresql": pg_insert, "sqlite": sqlite_insert}[self.dialect]
        stmt = factory(table).values(**values)
        if self.dialect == "mysql":
            return stmt.on_duplicate_key_update(node_id=table.c.node_id)
        return stmt.on_conflict_do_nothing(index_elements=[column.name for column in table.primary_key])

    def _stream_key(self, kind, node_id):
        return (self.streams.c.kind == kind) & (self.streams.c.node_id == node_id)

    async def _lock_stream(self, conn, kind, node_id):
        key = self._stream_key(kind, node_id)
        # UPDATE also serializes SQLite callers; FOR UPDATE alone does not.
        await conn.execute(update(self.streams).where(key).values(collection_epoch=self.streams.c.collection_epoch))
        return (await conn.execute(select(self.streams.c.collection_epoch).where(key))).scalar_one_or_none()

    def key(self, kind, node_id):
        return (self.table.c.kind == kind) & (self.table.c.node_id == node_id)

    async def pending_nodes(self, kind):
        async def read(conn):
            result = await conn.execute(
                select(self.table.c.node_id)
                .where(self.table.c.kind == kind, self.table.c.processed.is_(False))
                .distinct()
            )
            return list(result.scalars())

        return await self.transaction(read)

    async def prepare(self, kind, node_id):
        """Capture a durable fence BEFORE a node RPC can return an old receipt."""

        async def prepare(conn):
            epoch = (
                await conn.execute(select(self.streams.c.collection_epoch).where(self._stream_key(kind, node_id)))
            ).scalar_one_or_none()
            if epoch is None:
                await conn.execute(
                    self._insert_once(self.streams, node_id=node_id, kind=kind, collection_epoch=str(uuid4()))
                )
                epoch = (
                    await conn.execute(select(self.streams.c.collection_epoch).where(self._stream_key(kind, node_id)))
                ).scalar_one()
            return epoch

        return await self.transaction(prepare)

    async def stage(self, receipt):
        """Insert once without overwriting a pending payload or applied tombstone."""

        async def stage(conn):
            epoch = await self._lock_stream(conn, receipt.kind, receipt.node_id)
            if epoch is None or epoch != receipt.collection_epoch:
                raise StaleUsageCollection(f"Collection fenced for {receipt.kind}/{receipt.node_id}")
            stmt = self._insert_once(
                self.table,
                node_id=receipt.node_id,
                kind=receipt.kind,
                receipt_id=receipt.receipt_id,
                payload=receipt.payload,
                processed=False,
            )
            await conn.execute(stmt)

        await self.transaction(stage)

    async def acknowledge(self, receipt):
        """Record proof only AFTER a successful durable node ACK response."""

        async def acknowledge(conn):
            await conn.execute(
                update(self.table)
                .where(
                    self.key(receipt.kind, receipt.node_id),
                    self.table.c.receipt_id == receipt.receipt_id,
                    self.table.c.acknowledged_at.is_(None),
                )
                .values(acknowledged_at=datetime.now(UTC))
            )

        await self.transaction(acknowledge)

    async def cleanup(self, retention_days, batch_size, *, now=None):
        """Delete a bounded ACKed/applied batch and fence old collectors atomically.

        The node can replay an unACKed receipt forever. A confirmed ACK removes
        that replay source; rotating the stream fence rejects arbitrarily late
        in-flight replies and unstaged samples even after their IDs are deleted.
        Pending, unACKed and pre-migration receipts remain recoverable.
        """
        if retention_days < 1 or not 1 <= batch_size <= 10000:
            raise ValueError("Receipt cleanup requires positive retention and a bounded batch")
        cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
        eligible = (
            self.table.c.processed.is_(True)
            & (self.table.c.applied_at < cutoff)
            & (self.table.c.acknowledged_at < cutoff)
        )

        async def cleanup(conn):
            candidates = (
                await conn.execute(
                    select(self.table.c.node_id, self.table.c.kind, self.table.c.receipt_id)
                    .where(eligible)
                    .order_by(self.table.c.acknowledged_at)
                    .limit(batch_size)
                )
            ).all()
            streams = defaultdict(list)
            for node_id, kind, receipt_id in candidates:
                streams[(node_id, kind)].append(receipt_id)
            deleted = 0
            for (node_id, kind), ids in sorted(streams.items()):
                if await self._lock_stream(conn, kind, node_id) is None:
                    continue
                await conn.execute(
                    update(self.streams).where(self._stream_key(kind, node_id)).values(collection_epoch=str(uuid4()))
                )
                for batch in chunks(ids):
                    result = await conn.execute(
                        delete(self.table).where(self.key(kind, node_id), eligible, self.table.c.receipt_id.in_(batch))
                    )
                    deleted += result.rowcount
            return deleted

        return await self.transaction(cleanup)

    async def apply(self, kind, node_id):
        # Bound recovery work per tick; independent receipts never block staging
        # newer ones. The next tick resumes any remaining durable backlog.
        changed = False
        for _ in range(100):
            if not await self._apply_one(kind, node_id):
                break
            changed = True
        return changed

    async def _apply_one(self, kind, node_id):
        async def apply(conn):
            key = self.key(kind, node_id)
            receipt_id = (
                await conn.execute(
                    select(self.table.c.receipt_id)
                    .where(key, self.table.c.processed.is_(False))
                    .order_by(self.table.c.receipt_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if receipt_id is None:
                return False
            key = key & (self.table.c.receipt_id == receipt_id)
            # An UPDATE acquires a write lock on SQLite too, where FOR UPDATE
            # alone would allow two consumers to read the same pending payload.
            await conn.execute(update(self.table).where(key).values(receipt_id=self.table.c.receipt_id))
            row = (await conn.execute(select(self.table.c.payload).where(key))).first()
            if row is None or row.payload is None:
                return False
            payload = row.payload
            if payload.get("version") != 1:
                raise ValueError("Unsupported usage receipt version")
            collected_at = datetime.fromisoformat(payload["collected_at"])
            bucket = collected_at.replace(minute=collected_at.minute // 10 * 10, second=0, microsecond=0)
            # Lock the node before users. Deletion must not race history writes.
            node = (await conn.execute(select(Node.id).where(Node.id == node_id).with_for_update())).first()
            history_node_id = node_id if node else None
            if kind == "users":
                await self._users(conn, history_node_id, payload, collected_at, bucket)
            elif kind == "outbounds":
                await self._outbounds(conn, history_node_id, payload, bucket)
            else:
                raise ValueError("Unknown usage stream")
            # Retain the ID until confirmed ACK, retention and fence rotation.
            # This commit includes ALL accounting and history writes.
            await conn.execute(
                update(self.table).where(key).values(payload=None, processed=True, applied_at=datetime.now(UTC))
            )
            return True

        return await self.transaction(apply)

    async def _users(self, conn, node_id, payload, collected_at, bucket):
        values = defaultdict(int)
        for stat in payload["stats"]:
            if stat["value"] > 0:
                value = int(stat["value"] * payload.get("coefficient", 1.0))
                if value > 0:
                    values[int(stat["uid"])] += value
        uids = sorted(values)
        owners = {}
        for batch in chunks(uids):
            rows = await conn.execute(
                select(User.id, User.admin_id).where(User.id.in_(batch)).order_by(User.id).with_for_update()
            )
            owners.update(rows.all())
        user_params = [{"uid": uid, "value": values[uid]} for uid in uids if uid in owners]
        admins = defaultdict(int)
        for stat in user_params:
            if owners[stat["uid"]] is not None:
                admins[owners[stat["uid"]]] += stat["value"]
        # Keep set-based PostgreSQL writes and throttled timestamps inside the
        # receipt transaction, so retries cannot charge a partially applied batch.
        if user_params:
            stmt, parameters = build_user_traffic_update(self.dialect, user_params)
            if self.dialect == "postgresql":
                await conn.execute(stmt, parameters)
            else:
                for batch in chunks(parameters):
                    await conn.execute(stmt, batch)
            for stmt, parameters in build_online_at_updates(
                self.dialect, [stat["uid"] for stat in user_params], collected_at
            ):
                if parameters is None:
                    await conn.execute(stmt)
                else:
                    await conn.execute(stmt, parameters)
        if admins:
            table = Admin.__table__
            await conn.execute(
                update(table)
                .where(table.c.id == bindparam("aid"))
                .values(used_traffic=table.c.used_traffic + bindparam("value")),
                [{"aid": aid, "value": value} for aid, value in sorted(admins.items())],
            )
        if payload["history"]:
            params = [{**stat, "node_id": node_id, "created_at": bucket} for stat in user_params]
            batch_size = {"mysql": 1000, "sqlite": 400}.get(self.dialect, 5000)
            for batch in chunks(params, batch_size):
                for stmt, parameters in build_node_user_usage_upsert(self.dialect, batch):
                    await conn.execute(stmt, parameters)

    async def _outbounds(self, conn, node_id, payload, bucket):
        up = sum(max(0, int(stat.get("up", 0))) for stat in payload["stats"])
        down = sum(max(0, int(stat.get("down", 0))) for stat in payload["stats"])
        if not (up or down):
            return
        if node_id is not None:
            await conn.execute(
                update(Node.__table__)
                .where(Node.id == node_id)
                .values(uplink=Node.uplink + up, downlink=Node.downlink + down)
            )
        result = await conn.execute(
            update(System.__table__).values(uplink=System.uplink + up, downlink=System.downlink + down)
        )
        if result.rowcount != 1:
            raise RuntimeError("Usage accounting requires exactly one system row")
        if payload["history"]:
            for stmt, parameters in build_node_usage_upsert(
                self.dialect,
                {
                    "node_id": node_id,
                    "created_at": bucket,
                    "up": up,
                    "down": down,
                },
            ):
                await conn.execute(stmt, parameters)

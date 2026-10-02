"""Durable receipt ledger and atomic accounting, independent of node RPCs."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import bindparam, case, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import Admin, Node, System, UsageReceipt, User
from app.jobs._usage_queries import build_node_usage_upsert, build_node_user_usage_upsert


def chunks(items, size=400):
    for index in range(0, len(items), size):
        yield items[index : index + size]


@dataclass(frozen=True)
class Receipt:
    kind: str
    node_id: int
    previous_id: str
    receipt_id: str
    payload: dict

    @classmethod
    def create(cls, kind, node_id, previous_id, stats, history, coefficient=1.0, *, receipt_id=None, collected_at=None):
        # Node-generated IDs survive transport retries and leadership changes.
        if receipt_id is not None:
            receipt_id = str(UUID(receipt_id))
        return cls(
            kind,
            node_id,
            previous_id,
            receipt_id or str(uuid4()),
            {
                "version": 1,
                "collected_at": (collected_at or datetime.now(UTC)).isoformat(),
                "stats": stats,
                "history": history,
                "coefficient": coefficient,
            },
        )


class UsageStore:
    def __init__(self, transaction, dialect):
        self.transaction = transaction
        self.dialect = dialect
        self.table = UsageReceipt.__table__

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
        """Check storage before polling; every receipt now owns an independent row."""

        async def prepare(conn):
            await conn.execute(select(self.table.c.receipt_id).where(self.key(kind, node_id)).limit(1))
            return ""

        return await self.transaction(prepare)

    async def stage(self, receipt):
        """Insert once without overwriting a pending payload or applied tombstone."""

        async def stage(conn):
            factory = {"mysql": mysql_insert, "postgresql": pg_insert, "sqlite": sqlite_insert}[self.dialect]
            stmt = factory(self.table).values(
                node_id=receipt.node_id,
                kind=receipt.kind,
                receipt_id=receipt.receipt_id,
                payload=receipt.payload,
                processed=False,
            )
            if self.dialect == "mysql":
                stmt = stmt.on_duplicate_key_update(receipt_id=self.table.c.receipt_id)
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=["node_id", "kind", "receipt_id"])
            await conn.execute(stmt)

        await self.transaction(stage)

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
            # Keep the receipt ID as a tombstone, releasing only the large payload.
            # This commit includes ALL accounting and history writes.
            await conn.execute(update(self.table).where(key).values(payload=None, processed=True))
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
        # Core tables avoid ORM bulk-update semantics and identity-map overhead.
        users = User.__table__
        stmt = (
            update(users)
            .where(users.c.id == bindparam("uid"))
            .values(
                used_traffic=users.c.used_traffic + bindparam("value"),
                online_at=case((users.c.online_at > collected_at, users.c.online_at), else_=collected_at),
            )
        )
        for batch in chunks(user_params):
            await conn.execute(stmt, batch)
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

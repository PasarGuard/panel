from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Group, ProxyInbound, User, UserStatus, inbounds_groups_association, users_groups_association
from app.models.protocol import ProxyProtocol
from app.node.user import core_users
from app.operation import node as node_operation
from app.operation.node import NodeOperation
from tests.api import DATABASE_URL


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["mysql", "mariadb", "postgresql", "sqlite"])
@pytest.mark.parametrize("current_read", [False, True])
async def test_core_users_locking_is_scoped_to_authoritative_mysql_reads(backend, current_read):
    dialect = (
        mysql.dialect()
        if backend in ("mysql", "mariadb")
        else (postgresql.dialect() if backend == "postgresql" else sqlite.dialect())
    )
    if backend == "mariadb":
        dialect.name = "mariadb"
    result = MagicMock()
    result.all.return_value = []
    db = SimpleNamespace(bind=SimpleNamespace(dialect=dialect), execute=AsyncMock(return_value=result))
    assert await core_users(db, current_read=current_read) == []
    statement = db.execute.await_args.args[0]
    sql = str(statement.compile(dialect=dialect))
    assert ("FOR UPDATE" in sql) is (current_read and backend in ("mysql", "mariadb"))


@pytest.mark.asyncio
@pytest.mark.skipif(not DATABASE_URL.startswith(("mysql", "mariadb")), reason="requires MySQL/MariaDB REPEATABLE READ")
@pytest.mark.parametrize("change", ["disable", "credentials", "groups"])
async def test_mysql_authoritative_node_snapshot_uses_current_committed_values(monkeypatch, change):
    """Keep A's snapshot open across B's commit; only startup may bypass it."""
    engine = create_async_engine(DATABASE_URL, isolation_level="REPEATABLE READ")
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    old_id, new_id = str(uuid4()), str(uuid4())
    tags = [f"rr_old_{uuid4().hex[:12]}", f"rr_new_{uuid4().hex[:12]}"]
    protocols = frozenset({ProxyProtocol.vless})
    core_id = 424242
    core = SimpleNamespace(inbounds=tags, protocols=protocols)
    monkeypatch.setattr(
        node_operation, "core_manager", SimpleNamespace(get_cores=AsyncMock(return_value={core_id: core}))
    )
    # Keep external transport out of this database regression. Production SQL,
    # grouping, eligibility, and protobuf serialization all run unchanged.
    monkeypatch.setattr(node_operation, "node_manager", SimpleNamespace(uses_shared_revocation_store=True))
    user_id = None
    group_ids = []
    inbound_ids = []
    try:
        async with sessions() as seed:
            inbounds = [ProxyInbound(tag=tag) for tag in tags]
            groups = [Group(name=f"rr_group_{uuid4().hex[:12]}", inbounds=[inbound]) for inbound in inbounds]
            user = User(username=f"rr_user_{uuid4().hex[:16]}", proxy_settings={"vless": {"id": old_id}})
            seed.add_all([*groups, user])
            await seed.flush()
            user_id, sync_id = user.id, user.sync_id
            group_ids = [group.id for group in groups]
            inbound_ids = [inbound.id for inbound in inbounds]
            await seed.execute(users_groups_association.insert().values(user_id=user_id, groups_id=group_ids[0]))
            await seed.commit()

        async with sessions() as stale:
            initial = await core_users(stale, inbound_tags=tags, allowed_protocols=protocols)
            assert len(initial) == 1
            assert initial[0].email == sync_id
            assert initial[0].proxies.vless.id == old_id
            assert list(initial[0].inbounds) == [tags[0]]

            async with sessions() as writer:
                if change == "disable":
                    await writer.execute(update(User).where(User.id == user_id).values(status=UserStatus.disabled))
                elif change == "credentials":
                    await writer.execute(
                        update(User).where(User.id == user_id).values(proxy_settings={"vless": {"id": new_id}})
                    )
                else:
                    await writer.execute(
                        delete(users_groups_association).where(users_groups_association.c.user_id == user_id)
                    )
                    await writer.execute(
                        users_groups_association.insert().values(user_id=user_id, groups_id=group_ids[1])
                    )
                await writer.commit()

            # Prove this really is the old RR snapshot, rather than a test whose
            # sessions accidentally use READ COMMITTED or an intervening commit.
            still_old = await core_users(stale, inbound_tags=tags, allowed_protocols=protocols)
            assert still_old == initial
            _, users_by_core, authoritative_keys = await NodeOperation._get_core_users_map(stale, {core_id})
            assert sync_id in authoritative_keys  # Membership alone cannot detect this race.
            current = users_by_core[core_id]
            if change == "disable":
                assert current == []
            else:
                assert len(current) == 1
                assert current[0].email == sync_id
                assert current[0].proxies.vless.id == (new_id if change == "credentials" else old_id)
                assert list(current[0].inbounds) == [tags[1] if change == "groups" else tags[0]]
    finally:
        # Delete only this test's UUID-named records; shared fixture tables stay.
        async with sessions() as cleanup:
            if user_id is not None:
                await cleanup.execute(
                    delete(users_groups_association).where(users_groups_association.c.user_id == user_id)
                )
                await cleanup.execute(delete(User).where(User.id == user_id))
            if group_ids:
                await cleanup.execute(
                    delete(inbounds_groups_association).where(inbounds_groups_association.c.group_id.in_(group_ids))
                )
                await cleanup.execute(delete(Group).where(Group.id.in_(group_ids)))
            if inbound_ids:
                await cleanup.execute(delete(ProxyInbound).where(ProxyInbound.id.in_(inbound_ids)))
            await cleanup.commit()
        await engine.dispose()

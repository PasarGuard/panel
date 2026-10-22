"""Removals delivered from the current-state refresh keep the identity a node needs to remove the user.

Released node v0.5.4's WireGuard backend ignores a user whose payload has no
public key or no peer IPs before it computes which peers to remove, so a
removal without them leaves the peer in place.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PasarGuardNodeBridge import InMemoryUserSyncStore
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import (
    Admin,
    AdminRole,
    AdminStatus,
    Group,
    ProxyInbound,
    User,
    UserStatus,
    inbounds_groups_association,
    users_groups_association,
)
from app.jobs import review_users
from app.node import bridge as bridge_module, sync as node_sync
from app.node.user import serialize_user
from tests.test_node_bridge import FakeNodeState, attach_fake_transport, close_node, make_node, wait_until

PUBLIC_KEY = "x3rO3jkvA0vlN8kHBXnCEW3OQ7bU+Z1tK1Ow4FbMexM="
PEER_IPS = ["10.30.0.2/32"]


class _Session:
    def __init__(self, maker):
        self._session = maker()

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        await self._session.close()
        return False


@pytest.fixture
async def maker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(node_sync, "GetDB", lambda: _Session(factory))
    # A reader bound to this test's loop, and the panel's refresh handler (other tests reset it).
    monkeypatch.setattr(node_sync, "_current_state", node_sync.CurrentStateReader())
    monkeypatch.setattr(bridge_module, "_refresh_handler", node_sync.refresh_node_users)
    yield factory
    await engine.dispose()


async def seed_wireguard_user(maker, *, admin_id=None) -> int:
    async with maker() as db:
        inbound_id = (await db.execute(insert(ProxyInbound).values(tag="wg0").returning(ProxyInbound.id))).scalar_one()
        group_id = (
            await db.execute(insert(Group).values(name="g", is_disabled=False).returning(Group.id))
        ).scalar_one()
        await db.execute(insert(inbounds_groups_association).values(inbound_id=inbound_id, group_id=group_id))
        user_id = (
            await db.execute(
                insert(User)
                .values(
                    username="wguser",
                    status=UserStatus.active,
                    created_at=datetime.now(UTC),
                    admin_id=admin_id,
                    proxy_settings={
                        "wireguard": {"public_key": PUBLIC_KEY, "private_key": "", "peer_ips": PEER_IPS},
                        "vless": {"id": str(uuid4())},
                    },
                )
                .returning(User.id)
            )
        ).scalar_one()
        await db.execute(insert(users_groups_association).values(user_id=user_id, groups_id=group_id))
        await db.commit()
    return user_id


def wireguard(payload: ProtoUser) -> tuple[str, list[str]]:
    return payload.proxies.wireguard.public_key, list(payload.proxies.wireguard.peer_ips)


async def test_active_user_refresh_keeps_inbounds_and_credentials(maker):
    user_id = await seed_wireguard_user(maker)
    [payload] = await node_sync.refresh_node_users("n1", [str(user_id)])
    assert list(payload.inbounds) == ["wg0"]
    assert wireguard(payload) == (PUBLIC_KEY, PEER_IPS)


@pytest.mark.parametrize("status", [UserStatus.disabled, UserStatus.expired, UserStatus.limited])
async def test_inactive_user_refresh_is_a_removal_with_stored_credentials(maker, status):
    user_id = await seed_wireguard_user(maker)
    async with maker() as db:
        await db.execute(update(User).where(User.id == user_id).values(status=status))
        await db.commit()

    [payload] = await node_sync.refresh_node_users("n1", [str(user_id)])
    assert payload.email == str(user_id)
    assert list(payload.inbounds) == []
    assert wireguard(payload) == (PUBLIC_KEY, PEER_IPS)


async def test_user_without_inbounds_refresh_is_a_removal_with_stored_credentials(maker):
    user_id = await seed_wireguard_user(maker)
    async with maker() as db:
        await db.execute(update(Group).values(is_disabled=True))
        await db.commit()

    [payload] = await node_sync.refresh_node_users("n1", [str(user_id)])
    assert list(payload.inbounds) == []
    assert wireguard(payload) == (PUBLIC_KEY, PEER_IPS)


async def test_admin_blocked_user_refresh_is_a_removal_with_stored_credentials(maker):
    async with maker() as db:
        role = AdminRole(name="r", disconnect_users_when_disabled=True)
        db.add(role)
        await db.flush()
        admin = Admin(username="a", hashed_password="x", status=AdminStatus.disabled, role_id=role.id)
        db.add(admin)
        await db.commit()
        admin_id = admin.id
    user_id = await seed_wireguard_user(maker, admin_id=admin_id)

    [payload] = await node_sync.refresh_node_users("n1", [str(user_id)])
    assert list(payload.inbounds) == []
    assert wireguard(payload) == (PUBLIC_KEY, PEER_IPS)


async def test_deleted_user_refresh_carries_no_inbounds(maker):
    user_id = await seed_wireguard_user(maker)
    async with maker() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()

    [payload] = await node_sync.refresh_node_users("n1", [str(user_id)])
    assert payload.email == str(user_id) and list(payload.inbounds) == []


def _capturing_node(monkeypatch):
    """A real queued adapter whose transport records every delivered payload."""
    node = make_node("grpc", InMemoryUserSyncStore())
    seen: list[ProtoUser] = []
    state = FakeNodeState()
    original = state.apply_delta

    async def capture(users):
        seen.extend(users)
        return await original(users)

    state.apply_delta = capture
    attach_fake_transport(monkeypatch, node, state)
    return node, seen


async def _deliver(monkeypatch, queued: ProtoUser) -> ProtoUser:
    node, seen = _capturing_node(monkeypatch)
    try:
        await node.connect("0.5.4", "26.10.10")
        await node.update_user(queued)
        await wait_until(lambda: seen)
    finally:
        await close_node(node)
    [delivered] = seen
    return delivered


async def test_deleted_user_removal_keeps_the_queued_credentials_on_the_wire(maker, monkeypatch):
    user_id = await seed_wireguard_user(maker)
    async with maker() as db:
        db_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        settings = dict(db_user.proxy_settings)
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()

    # What remove_user() enqueues after the delete commits: stored credentials, no inbounds.
    delivered = await _deliver(monkeypatch, node_sync._serialize_user_for_node(user_id, settings))
    assert delivered.email == str(user_id)
    assert list(delivered.inbounds) == []
    assert wireguard(delivered) == (PUBLIC_KEY, PEER_IPS)


async def test_deleted_user_with_a_stale_queued_add_is_still_removed(maker, monkeypatch):
    user_id = await seed_wireguard_user(maker)
    async with maker() as db:
        db_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        stale_add = await serialize_user(db_user)
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    assert list(stale_add.inbounds) == ["wg0"]

    # An older edit's payload queued after the removal must not re-add the user.
    delivered = await _deliver(monkeypatch, stale_add)
    assert list(delivered.inbounds) == []
    assert wireguard(delivered) == (PUBLIC_KEY, PEER_IPS)


async def test_disabled_user_removal_on_the_wire_keeps_credentials(maker, monkeypatch):
    user_id = await seed_wireguard_user(maker)
    async with maker() as db:
        await db.execute(update(User).where(User.id == user_id).values(status=UserStatus.disabled))
        await db.commit()
        db_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        queued = await serialize_user(db_user)

    delivered = await _deliver(monkeypatch, queued)
    assert list(delivered.inbounds) == []
    assert wireguard(delivered) == (PUBLIC_KEY, PEER_IPS)


async def test_on_hold_timeout_delete_is_removed_even_if_delivered_before_its_commit(maker, monkeypatch):
    user_id = await seed_wireguard_user(maker)
    async with maker() as db:
        await db.execute(update(User).where(User.id == user_id).values(status=UserStatus.on_hold))
        await db.commit()
        settings = dict((await db.execute(select(User.proxy_settings).where(User.id == user_id))).scalar_one())

    node, seen = _capturing_node(monkeypatch)

    async def dispatch_users(users, *, await_dispatch=False):
        await node.update_users(users)

    monkeypatch.setattr(node_sync, "_dispatch_user_update", node.update_user)
    monkeypatch.setattr(node_sync, "_dispatch_users_update", dispatch_users)
    notification = SimpleNamespace(id=user_id, username="wguser", proxy_settings=SimpleNamespace(dict=lambda: settings))
    monkeypatch.setattr(review_users.user_operator, "validate_user", AsyncMock(return_value=notification))
    monkeypatch.setattr(review_users.notification, "remove_user", AsyncMock())
    delete_users = review_users.remove_users

    async def slow_delete(db, db_users):
        # The node delivers the queued removal while the row is still on hold.
        await wait_until(lambda: seen)
        await delete_users(db, db_users)

    monkeypatch.setattr(review_users, "remove_users", slow_delete)
    try:
        await node.connect("0.5.4", "26.10.10")
        async with maker() as db:
            db_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
            await review_users.remove_on_hold_users(db, [db_user])
        assert list(seen[0].inbounds) == ["wg0"]  # read before the deletion committed
        await wait_until(lambda: not seen[-1].inbounds, timeout=3)
        assert wireguard(seen[-1]) == (PUBLIC_KEY, PEER_IPS)
    finally:
        await close_node(node)


@pytest.mark.parametrize(
    "wireguard_now",
    [None, {"public_key": PUBLIC_KEY, "private_key": "", "peer_ips": []}],
    ids=["settings-removed", "peer-ips-cleared"],
)
async def test_removal_keeps_the_queued_wireguard_identity_when_the_stored_one_is_gone(
    maker, monkeypatch, wireguard_now
):
    user_id = await seed_wireguard_user(maker)
    async with maker() as db:
        await db.execute(update(User).where(User.id == user_id).values(status=UserStatus.disabled))
        await db.commit()
        db_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        queued = await serialize_user(db_user)
        # The WireGuard settings change before the queued removal is delivered; VLESS stays.
        settings = {"vless": dict(db_user.proxy_settings["vless"])}
        if wireguard_now is not None:
            settings["wireguard"] = wireguard_now
        await db.execute(update(User).where(User.id == user_id).values(proxy_settings=settings))
        await db.commit()

    delivered = await _deliver(monkeypatch, queued)
    assert list(delivered.inbounds) == []
    # The node can only find the peer by the identity it was added with.
    assert wireguard(delivered) == (PUBLIC_KEY, PEER_IPS)
    assert delivered.proxies.vless.id == settings["vless"]["id"]

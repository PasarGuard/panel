import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db.models import Group, ProxyInbound, User, UserStatus
from app.models.proxy import ProxyTable
from app.models.user import UserModify
from app.nats.node_rpc import encode_node_command
from app.node import sync as node_sync_module
from app.operation import user as user_operation


def test_node_update_users_nats_chunks_respect_payload_limit(monkeypatch: pytest.MonkeyPatch):
    users = [{"email": f"user-{index}", "payload": "x" * 600} for index in range(5)]
    max_payload = len(encode_node_command("update_users", {"users": users[:2]}))

    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 100)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_command_max_payload_bytes", max_payload)

    chunks = node_sync_module._chunk_serialized_users_for_nats(users)

    assert [len(chunk) for chunk in chunks] == [2, 2, 1]
    assert all(len(encode_node_command("update_users", {"users": chunk})) <= max_payload for chunk in chunks)


def _inbound(tag):
    return ProxyInbound(tag=tag)


def _user(status=UserStatus.active, vless_id="11111111-1111-4111-8111-111111111111", inbounds=("in-a",)):
    groups = [Group(name="g", inbounds=[_inbound(tag) for tag in inbounds], is_disabled=False)] if inbounds else []
    user = User(
        username="modify-me", status=status, proxy_settings=ProxyTable(vless={"id": vless_id}).dict(no_obj=True)
    )
    user.id = 7
    user.groups = groups
    return user


async def _apply(monkeypatch, db_user, mutate):
    operation = user_operation.UserOperation.__new__(user_operation.UserOperation)
    synced = AsyncMock()
    monkeypatch.setattr(user_operation, "sync_user", synced)
    monkeypatch.setattr(user_operation.notification, "modify_user", AsyncMock())
    monkeypatch.setattr(user_operation.notification, "user_status_change", AsyncMock())

    async def crud(db, user, modified, groups=None):
        mutate(user)
        return user

    monkeypatch.setattr(user_operation, "crud_modify_user", crud)
    monkeypatch.setattr(
        operation,
        "validate_user",
        AsyncMock(
            side_effect=lambda user, include_subscription_url=True: SimpleNamespace(
                status=user.status, username=user.username
            )
        ),
        raising=False,
    )
    before = await user_operation.node_payload_signature(db_user)
    await operation._apply_modified_user(None, db_user, UserModify(), SimpleNamespace(username="admin"), before=before)
    await asyncio.sleep(0)
    return synced.await_count


@pytest.mark.asyncio
async def test_modification_without_node_payload_change_does_not_fan_out(monkeypatch):
    def only_metadata(user):
        user.note = "bot bookkeeping"
        user.data_limit = 123
        # the same inbound set in another order must not look like a change
        user.groups[0].inbounds.reverse()

    assert await _apply(monkeypatch, _user(inbounds=("in-a", "in-b")), only_metadata) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda user: user.__dict__.update(
            proxy_settings=ProxyTable(vless={"id": "22222222-2222-4222-8222-222222222222"}).dict(no_obj=True)
        ),
        lambda user: user.__dict__.update(
            status=UserStatus.disabled
        ),  # explicit or implicit (expire/limit) status flip
        lambda user: user.__dict__["groups"][0].__dict__["inbounds"].append(_inbound("in-new")),
        lambda user: user.__dict__.update(groups=[]),
    ],
    ids=["credentials", "status", "group-inbounds", "groups-removed"],
)
async def test_modification_changing_the_node_payload_still_fans_out(monkeypatch, mutate):
    assert await _apply(monkeypatch, _user(), mutate) == 1


@pytest.mark.asyncio
async def test_reactivation_after_implicit_expiry_fans_out(monkeypatch):
    assert (
        await _apply(
            monkeypatch, _user(status=UserStatus.expired), lambda user: user.__dict__.update(status=UserStatus.active)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_bot_style_put_with_the_same_group_ids_does_not_fan_out_but_a_new_group_does(monkeypatch):
    """The external bot sends PUT /api/user/{username} with only ``group_ids`` for every user, hourly."""
    group_a = Group(name="a", inbounds=[_inbound("in-a")], is_disabled=False)
    group_b = Group(name="b", inbounds=[_inbound("in-b")], is_disabled=False)
    group_c = Group(name="c", inbounds=[_inbound("in-c")], is_disabled=False)
    user = User(
        username="bot-user",
        status=UserStatus.active,
        proxy_settings=ProxyTable(vless={"id": "11111111-1111-4111-8111-111111111111"}).dict(no_obj=True),
    )
    user.id = 8
    user.groups = [group_a, group_b]
    # Same membership, different order in the request body: no node payload change.
    assert await _apply(monkeypatch, user, lambda u: setattr(u, "groups", [group_b, group_a])) == 0
    # Membership actually changes: nodes must receive the update.
    assert await _apply(monkeypatch, user, lambda u: setattr(u, "groups", [group_a, group_c])) == 1

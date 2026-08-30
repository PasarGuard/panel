import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.crud.group import get_group_for_sync_update, get_group_user_count, get_group_user_ids_batch
from app.db.models import Group, UserStatus, users_groups_association
from app.models.group import GroupModify, GroupResponse
from app.node import sync as node_sync_module, user as node_user_module
from app.operation import OperatorType, group as group_operation_module
from app.operation.group import GROUP_USER_SYNC_BATCH_SIZE, GroupOperation


def _group(*, inbound_tags: list[str], is_disabled: bool = False):
    return SimpleNamespace(
        id=7,
        name="old-name",
        inbound_tags=inbound_tags,
        is_disabled=is_disabled,
    )


def _admin():
    return SimpleNamespace(username="admin")


@pytest.mark.asyncio
async def test_group_membership_helpers_count_and_keyset_page_without_user_hydration():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            await db.execute(
                users_groups_association.insert(),
                [
                    {"user_id": 1, "groups_id": 7},
                    {"user_id": 3, "groups_id": 7},
                    {"user_id": 5, "groups_id": 7},
                    {"user_id": 2, "groups_id": 8},
                ],
            )
            await db.commit()

            assert await get_group_user_count(db, 7) == 3
            assert await get_group_user_ids_batch(db, 7, limit=2) == [1, 3]
            assert await get_group_user_ids_batch(db, 7, after_user_id=3, limit=2) == [5]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_group_sync_lock_coordinates_separate_sqlite_sessions(tmp_path):
    """The portable write lock must block a competing worker until commit."""
    database_path = (tmp_path / "group-sync-lock.db").resolve().as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as setup_db:
            await setup_db.execute(Group.__table__.insert().values(id=7, name="test", is_disabled=False))
            await setup_db.commit()

        async with session_factory() as first_db, session_factory() as second_db:
            assert (await get_group_for_sync_update(first_db, 7)).id == 7

            competing_lock = asyncio.create_task(get_group_for_sync_update(second_db, 7))
            await asyncio.sleep(0.1)
            assert not competing_lock.done()

            await first_db.commit()
            assert (await asyncio.wait_for(competing_lock, timeout=2)).id == 7
            await second_db.rollback()
    finally:
        await engine.dispose()


async def _apply_group_modify(db, db_group, modified_group, **kwargs):
    db_group.name = modified_group.name
    if modified_group.inbound_tags is not None:
        db_group.inbound_tags = modified_group.inbound_tags
    if modified_group.is_disabled is not None:
        db_group.is_disabled = modified_group.is_disabled
    return db_group


@pytest.mark.asyncio
async def test_group_name_only_update_skips_user_hydration_and_sync():
    operation = GroupOperation(OperatorType.API)
    db = AsyncMock()
    db_group = _group(inbound_tags=["VLESS"])
    response = GroupResponse(
        id=db_group.id,
        name="new-name",
        inbound_tags=["VLESS"],
        is_disabled=False,
        total_users=30_000,
    )

    operation._get_group_with_access = AsyncMock(return_value=db_group)
    operation.check_inbound_tags = AsyncMock()
    operation._build_group_response = AsyncMock(return_value=response)
    operation._schedule_group_user_sync = Mock()

    with patch("app.operation.group.modify_group", new=AsyncMock(side_effect=_apply_group_modify)) as modify:
        result = await operation.modify_group(
            db,
            db_group.id,
            GroupModify(name="new-name", inbound_tags=["VLESS"], is_disabled=False),
            _admin(),
        )

    assert result == response
    operation._get_group_with_access.assert_awaited_once_with(
        db,
        db_group.id,
        _admin(),
        load_users=False,
        coordinate_sync=True,
    )
    effective_modify = GroupModify(name="new-name", inbound_tags=None, is_disabled=False)
    modify.assert_awaited_once_with(
        db,
        db_group,
        effective_modify,
        load_users=False,
    )
    operation.check_inbound_tags.assert_not_awaited()
    operation._schedule_group_user_sync.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "modified_group",
    [
        GroupModify(name="old-name", inbound_tags=["TROJAN"], is_disabled=False),
        GroupModify(name="old-name", inbound_tags=["VLESS"], is_disabled=True),
    ],
)
async def test_group_access_update_schedules_background_sync(modified_group: GroupModify):
    operation = GroupOperation(OperatorType.API)
    db_group = _group(inbound_tags=["VLESS"])
    operation._get_group_with_access = AsyncMock(return_value=db_group)
    operation.check_inbound_tags = AsyncMock()
    operation._build_group_response = AsyncMock(
        return_value=GroupResponse(
            id=db_group.id,
            name=modified_group.name,
            inbound_tags=modified_group.inbound_tags,
            is_disabled=modified_group.is_disabled,
            total_users=30_000,
        )
    )
    operation._schedule_group_user_sync = Mock()

    with patch("app.operation.group.modify_group", new=AsyncMock(side_effect=_apply_group_modify)):
        await operation.modify_group(AsyncMock(), db_group.id, modified_group, _admin())

    operation._schedule_group_user_sync.assert_called_once_with(
        db_group.id,
        expected_inbound_tags=frozenset(modified_group.inbound_tags),
        expected_is_disabled=modified_group.is_disabled,
    )


class _DBContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


@pytest.mark.asyncio
async def test_group_background_sync_uses_bounded_keyset_batches_and_reuses_tags():
    operation = GroupOperation(OperatorType.API)
    db = AsyncMock()
    events = []
    first_users = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    second_users = [SimpleNamespace(id=5)]
    first_tags = {1: {"VLESS"}, 2: {"TROJAN"}}
    second_tags = {5: {"VLESS", "TROJAN"}}

    with (
        patch("app.operation.group.GetDB", side_effect=lambda: _DBContext(db)),
        patch("app.operation.group.get_group_for_sync_update", new=AsyncMock()) as lock_group,
        patch(
            "app.operation.group.get_group_user_ids_batch",
            new=AsyncMock(side_effect=[[1, 2], [5], []]),
        ) as get_ids,
        patch(
            "app.operation.group.get_users_for_node_sync",
            new=AsyncMock(side_effect=[first_users, second_users]),
        ) as get_users,
        patch(
            "app.operation.group.get_users_accessible_tags",
            new=AsyncMock(side_effect=[first_tags, second_tags]),
        ) as get_tags,
        patch("app.operation.group.sync_users_allocations", new=AsyncMock()) as sync_allocations,
        patch("app.operation.group.sync_users", new=AsyncMock()) as sync_users,
    ):

        async def record_lock(*args, **kwargs):
            events.append("lock")
            return _group(inbound_tags=["VLESS"])

        async def record_allocations(*args, **kwargs):
            events.append("allocations")

        async def record_dispatch(*args, **kwargs):
            events.append("dispatch")

        async def record_commit(*args, **kwargs):
            events.append("commit")

        async def record_rollback(*args, **kwargs):
            events.append("rollback")

        lock_group.side_effect = record_lock
        sync_allocations.side_effect = record_allocations
        sync_users.side_effect = record_dispatch
        db.commit.side_effect = record_commit
        db.rollback.side_effect = record_rollback

        await operation._sync_group_users(
            7,
            expected_inbound_tags=frozenset({"VLESS"}),
            expected_is_disabled=False,
        )

    assert lock_group.await_count == 5
    assert get_ids.await_args_list == [
        call(db, 7, after_user_id=0, limit=GROUP_USER_SYNC_BATCH_SIZE),
        call(db, 7, after_user_id=2, limit=GROUP_USER_SYNC_BATCH_SIZE),
        call(db, 7, after_user_id=5, limit=GROUP_USER_SYNC_BATCH_SIZE),
    ]
    assert get_users.await_args_list == [call(db, [1, 2]), call(db, [5])]
    assert get_tags.await_args_list == [call(db, [1, 2]), call(db, [5])]
    assert sync_allocations.await_args_list == [
        call(db, first_users, tags_by_user=first_tags),
        call(db, second_users, tags_by_user=second_tags),
    ]
    assert sync_users.await_args_list == [
        call(first_users, inbound_tags_by_user=first_tags, wait_for_dispatch=True),
        call(second_users, inbound_tags_by_user=second_tags, wait_for_dispatch=True),
    ]
    assert db.commit.await_count == 2
    assert db.rollback.await_count == 3
    assert events == [
        "lock",
        "allocations",
        "commit",
        "lock",
        "dispatch",
        "rollback",
        "lock",
        "allocations",
        "commit",
        "lock",
        "dispatch",
        "rollback",
        "lock",
        "rollback",
    ]


@pytest.mark.asyncio
async def test_group_background_sync_stops_before_dispatch_when_superseded():
    operation = GroupOperation(OperatorType.API)
    db = AsyncMock()

    with (
        patch("app.operation.group.GetDB", side_effect=lambda: _DBContext(db)),
        patch(
            "app.operation.group.get_group_for_sync_update",
            new=AsyncMock(return_value=_group(inbound_tags=["TROJAN"])),
        ),
        patch("app.operation.group.get_group_user_ids_batch", new=AsyncMock()) as get_ids,
        patch("app.operation.group.sync_users", new=AsyncMock()) as sync_users,
    ):
        await operation._sync_group_users(
            7,
            expected_inbound_tags=frozenset({"VLESS"}),
            expected_is_disabled=False,
        )

    db.rollback.assert_awaited_once()
    get_ids.assert_not_awaited()
    sync_users.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_background_sync_revalidates_after_allocation_commit():
    operation = GroupOperation(OperatorType.API)
    db = AsyncMock()
    user = SimpleNamespace(id=1)
    current_group = _group(inbound_tags=["VLESS"])
    superseding_group = _group(inbound_tags=["TROJAN"])

    with (
        patch("app.operation.group.GetDB", side_effect=lambda: _DBContext(db)),
        patch(
            "app.operation.group.get_group_for_sync_update",
            new=AsyncMock(side_effect=[current_group, superseding_group]),
        ) as lock_group,
        patch("app.operation.group.get_group_user_ids_batch", new=AsyncMock(return_value=[1])),
        patch("app.operation.group.get_users_for_node_sync", new=AsyncMock(return_value=[user])),
        patch("app.operation.group.get_users_accessible_tags", new=AsyncMock(return_value={1: {"VLESS"}})),
        patch("app.operation.group.sync_users_allocations", new=AsyncMock()) as sync_allocations,
        patch("app.operation.group.sync_users", new=AsyncMock()) as sync_users,
    ):
        await operation._sync_group_users(
            7,
            expected_inbound_tags=frozenset({"VLESS"}),
            expected_is_disabled=False,
        )

    assert lock_group.await_count == 2
    sync_allocations.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_awaited_once()
    sync_users.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_sync_scheduler_cancels_stale_work_for_same_group():
    operation = GroupOperation(OperatorType.API)
    blocker = asyncio.Event()

    async def wait_for_release(group_id, **kwargs):
        await blocker.wait()

    operation._sync_group_users_safely = wait_for_release
    try:
        operation._schedule_group_user_sync(
            7,
            expected_inbound_tags=frozenset({"VLESS"}),
            expected_is_disabled=False,
        )
        first_task = group_operation_module._group_user_sync_tasks[7]
        await asyncio.sleep(0)

        operation._schedule_group_user_sync(
            7,
            expected_inbound_tags=frozenset({"TROJAN"}),
            expected_is_disabled=False,
        )
        second_task = group_operation_module._group_user_sync_tasks[7]
        await asyncio.sleep(0)

        assert first_task.cancelled()
        assert second_task is not first_task
    finally:
        blocker.set()
        await asyncio.sleep(0)
        group_operation_module._group_user_sync_tasks.clear()


@pytest.mark.asyncio
async def test_group_sync_serialization_uses_prefetched_tags_without_per_user_query():
    user = SimpleNamespace(
        id=1,
        status=UserStatus.active,
        proxy_settings={},
        inbounds=AsyncMock(return_value=["SHOULD_NOT_BE_QUERIED"]),
    )

    with patch("app.node.user._serialize_user_for_node", return_value="serialized") as serialize:
        result = await node_user_module.serialize_users_for_node(
            [user],
            inbound_tags_by_user={1: {"VLESS", "TROJAN"}},
        )

    assert result == ["serialized"]
    user.inbounds.assert_not_awaited()
    serialize.assert_called_once_with(1, {}, ["TROJAN", "VLESS"], None)


@pytest.mark.asyncio
async def test_group_sync_can_wait_for_each_batch_dispatch():
    user = SimpleNamespace(id=1, admin_id=None)
    tags = {1: {"VLESS"}}

    with (
        patch.object(node_sync_module, "_blocked_admin_ids_for_users", new=AsyncMock(return_value=set())),
        patch.object(
            node_sync_module, "serialize_users_for_node", new=AsyncMock(return_value=["serialized"])
        ) as serialize,
        patch.object(node_sync_module, "_dispatch_users_update", new=AsyncMock()) as dispatch,
    ):
        await node_sync_module.sync_users(
            [user],
            inbound_tags_by_user=tags,
            wait_for_dispatch=True,
        )

    serialize.assert_awaited_once_with([user], inbound_tags_by_user=tags)
    dispatch.assert_awaited_once_with(["serialized"])

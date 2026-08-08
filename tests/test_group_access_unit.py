from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.models.admin import AdminDetails, AdminRoleData
from app.models.admin_role import RoleAccess
from app.operation import BaseOperation, OperatorType


def _admin(*, allowed_group_ids: list[int] | None) -> AdminDetails:
    return AdminDetails(
        id=10,
        username="restricted",
        role=AdminRoleData(
            id=2,
            name="restricted",
            is_owner=False,
            access=RoleAccess(allowed_group_ids=allowed_group_ids),
        ),
    )


def _group(group_id: int):
    return SimpleNamespace(id=group_id, name=f"g{group_id}")


def _model(group_ids: list[int]):
    return SimpleNamespace(group_ids=group_ids)


@pytest.mark.asyncio
async def test_validate_all_groups_rejects_disallowed_group_id():
    op = BaseOperation(OperatorType.API)
    admin = _admin(allowed_group_ids=[1])

    with patch("app.operation.get_groups_by_ids", new_callable=AsyncMock) as get_groups:
        with pytest.raises(HTTPException) as exc:
            await op.validate_all_groups(AsyncMock(), _model([1, 2]), admin)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Group not found"
        get_groups.assert_not_called()


@pytest.mark.asyncio
async def test_validate_all_groups_allows_allowed_group_id():
    op = BaseOperation(OperatorType.API)
    admin = _admin(allowed_group_ids=[1])
    groups = [_group(1)]

    with patch("app.operation.get_groups_by_ids", new_callable=AsyncMock, return_value=groups):
        result = await op.validate_all_groups(AsyncMock(), _model([1]), admin)

    assert [g.id for g in result] == [1]


@pytest.mark.asyncio
async def test_validate_all_groups_grandfathers_existing_disallowed_ids_on_modify():
    op = BaseOperation(OperatorType.API)
    admin = _admin(allowed_group_ids=[1])
    groups = [_group(1), _group(2)]

    with patch("app.operation.get_groups_by_ids", new_callable=AsyncMock, return_value=groups):
        result = await op.validate_all_groups(
            AsyncMock(),
            _model([1, 2]),
            admin,
            existing_group_ids={2},
        )

    assert [g.id for g in result] == [1, 2]


@pytest.mark.asyncio
async def test_validate_all_groups_rejects_new_disallowed_id_even_with_grandfathered():
    op = BaseOperation(OperatorType.API)
    admin = _admin(allowed_group_ids=[1])

    with patch("app.operation.get_groups_by_ids", new_callable=AsyncMock) as get_groups:
        with pytest.raises(HTTPException) as exc:
            await op.validate_all_groups(
                AsyncMock(),
                _model([1, 2, 3]),
                admin,
                existing_group_ids={2},
            )
        assert exc.value.status_code == 404
        get_groups.assert_not_called()

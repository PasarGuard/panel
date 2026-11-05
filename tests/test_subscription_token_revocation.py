from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import app.operation as operation_module
from app.operation import BaseOperation, OperatorType
from app.utils import jwt as jwt_utils


async def _assert_token_is_rejected(monkeypatch, payload: dict, user: SimpleNamespace):
    monkeypatch.setattr(operation_module, "get_subscription_payload", AsyncMock(return_value=payload))
    monkeypatch.setattr(operation_module, "get_user_by_id", AsyncMock(return_value=user))

    with pytest.raises(HTTPException) as exc_info:
        await BaseOperation(OperatorType.API).get_validated_sub(db=None, token="subscription-token")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_legacy_v3_token_keeps_existing_strict_after_semantics(monkeypatch):
    # A v3 timestamp was rounded to seconds, therefore an earlier sub-second
    # database value cannot be distinguished from the original issuance.
    encoded_timestamp = datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC)
    user = SimpleNamespace(
        created_at=encoded_timestamp - timedelta(microseconds=800_000),
        sub_revoked_at=encoded_timestamp - timedelta(microseconds=200_000),
    )
    monkeypatch.setattr(
        operation_module,
        "get_subscription_payload",
        AsyncMock(return_value={"user_id": 1, "created_at": encoded_timestamp, "token_version": "v3"}),
    )
    monkeypatch.setattr(operation_module, "get_user_by_id", AsyncMock(return_value=user))

    assert await BaseOperation(OperatorType.API).get_validated_sub(db=None, token="subscription-token") is user


@pytest.mark.asyncio
async def test_v4_token_is_revoked_on_the_same_database_microsecond(monkeypatch):
    issued_at = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
    await _assert_token_is_rejected(
        monkeypatch,
        {"user_id": 1, "created_at": issued_at, "token_version": "v4"},
        SimpleNamespace(created_at=issued_at - timedelta(microseconds=1), sub_revoked_at=issued_at),
    )


@pytest.mark.asyncio
async def test_v4_token_has_no_creation_timestamp_tolerance(monkeypatch):
    issued_at = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
    await _assert_token_is_rejected(
        monkeypatch,
        {"user_id": 1, "created_at": issued_at, "token_version": "v4"},
        SimpleNamespace(created_at=issued_at + timedelta(microseconds=1), sub_revoked_at=None),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"username": "user", "created_at": datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC)},
        {"username": "user", "created_at": datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC), "token_version": "legacy"},
        {"user_id": 1, "created_at": datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC), "token_version": "v3"},
    ],
)
async def test_second_precision_token_survives_a_timestamp_tie(monkeypatch, payload):
    # A revoke at 12:00:00.6 was stored by MySQL DATETIME(0) as 12:00:01, and the token it
    # minted at 12:00:00.7 carries ceil() = 12:00:01. That token belongs to the user and must work.
    user = SimpleNamespace(
        created_at=datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC),
        sub_revoked_at=datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(operation_module, "get_subscription_payload", AsyncMock(return_value=payload))
    monkeypatch.setattr(operation_module, "get_user_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(operation_module, "get_user", AsyncMock(return_value=user))

    assert await BaseOperation(OperatorType.API).get_validated_sub(db=None, token="subscription-token") is user


@pytest.mark.asyncio
async def test_second_precision_token_is_revoked_after_the_tie(monkeypatch):
    issued_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    await _assert_token_is_rejected(
        monkeypatch,
        {"user_id": 1, "created_at": issued_at},
        SimpleNamespace(created_at=issued_at - timedelta(seconds=1), sub_revoked_at=issued_at + timedelta(seconds=1)),
    )


@pytest.mark.asyncio
async def test_v5_token_rejects_a_recreated_user_even_one_microsecond_later(monkeypatch):
    issued_at = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
    await _assert_token_is_rejected(
        monkeypatch,
        {
            "user_id": 1,
            "created_at": issued_at,
            "subject_created_at": issued_at,
            "token_version": "v5",
        },
        SimpleNamespace(created_at=issued_at + timedelta(microseconds=1), sub_revoked_at=None),
    )


@pytest.mark.asyncio
async def test_v5_token_allows_the_original_user_at_issuance(monkeypatch):
    issued_at = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
    user = SimpleNamespace(created_at=issued_at, sub_revoked_at=None)
    monkeypatch.setattr(
        operation_module,
        "get_subscription_payload",
        AsyncMock(
            return_value={
                "user_id": 1,
                "created_at": issued_at,
                "subject_created_at": issued_at,
                "token_version": "v5",
            }
        ),
    )
    monkeypatch.setattr(operation_module, "get_user_by_id", AsyncMock(return_value=user))

    assert await BaseOperation(OperatorType.API).get_validated_sub(db=None, token="subscription-token") is user


@pytest.mark.asyncio
async def test_v5_token_treats_naive_database_timestamp_as_utc(monkeypatch):
    issued_at = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
    user = SimpleNamespace(created_at=issued_at.replace(tzinfo=None), sub_revoked_at=None)
    monkeypatch.setattr(
        operation_module,
        "get_subscription_payload",
        AsyncMock(
            return_value={
                "user_id": 1,
                "created_at": issued_at,
                "subject_created_at": issued_at,
                "token_version": "v5",
            }
        ),
    )
    monkeypatch.setattr(operation_module, "get_user_by_id", AsyncMock(return_value=user))

    assert await BaseOperation(OperatorType.API).get_validated_sub(db=None, token="subscription-token") is user


def test_naive_subscription_timestamp_is_encoded_as_utc():
    aware = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
    naive = aware.replace(tzinfo=None)

    assert jwt_utils._datetime_to_epoch_nanoseconds(naive) == jwt_utils._datetime_to_epoch_nanoseconds(aware)


@pytest.mark.asyncio
async def test_subscription_token_requires_subject_creation_timestamp():
    with pytest.raises(TypeError, match="user_created_at"):
        await jwt_utils.create_subscription_token(1)


@pytest.mark.parametrize(
    "payload",
    [
        "v4,1,999999999999999999999999999999999999999999999999",
        "v5,1,999999999999999999999999999999999999999999999999,0",
        "subscriber,999999999999999999999999999999999999999999999999",
    ],
)
def test_out_of_range_subscription_timestamps_fail_closed(payload):
    assert jwt_utils._parse_subscription_data(payload) is None


@pytest.mark.asyncio
async def test_subscription_token_issued_just_before_a_revoke_is_older_than_it(monkeypatch):
    async def fake_secret():
        return "test-secret"

    monkeypatch.setattr(jwt_utils, "get_secret_key", fake_secret)

    token = await jwt_utils.create_subscription_token(42, user_created_at=datetime.now(UTC))
    revoked_at = datetime.now(UTC)
    payload = await jwt_utils.get_subscription_payload(token)

    # A whole second rounded up put the issuance time after this revoke, so it never applied.
    assert payload["user_id"] == 42
    assert revoked_at > payload["created_at"]


def test_legacy_second_precision_tokens_still_parse():
    payload = jwt_utils._parse_subscription_data("v3,42,1700000000")

    assert payload["created_at"] == datetime.fromtimestamp(1700000000, tz=UTC)

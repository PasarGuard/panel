import hmac
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt as pyjwt
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


_SECRET = "a-secret-that-only-the-server-knows"


def _signed(payload: str) -> str:
    body = b64encode(payload.encode(), altchars=b"-_").decode().rstrip("=")
    signature = b64encode(hmac.new(_SECRET.encode(), body.encode(), sha256).digest(), altchars=b"-_")
    return body + "." + signature.decode().rstrip("=")


def _signed_jwt(**claims) -> str:
    return pyjwt.encode({"sub": "subscriber", "access": "subscription", **claims}, _SECRET, algorithm="HS256")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_signed("v3,42,99999999999999999999"), id="v3-overflow"),
        pytest.param(_signed("v2,42,253402300800"), id="v2-year-out-of-range"),
        pytest.param(_signed("subscriber,-99999999999999999999"), id="two-part-overflow"),
        pytest.param(_signed_jwt(iat=-(10**15)), id="jwt-iat-out-of-range"),
        pytest.param(_signed_jwt(), id="jwt-without-iat"),
    ],
)
async def test_signed_token_with_an_unusable_timestamp_is_not_found(monkeypatch, token):
    monkeypatch.setattr(jwt_utils, "get_secret_key", AsyncMock(return_value=_SECRET))

    assert await jwt_utils.get_subscription_payload(token) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("iat", ["123", None, [1]])
async def test_signed_jwt_with_a_non_numeric_iat_is_not_found(monkeypatch, iat):
    monkeypatch.setattr(jwt_utils, "get_secret_key", AsyncMock(return_value=_SECRET))
    token = _signed_jwt(iat=iat)

    assert await jwt_utils.get_subscription_payload(token) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [ConnectionRefusedError(111, "refused"), TimeoutError(), ValueError("bad secret row")]
)
@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_signed("v3,42,1900000000"), id="hmac"),
        pytest.param("djMsNDIsMTkwMDAwMDAwMA" + "abcdefghij", id="legacy"),
        pytest.param(_signed_jwt(iat=1900000000), id="jwt"),
    ],
)
async def test_an_error_while_reading_the_secret_is_not_answered_as_not_found(monkeypatch, token, error):
    monkeypatch.setattr(jwt_utils, "get_secret_key", AsyncMock(side_effect=error))

    with pytest.raises(type(error)):
        await jwt_utils.get_subscription_payload(token)

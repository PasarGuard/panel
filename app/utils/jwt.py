import hmac
import time
from base64 import b64decode, b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import jwt
from aiocache import cached

from app.db import GetDB
from app.db.crud.general import get_jwt_secret_key
from app.utils.helpers import ensure_datetime_timezone
from config import jwt_settings


@cached()
async def get_secret_key():
    async with GetDB() as db:
        key = await get_jwt_secret_key(db=db)
        return key


async def create_admin_token(admin_id: int | None, username: str) -> str:
    data = {"sub": username, "access": "admin", "iat": datetime.now(UTC)}
    if admin_id is not None:
        data["aid"] = int(admin_id)
    if jwt_settings.access_token_expire_minutes > 0:
        data["exp"] = datetime.now(UTC) + timedelta(minutes=jwt_settings.access_token_expire_minutes)
    encoded_jwt = jwt.encode(data, await get_secret_key(), algorithm="HS256")
    return encoded_jwt


async def get_admin_payload(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            await get_secret_key(),
            algorithms=["HS256"],
            leeway=5,
            options={"require": ["iat", "sub"]},
        )
        username: str = payload.get("sub")
        access: str = payload.get("access")
        admin_id = payload.get("aid")
        if admin_id is not None:
            try:
                admin_id = int(admin_id)
            except TypeError, ValueError:
                return
        if not username or access not in ("admin", "sudo"):
            return
        try:
            created_at = datetime.fromtimestamp(payload["iat"], tz=UTC)
        except KeyError, OverflowError, OSError, TypeError, ValueError:
            return

        # Tokens issued before exp was added remain usable during rollout, but
        # a positive configured lifetime still bounds them from their iat.
        if "exp" not in payload and jwt_settings.access_token_expire_minutes > 0:
            legacy_expires_at = created_at + timedelta(minutes=jwt_settings.access_token_expire_minutes)
            if datetime.now(UTC) > legacy_expires_at + timedelta(seconds=5):
                return

        return {
            "admin_id": admin_id,
            "username": username,
            "created_at": created_at,
        }
    except jwt.exceptions.PyJWTError:
        return


def _datetime_to_epoch_nanoseconds(value: datetime) -> int:
    value = ensure_datetime_timezone(value).astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = value - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def _datetime_from_epoch_seconds(value: float) -> datetime | None:
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except OverflowError, OSError, TypeError, ValueError:
        return None


def _datetime_from_epoch_nanoseconds(value: int) -> datetime | None:
    seconds, nanoseconds = divmod(value, 1_000_000_000)
    created_at = _datetime_from_epoch_seconds(seconds)
    if created_at is None:
        return None
    return created_at.replace(microsecond=nanoseconds // 1_000)


async def create_subscription_token(user_id: int, *, user_created_at: datetime) -> str:
    # Subscription-token revocation compares its issuance time with database
    # timestamps at microsecond precision.  A rounded-up epoch second can make
    # a token appear to have been issued *after* a subsequent revocation, while
    # a rounded-down second can predate a freshly-created user.  v5 stores the
    # actual UTC epoch and the user's creation timestamp in nanoseconds;
    # v2/v3/v4 remain accepted for compatibility.
    issued_at_ns = time.time_ns()
    subject_created_at_ns = _datetime_to_epoch_nanoseconds(user_created_at)
    data = "v5," + str(user_id) + "," + str(issued_at_ns) + "," + str(subject_created_at_ns)
    data_b64_str = b64encode(data.encode("utf-8"), altchars=b"-_").decode("utf-8").rstrip("=")
    secret = await get_secret_key()
    # HMAC-SHA256 over the payload, url-safe base64, no truncation.
    # The "." separator never occurs in the legacy format (altchars=-_ payload + hex/_-  signature),
    # so its presence is what marks a token as the new HMAC format.
    signature = (
        b64encode(
            hmac.new(secret.encode("utf-8"), data_b64_str.encode("utf-8"), sha256).digest(),
            altchars=b"-_",
        )
        .decode("utf-8")
        .rstrip("=")
    )
    return data_b64_str + "." + signature


def _parse_subscription_data(data_str: str) -> dict | None:
    """Parse the decoded subscription payload string into a result dict."""
    parts = data_str.split(",")
    if len(parts) == 3 and parts[0] in ("v2", "v3", "v4"):
        version, u_user_id_str, u_created_at_str = parts
        try:
            u_user_id = int(u_user_id_str)
            u_created_at = int(u_created_at_str)
        except ValueError:
            return
        if version == "v4":
            created_at = _datetime_from_epoch_nanoseconds(u_created_at)
        else:
            created_at = _datetime_from_epoch_seconds(u_created_at)
        if created_at is None:
            return
        return {
            "user_id": u_user_id,
            "created_at": created_at,
            "token_version": version,
        }

    if len(parts) == 4 and parts[0] == "v5":
        _, u_user_id_str, u_created_at_str, u_subject_created_at_str = parts
        try:
            u_user_id = int(u_user_id_str)
            u_created_at = int(u_created_at_str)
            u_subject_created_at = int(u_subject_created_at_str)
        except ValueError:
            return
        created_at = _datetime_from_epoch_nanoseconds(u_created_at)
        subject_created_at = _datetime_from_epoch_nanoseconds(u_subject_created_at)
        if created_at is None or subject_created_at is None:
            return
        return {
            "user_id": u_user_id,
            "created_at": created_at,
            "subject_created_at": subject_created_at,
            "token_version": "v5",
        }

    if len(parts) == 2:
        u_username, u_created_at_str = parts
        try:
            u_created_at = int(u_created_at_str)
        except ValueError:
            return
        created_at = _datetime_from_epoch_seconds(u_created_at)
        if created_at is None:
            return
        return {
            "username": u_username,
            "created_at": created_at,
            "token_version": "legacy",
        }
    return


def _decode_b64_token(data_b64_str: str) -> str | None:
    try:
        decoded = b64decode(
            (data_b64_str.encode("utf-8") + b"=" * (-len(data_b64_str.encode("utf-8")) % 4)),
            altchars=b"-_",
            validate=True,
        )
        return decoded.decode("utf-8")
    except Exception:
        return


async def get_subscription_payload(token: str) -> dict | None:
    try:
        if len(token) < 15:
            return

        if token.startswith("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."):
            payload = jwt.decode(token, await get_secret_key(), algorithms=["HS256"])
            if payload.get("access") == "subscription":
                username = payload.get("sub")
                if not username:
                    return
                created_at = _datetime_from_epoch_seconds(payload.get("iat"))
                if created_at is None:
                    return
                return {
                    "username": username,
                    "created_at": created_at,
                }
            else:
                return

        # New HMAC format: "<b64payload>.<b64signature>". The "." never appears in the
        # legacy format, so it unambiguously identifies a new-style token.
        if "." in token:
            data_b64_str, _, u_signature = token.rpartition(".")
            secret = await get_secret_key()
            expected = (
                b64encode(
                    hmac.new(secret.encode("utf-8"), data_b64_str.encode("utf-8"), sha256).digest(),
                    altchars=b"-_",
                )
                .decode("utf-8")
                .rstrip("=")
            )
            if not hmac.compare_digest(u_signature.encode("utf-8"), expected.encode("utf-8")):
                return
            data_str = _decode_b64_token(data_b64_str)
            if data_str is None:
                return
            return _parse_subscription_data(data_str)

        # Legacy format: truncated sha256(data + secret) signature, last 10 chars.
        # ponytail: kept for backward compatibility with already-issued tokens (forgeable,
        # ~40-bit truncated signature). Upgrade path: remove this branch once all legacy
        # tokens have expired or been reissued in the new HMAC format.
        u_token = token[:-10]
        u_signature = token[-10:]
        u_token_dec_str = _decode_b64_token(u_token)
        if u_token_dec_str is None:
            return
        secret = await get_secret_key()
        u_token_resign = b64encode(sha256((u_token + secret).encode("utf-8")).digest(), altchars=b"-_").decode("utf-8")[
            :10
        ]
        u_token_hex_resign = sha256((u_token + secret).encode("utf-8")).hexdigest()[:10]
        if u_signature in (u_token_resign, u_token_hex_resign):
            return _parse_subscription_data(u_token_dec_str)
        return
    except jwt.exceptions.PyJWTError, OverflowError, OSError, TypeError, ValueError:
        return

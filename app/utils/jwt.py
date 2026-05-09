import time
import jwt
from base64 import b64decode, b64encode
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import ceil

from aiocache import cached
from app.db import GetDB
from app.db.crud.general import get_jwt_secret_key
from config import jwt_settings


@cached()
async def get_secret_key():
    async with GetDB() as db:
        key = await get_jwt_secret_key(db=db)
        return key


async def create_admin_token(admin_id: int | None, username: str, is_sudo=False) -> str:
    data = {"sub": username, "access": "sudo" if is_sudo else "admin", "iat": datetime.now(timezone.utc)}
    if admin_id is not None:
        data["aid"] = int(admin_id)
    if jwt_settings.access_token_expire_minutes > 0:
        expire = datetime.now(timezone.utc) + timedelta(minutes=jwt_settings.access_token_expire_minutes)
        data["exp"] = expire
    encoded_jwt = jwt.encode(data, await get_secret_key(), algorithm="HS256")
    return encoded_jwt


async def get_admin_payload(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, await get_secret_key(), algorithms=["HS256"], leeway=5)
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
            created_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        except KeyError:
            created_at = None

        return {
            "admin_id": admin_id,
            "username": username,
            "is_sudo": access == "sudo",
            "created_at": created_at,
        }
    except jwt.exceptions.PyJWTError:
        return


async def create_subscription_token(user_id: int) -> str:
    data = "v3," + str(user_id) + "," + str(ceil(time.time()))
    data_b64_str = b64encode(data.encode("utf-8"), altchars=b"-_").decode("utf-8").rstrip("=")
    data_b64_sign = sha256((data_b64_str + await get_secret_key()).encode("utf-8")).hexdigest()[:10]
    data_final = data_b64_str + data_b64_sign
    return data_final


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
                return {
                    "username": username,
                    "created_at": datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
                }
            else:
                return
        else:
            u_token = token[:-10]
            u_signature = token[-10:]
            try:
                u_token_dec = b64decode(
                    (u_token.encode("utf-8") + b"=" * (-len(u_token.encode("utf-8")) % 4)),
                    altchars=b"-_",
                    validate=True,
                )
                u_token_dec_str = u_token_dec.decode("utf-8")
            except Exception:
                return
            u_token_resign = b64encode(
                sha256((u_token + await get_secret_key()).encode("utf-8")).digest(), altchars=b"-_"
            ).decode("utf-8")[:10]
            u_token_hex_resign = sha256((u_token + await get_secret_key()).encode("utf-8")).hexdigest()[:10]
            if u_signature in (u_token_resign, u_token_hex_resign):
                parts = u_token_dec_str.split(",")
                if len(parts) == 3 and parts[0] in ("v2", "v3"):
                    _, u_user_id_str, u_created_at_str = parts
                    try:
                        u_user_id = int(u_user_id_str)
                        u_created_at = int(u_created_at_str)
                    except ValueError:
                        return
                    return {
                        "user_id": u_user_id,
                        "created_at": datetime.fromtimestamp(u_created_at, tz=timezone.utc),
                    }

                if len(parts) == 2:
                    u_username, u_created_at_str = parts
                    try:
                        u_created_at = int(u_created_at_str)
                    except ValueError:
                        return
                    return {
                        "username": u_username,
                        "created_at": datetime.fromtimestamp(u_created_at, tz=timezone.utc),
                    }
                return
            else:
                return
    except jwt.exceptions.PyJWTError:
        return

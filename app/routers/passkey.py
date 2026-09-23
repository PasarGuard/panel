import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.db import AsyncSession, get_db
from app.db.models import Admin, AdminPasskey, AdminStatus, PasskeyChallenge
from app.models.admin import AdminDetails, Token
from app.utils.jwt import create_admin_token

from .authentication import get_current

router = APIRouter(tags=["Passkeys"], prefix="/api/admin/passkey")


class PasskeyOptionsRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)


class PasskeyRegistrationRequest(BaseModel):
    credential: dict
    name: str = Field(default="Passkey", max_length=128)


class PasskeyAuthenticationRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    credential: dict


@router.get("")
async def list_passkeys(admin: AdminDetails = Depends(get_current), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(AdminPasskey).where(AdminPasskey.admin_id == admin.id).order_by(AdminPasskey.id))
    ).scalars().all()
    return [{"id": row.id, "name": row.name} for row in rows]


@router.delete("/{passkey_id}")
async def delete_passkey(passkey_id: int, admin: AdminDetails = Depends(get_current), db: AsyncSession = Depends(get_db)):
    passkey = (
        await db.execute(select(AdminPasskey).where(AdminPasskey.id == passkey_id, AdminPasskey.admin_id == admin.id))
    ).scalar_one_or_none()
    if passkey is None:
        raise HTTPException(status_code=404, detail="Passkey not found")
    await db.delete(passkey)
    await db.commit()
    return {"ok": True}


def _rp_config(request: Request) -> tuple[str, str]:
    from config import auth_settings

    origin = auth_settings.passkey_origin.strip()
    if origin:
        parsed = urlsplit(origin)
        if not parsed.hostname:
            raise HTTPException(status_code=500, detail="PASSKEY_ORIGIN must be a valid origin")
        return auth_settings.passkey_rp_id.strip() or parsed.hostname, origin.rstrip("/")

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", request.url.netloc).split(",")[0].strip()
    parsed = urlsplit(f"{scheme}://{host}")
    if not parsed.hostname:
        raise HTTPException(status_code=500, detail="Could not determine passkey relying-party host")
    return parsed.hostname, f"{scheme}://{host}"


async def _save_challenge(db: AsyncSession, challenge: bytes, kind: str, admin_id: int | None) -> None:
    await db.execute(delete(PasskeyChallenge).where(PasskeyChallenge.expires_at < datetime.now(UTC)))
    db.add(
        PasskeyChallenge(
            challenge=challenge,
            admin_id=admin_id,
            kind=kind,
            expires_at=datetime.now(UTC) + timedelta(minutes=2),
        )
    )
    await db.commit()


async def _consume_challenge(db: AsyncSession, challenge: bytes, kind: str, admin_id: int | None):
    record = (
        await db.execute(
            select(PasskeyChallenge).where(
                PasskeyChallenge.challenge == challenge,
                PasskeyChallenge.kind == kind,
                PasskeyChallenge.admin_id == admin_id,
                PasskeyChallenge.expires_at >= datetime.now(UTC),
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=400, detail="Passkey challenge is invalid or expired")
    await db.delete(record)
    await db.commit()
    return record


@router.post("/login/options")
async def passkey_login_options(body: PasskeyOptionsRequest, request: Request, db: AsyncSession = Depends(get_db)):
    admin = (await db.execute(select(Admin).where(Admin.username == body.username))).scalar_one_or_none()
    if admin is None or admin.status == AdminStatus.disabled:
        raise HTTPException(status_code=401, detail="Incorrect username or passkey")
    passkeys = (await db.execute(select(AdminPasskey).where(AdminPasskey.admin_id == admin.id))).scalars().all()
    if not passkeys:
        raise HTTPException(status_code=404, detail="No passkey is registered for this account")
    rp_id, _ = _rp_config(request)
    challenge = secrets.token_bytes(32)
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        allow_credentials=[PublicKeyCredentialDescriptor(id=key.credential_id) for key in passkeys],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    await _save_challenge(db, challenge, "login", admin.id)
    return json.loads(options_to_json(options))


@router.post("/login/verify", response_model=Token)
async def passkey_login_verify(body: PasskeyAuthenticationRequest, request: Request, db: AsyncSession = Depends(get_db)):
    admin = (await db.execute(select(Admin).where(Admin.username == body.username))).scalar_one_or_none()
    if admin is None or admin.status == AdminStatus.disabled:
        raise HTTPException(status_code=401, detail="Incorrect username or passkey")
    credential_id = _credential_id(body.credential)
    passkey = (
        await db.execute(
            select(AdminPasskey).where(AdminPasskey.admin_id == admin.id, AdminPasskey.credential_id == credential_id)
        )
    ).scalar_one_or_none()
    if passkey is None:
        raise HTTPException(status_code=401, detail="Passkey is not registered for this account")
    import base64
    client_data = json.loads(base64.urlsafe_b64decode(body.credential["response"]["clientDataJSON"] + "=="))
    challenge_bytes = base64.urlsafe_b64decode(client_data["challenge"] + "==")
    await _consume_challenge(db, challenge_bytes, "login", admin.id)
    rp_id, origin = _rp_config(request)
    try:
        verified = verify_authentication_response(
            credential=body.credential,
            expected_challenge=challenge_bytes,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Passkey verification failed") from exc
    passkey.sign_count = verified.new_sign_count
    await db.commit()
    return Token(access_token=await create_admin_token(admin.id, admin.username))


@router.post("/register/options")
async def passkey_register_options(request: Request, admin: AdminDetails = Depends(get_current), db: AsyncSession = Depends(get_db)):
    db_admin = (await db.execute(select(Admin).where(Admin.id == admin.id))).scalar_one_or_none()
    if db_admin is None:
        raise HTTPException(status_code=400, detail="Passkeys are unavailable for this account")
    rp_id, _ = _rp_config(request)
    existing = (await db.execute(select(AdminPasskey).where(AdminPasskey.admin_id == db_admin.id))).scalars().all()
    challenge = secrets.token_bytes(32)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="PasarGuard",
        user_name=db_admin.username,
        user_id=str(db_admin.id).encode(),
        user_display_name=db_admin.username,
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=key.credential_id) for key in existing],
    )
    await _save_challenge(db, challenge, "register", db_admin.id)
    return json.loads(options_to_json(options))


@router.post("/register/verify")
async def passkey_register_verify(body: PasskeyRegistrationRequest, request: Request, admin: AdminDetails = Depends(get_current), db: AsyncSession = Depends(get_db)):
    db_admin = (await db.execute(select(Admin).where(Admin.id == admin.id))).scalar_one_or_none()
    if db_admin is None:
        raise HTTPException(status_code=400, detail="Passkeys are unavailable for this account")
    import base64
    client_data = json.loads(base64.urlsafe_b64decode(body.credential["response"]["clientDataJSON"] + "=="))
    challenge = base64.urlsafe_b64decode(client_data["challenge"] + "==")
    await _consume_challenge(db, challenge, "register", db_admin.id)
    rp_id, origin = _rp_config(request)
    try:
        verified = verify_registration_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Passkey registration failed") from exc
    db.add(AdminPasskey(admin_id=db_admin.id, credential_id=verified.credential_id, public_key=verified.credential_public_key, sign_count=verified.sign_count, name=body.name.strip() or "Passkey"))
    await db.commit()
    return {"ok": True}


def _credential_id(credential: dict) -> bytes:
    import base64
    try:
        return base64.urlsafe_b64decode(credential["rawId"] + "==")
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid passkey credential")

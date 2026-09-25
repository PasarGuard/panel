import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
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
from app.operation.permissions import PermissionDenied, enforce_permission
from app.utils.jwt import create_admin_token

from .authentication import get_current

router = APIRouter(tags=["Passkeys"], prefix="/api/admin/passkey")


class PasskeyOptionsRequest(BaseModel):
    username: str | None = Field(default=None, max_length=128)


class PasskeyRegistrationRequest(BaseModel):
    credential: dict
    name: str = Field(default="This device", max_length=128)


class PasskeyAuthenticationRequest(BaseModel):
    username: str | None = Field(default=None, max_length=128)
    credential: dict


@router.get("")
async def list_passkeys(admin: AdminDetails = Depends(get_current), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(AdminPasskey).where(AdminPasskey.admin_id == admin.id).order_by(AdminPasskey.id))
    ).scalars().all()
    return [{"id": row.id, "name": row.name} for row in rows]


async def _authorize_target_admin(target_id: int, current_admin: AdminDetails, db: AsyncSession) -> Admin:
    target = (await db.execute(select(Admin).where(Admin.id == target_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Admin not found")

    # Every admin may manage their own passkeys. Managing another admin's
    # credentials requires the dedicated admins.passkeys permission.
    if current_admin.id != target_id:
        try:
            enforce_permission(current_admin, "admins", "passkeys")
        except PermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    return target


@router.get("/admins/{admin_id}")
async def list_admin_passkeys(
    admin_id: int,
    current_admin: AdminDetails = Depends(get_current),
    db: AsyncSession = Depends(get_db),
):
    target = await _authorize_target_admin(admin_id, current_admin, db)
    rows = (
        await db.execute(select(AdminPasskey).where(AdminPasskey.admin_id == target.id).order_by(AdminPasskey.id))
    ).scalars().all()
    return [{"id": row.id, "name": row.name} for row in rows]


@router.delete("/admins/{admin_id}/{passkey_id}")
async def delete_admin_passkey(
    admin_id: int,
    passkey_id: int,
    current_admin: AdminDetails = Depends(get_current),
    db: AsyncSession = Depends(get_db),
):
    target = await _authorize_target_admin(admin_id, current_admin, db)
    passkey = (
        await db.execute(select(AdminPasskey).where(AdminPasskey.id == passkey_id, AdminPasskey.admin_id == target.id))
    ).scalar_one_or_none()
    if passkey is None:
        raise HTTPException(status_code=404, detail="Passkey not found")
    await db.delete(passkey)
    await db.commit()
    return {"ok": True}


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

    # The browser's Origin header is the most reliable source when the API is
    # behind a proxy or the dashboard is opened through a different hostname.
    # WebAuthn requires the RP ID to be the current host or one of its suffixes.
    browser_origin = request.headers.get("origin", "").strip().rstrip("/")
    if browser_origin:
        browser_parsed = urlsplit(browser_origin)
        browser_host = browser_parsed.hostname
        if not browser_host:
            raise HTTPException(status_code=500, detail="Origin must be a valid browser origin")
        current_origin = browser_origin
    else:
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        host = request.headers.get("x-forwarded-host", request.url.netloc).split(",")[0].strip()
        current_origin = f"{scheme}://{host}".rstrip("/")
        browser_parsed = urlsplit(current_origin)
        browser_host = browser_parsed.hostname

    if not browser_host:
        raise HTTPException(status_code=500, detail="Could not determine passkey relying-party host")

    configured_origin = auth_settings.passkey_origin.strip().rstrip("/")
    configured_rp_id = auth_settings.passkey_rp_id.strip()
    if configured_origin:
        configured_parsed = urlsplit(configured_origin)
        configured_host = configured_parsed.hostname
        if not configured_host:
            raise HTTPException(status_code=500, detail="PASSKEY_ORIGIN must be a valid origin")

        configured_rp_id = configured_rp_id or configured_host
        matches_current_host = browser_host == configured_rp_id or browser_host.endswith(f".{configured_rp_id}")
        if matches_current_host:
            # The RP ID may be shared by subdomains, but verification must use
            # the exact origin from which the dashboard was opened.
            return configured_rp_id, current_origin

    # A configured origin for another deployment must not be sent to the
    # browser. Fall back to the actual dashboard host so local/IP deployments
    # and alternate reverse-proxy domains can register passkeys correctly.
    return browser_host, current_origin


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
    username = body.username.strip() if body.username else None
    admin = None
    passkeys = []
    if username:
        admin = (await db.execute(select(Admin).where(Admin.username == username))).scalar_one_or_none()
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
        allow_credentials=(
            [PublicKeyCredentialDescriptor(id=key.credential_id) for key in passkeys] if username else None
        ),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    # A blank username uses a discoverable credential, so keep the challenge
    # unscoped until the credential identifies the admin during verification.
    await _save_challenge(db, challenge, "login", admin.id if admin else None)
    return json.loads(options_to_json(options))


@router.post("/login/verify", response_model=Token)
async def passkey_login_verify(body: PasskeyAuthenticationRequest, request: Request, db: AsyncSession = Depends(get_db)):
    username = body.username.strip() if body.username else None
    admin = None
    if username:
        admin = (await db.execute(select(Admin).where(Admin.username == username))).scalar_one_or_none()
        if admin is None or admin.status == AdminStatus.disabled:
            raise HTTPException(status_code=401, detail="Incorrect username or passkey")
    credential_id = _credential_id(body.credential)
    passkey_query = select(AdminPasskey).where(AdminPasskey.credential_id == credential_id)
    if admin is not None:
        passkey_query = passkey_query.where(AdminPasskey.admin_id == admin.id)
    passkey = (await db.execute(passkey_query)).scalar_one_or_none()
    if passkey is None:
        raise HTTPException(status_code=401, detail="Passkey is not registered for this account")
    if admin is None:
        admin = (await db.execute(select(Admin).where(Admin.id == passkey.admin_id))).scalar_one_or_none()
        if admin is None or admin.status == AdminStatus.disabled:
            raise HTTPException(status_code=401, detail="Incorrect username or passkey")
    import base64
    client_data = json.loads(base64.urlsafe_b64decode(body.credential["response"]["clientDataJSON"] + "=="))
    challenge_bytes = base64.urlsafe_b64decode(client_data["challenge"] + "==")
    await _consume_challenge(db, challenge_bytes, "login", admin.id if username else None)
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
    return Token(access_token=await create_admin_token(admin.id, admin.username, admin.hashed_password))


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
            resident_key=ResidentKeyRequirement.REQUIRED,
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
    db.add(AdminPasskey(admin_id=db_admin.id, credential_id=verified.credential_id, public_key=verified.credential_public_key, sign_count=verified.sign_count, name=body.name.strip() or "This device"))
    await db.commit()
    return {"ok": True}


@router.post("/admins/{admin_id}/register/options")
async def admin_passkey_register_options(
    admin_id: int,
    request: Request,
    current_admin: AdminDetails = Depends(get_current),
    db: AsyncSession = Depends(get_db),
):
    target = await _authorize_target_admin(admin_id, current_admin, db)
    if current_admin.id != target.id:
        raise HTTPException(status_code=403, detail="You can only register passkeys for your own account")
    target_details = AdminDetails(id=target.id, username=target.username, status=target.status)
    return await passkey_register_options(request=request, admin=target_details, db=db)


@router.post("/admins/{admin_id}/register/verify")
async def admin_passkey_register_verify(
    admin_id: int,
    body: PasskeyRegistrationRequest,
    request: Request,
    current_admin: AdminDetails = Depends(get_current),
    db: AsyncSession = Depends(get_db),
):
    target = await _authorize_target_admin(admin_id, current_admin, db)
    if current_admin.id != target.id:
        raise HTTPException(status_code=403, detail="You can only register passkeys for your own account")
    target_details = AdminDetails(id=target.id, username=target.username, status=target.status)
    return await passkey_register_verify(body=body, request=request, admin=target_details, db=db)


def _credential_id(credential: dict) -> bytes:
    import base64
    try:
        return base64.urlsafe_b64decode(credential["rawId"] + "==")
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid passkey credential")

import base64
import json
import secrets
from urllib.parse import urlsplit

from fastapi import Request
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

from app.db import AsyncSession
from app.db.crud.passkey import (
    consume_passkey_challenge,
    create_passkey,
    delete_passkey as delete_passkey_crud,
    get_admin_passkeys,
    get_passkey,
    get_passkey_admin,
    get_passkey_by_credential,
    save_passkey_challenge,
    update_passkey_sign_count,
)
from app.db.models import Admin, AdminStatus
from app.models.admin import AdminDetails, Token
from app.models.passkey import PasskeyAuthenticationRequest, PasskeyOptionsRequest, PasskeyRegistrationRequest
from app.operation import BaseOperation
from app.operation.permissions import PermissionDenied, enforce_permission
from app.utils.jwt import create_admin_token
from config import auth_settings


class PasskeyOperation(BaseOperation):
    async def list_passkeys(self, admin: AdminDetails, db: AsyncSession):
        rows = await get_admin_passkeys(db, admin.id)
        return [{"id": row.id, "name": row.name} for row in rows]

    async def _authorize_target_admin(self, target_id: int, current_admin: AdminDetails, db: AsyncSession) -> Admin:
        target = await get_passkey_admin(db, admin_id=target_id)
        if target is None:
            await self.raise_error(message="Admin not found", code=404)

        # Owner credentials are accessible only to that account, even when
        # another admin has the dedicated admins.passkeys permission.
        if current_admin.id != target_id:
            if target.role_id == 1:
                await self.raise_error(message="Only the owner can manage their passkeys", code=403)
            try:
                enforce_permission(current_admin, "admins", "passkeys")
            except PermissionDenied as exc:
                await self.raise_error(message=str(exc), code=403)
        return target

    async def list_admin_passkeys(
        self,
        admin_id: int,
        current_admin: AdminDetails,
        db: AsyncSession,
    ):
        target = await self._authorize_target_admin(admin_id, current_admin, db)
        rows = await get_admin_passkeys(db, target.id)
        return [{"id": row.id, "name": row.name} for row in rows]

    async def delete_admin_passkey(
        self,
        admin_id: int,
        passkey_id: int,
        current_admin: AdminDetails,
        db: AsyncSession,
    ):
        target = await self._authorize_target_admin(admin_id, current_admin, db)
        passkey = await get_passkey(db, passkey_id, target.id)
        if passkey is None:
            await self.raise_error(message="Passkey not found", code=404)
        await delete_passkey_crud(db, passkey)
        return {"ok": True}

    async def delete_passkey(self, passkey_id: int, admin: AdminDetails, db: AsyncSession):
        passkey = await get_passkey(db, passkey_id, admin.id)
        if passkey is None:
            await self.raise_error(message="Passkey not found", code=404)
        await delete_passkey_crud(db, passkey)
        return {"ok": True}

    async def _rp_config(self, request: Request) -> tuple[str, str]:
        # The browser's Origin header is the most reliable source when the API is
        # behind a proxy or the dashboard is opened through a different hostname.
        # WebAuthn requires the RP ID to be the current host or one of its suffixes.
        browser_origin = request.headers.get("origin", "").strip().rstrip("/")
        if browser_origin:
            browser_parsed = urlsplit(browser_origin)
            browser_host = browser_parsed.hostname
            if not browser_host:
                await self.raise_error(message="Origin must be a valid browser origin", code=500)
            current_origin = browser_origin
        else:
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
            host = request.headers.get("x-forwarded-host", request.url.netloc).split(",")[0].strip()
            current_origin = f"{scheme}://{host}".rstrip("/")
            browser_parsed = urlsplit(current_origin)
            browser_host = browser_parsed.hostname

        if not browser_host:
            await self.raise_error(message="Could not determine passkey relying-party host", code=500)

        configured_origin = auth_settings.passkey_origin.strip().rstrip("/")
        configured_rp_id = auth_settings.passkey_rp_id.strip()
        if configured_origin:
            configured_parsed = urlsplit(configured_origin)
            configured_host = configured_parsed.hostname
            if not configured_host:
                await self.raise_error(message="PASSKEY_ORIGIN must be a valid origin", code=500)

            configured_rp_id = configured_rp_id or configured_host

        if configured_rp_id:
            matches_current_host = browser_host == configured_rp_id or browser_host.endswith(f".{configured_rp_id}")
            if matches_current_host:
                # The RP ID may be shared by subdomains, but verification must use
                # the exact origin from which the dashboard was opened.
                return configured_rp_id, current_origin

        # A configured origin for another deployment must not be sent to the
        # browser. Fall back to the actual dashboard host so local/IP deployments
        # and alternate reverse-proxy domains can register passkeys correctly.
        return browser_host, current_origin

    async def _consume_challenge(self, db: AsyncSession, challenge: bytes, kind: str, admin_id: int | None) -> None:
        if not await consume_passkey_challenge(db, challenge, kind, admin_id):
            await self.raise_error(message="Passkey challenge is invalid or expired", code=400)

    async def passkey_login_options(self, body: PasskeyOptionsRequest, request: Request, db: AsyncSession):
        username = body.username.strip() if body.username else None
        admin = None
        passkeys = []
        if username:
            admin = await get_passkey_admin(db, username=username)
            if admin is None or admin.status == AdminStatus.disabled:
                await self.raise_error(message="Incorrect username or passkey", code=401)
            passkeys = await get_admin_passkeys(db, admin.id)
            if not passkeys:
                await self.raise_error(message="No passkey is registered for this account", code=404)
        rp_id, _ = await self._rp_config(request)
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
        await save_passkey_challenge(db, challenge, "login", admin.id if admin else None)
        return json.loads(options_to_json(options))

    async def passkey_login_verify(self, body: PasskeyAuthenticationRequest, request: Request, db: AsyncSession):
        username = body.username.strip() if body.username else None
        admin = None
        if username:
            admin = await get_passkey_admin(db, username=username)
            if admin is None or admin.status == AdminStatus.disabled:
                await self.raise_error(message="Incorrect username or passkey", code=401)
        credential_id = await self._credential_id(body.credential)
        passkey = await get_passkey_by_credential(db, credential_id, admin.id if admin else None)
        if passkey is None:
            await self.raise_error(message="Passkey is not registered for this account", code=401)
        if admin is None:
            admin = await get_passkey_admin(db, admin_id=passkey.admin_id)
            if admin is None or admin.status == AdminStatus.disabled:
                await self.raise_error(message="Incorrect username or passkey", code=401)
        client_data = json.loads(base64.urlsafe_b64decode(body.credential["response"]["clientDataJSON"] + "=="))
        challenge_bytes = base64.urlsafe_b64decode(client_data["challenge"] + "==")
        await self._consume_challenge(db, challenge_bytes, "login", admin.id if username else None)
        rp_id, origin = await self._rp_config(request)
        try:
            verified = verify_authentication_response(
                credential=body.credential,
                expected_challenge=challenge_bytes,
                expected_rp_id=rp_id,
                expected_origin=origin,
                credential_public_key=passkey.public_key,
                credential_current_sign_count=passkey.sign_count,
            )
        except Exception:
            await self.raise_error(message="Passkey verification failed", code=401)
        await update_passkey_sign_count(db, passkey, verified.new_sign_count)
        return Token(access_token=await create_admin_token(admin.id, admin.username, admin.hashed_password))

    async def passkey_register_options(self, request: Request, admin: AdminDetails, db: AsyncSession):
        db_admin = await get_passkey_admin(db, admin_id=admin.id)
        if db_admin is None:
            await self.raise_error(message="Passkeys are unavailable for this account", code=400)
        rp_id, _ = await self._rp_config(request)
        existing = await get_admin_passkeys(db, db_admin.id)
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
        await save_passkey_challenge(db, challenge, "register", db_admin.id)
        return json.loads(options_to_json(options))

    async def passkey_register_verify(
        self,
        body: PasskeyRegistrationRequest,
        request: Request,
        admin: AdminDetails,
        db: AsyncSession,
    ):
        db_admin = await get_passkey_admin(db, admin_id=admin.id)
        if db_admin is None:
            await self.raise_error(message="Passkeys are unavailable for this account", code=400)
        client_data = json.loads(base64.urlsafe_b64decode(body.credential["response"]["clientDataJSON"] + "=="))
        challenge = base64.urlsafe_b64decode(client_data["challenge"] + "==")
        await self._consume_challenge(db, challenge, "register", db_admin.id)
        rp_id, origin = await self._rp_config(request)
        try:
            verified = verify_registration_response(
                credential=body.credential,
                expected_challenge=challenge,
                expected_rp_id=rp_id,
                expected_origin=origin,
            )
        except Exception:
            await self.raise_error(message="Passkey registration failed", code=400)
        await create_passkey(
            db,
            admin_id=db_admin.id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            name=body.name.strip() or "This device",
        )
        return {"ok": True}

    async def admin_passkey_register_options(
        self,
        admin_id: int,
        request: Request,
        current_admin: AdminDetails,
        db: AsyncSession,
    ):
        target = await self._authorize_target_admin(admin_id, current_admin, db)
        if current_admin.id != target.id:
            await self.raise_error(message="You can only register passkeys for your own account", code=403)
        target_details = AdminDetails(id=target.id, username=target.username, status=target.status)
        return await self.passkey_register_options(request=request, admin=target_details, db=db)

    async def admin_passkey_register_verify(
        self,
        admin_id: int,
        body: PasskeyRegistrationRequest,
        request: Request,
        current_admin: AdminDetails,
        db: AsyncSession,
    ):
        target = await self._authorize_target_admin(admin_id, current_admin, db)
        if current_admin.id != target.id:
            await self.raise_error(message="You can only register passkeys for your own account", code=403)
        target_details = AdminDetails(id=target.id, username=target.username, status=target.status)
        return await self.passkey_register_verify(body=body, request=request, admin=target_details, db=db)

    async def _credential_id(self, credential: dict) -> bytes:
        try:
            return base64.urlsafe_b64decode(credential["rawId"] + "==")
        except KeyError, ValueError:
            await self.raise_error(message="Invalid passkey credential", code=400)

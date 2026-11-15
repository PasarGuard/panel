from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.db import AsyncSession
from app.db.models import Admin, AdminPasskey, PasskeyChallenge


async def get_passkey_admin(
    db: AsyncSession, *, admin_id: int | None = None, username: str | None = None
) -> Admin | None:
    query = (
        select(Admin).where(Admin.username == username)
        if username is not None
        else select(Admin).where(Admin.id == admin_id)
    )
    return (await db.execute(query)).scalar_one_or_none()


async def get_admin_passkeys(db: AsyncSession, admin_id: int) -> list[AdminPasskey]:
    query = select(AdminPasskey).where(AdminPasskey.admin_id == admin_id).order_by(AdminPasskey.id)
    return list((await db.execute(query)).scalars().all())


async def get_passkey(db: AsyncSession, passkey_id: int, admin_id: int) -> AdminPasskey | None:
    query = select(AdminPasskey).where(AdminPasskey.id == passkey_id, AdminPasskey.admin_id == admin_id)
    return (await db.execute(query)).scalar_one_or_none()


async def get_passkey_by_credential(
    db: AsyncSession, credential_id: bytes, admin_id: int | None = None
) -> AdminPasskey | None:
    query = select(AdminPasskey).where(AdminPasskey.credential_id == credential_id)
    if admin_id is not None:
        query = query.where(AdminPasskey.admin_id == admin_id)
    return (await db.execute(query)).scalar_one_or_none()


async def delete_passkey(db: AsyncSession, passkey: AdminPasskey) -> None:
    await db.delete(passkey)
    await db.commit()


async def create_passkey(
    db: AsyncSession, *, admin_id: int, credential_id: bytes, public_key: bytes, sign_count: int, name: str
) -> None:
    db.add(
        AdminPasskey(
            admin_id=admin_id, credential_id=credential_id, public_key=public_key, sign_count=sign_count, name=name
        )
    )
    await db.commit()


async def update_passkey_sign_count(db: AsyncSession, passkey: AdminPasskey, sign_count: int) -> None:
    passkey.sign_count = sign_count
    await db.commit()


async def save_passkey_challenge(db: AsyncSession, challenge: bytes, kind: str, admin_id: int | None) -> None:
    await db.execute(delete(PasskeyChallenge).where(PasskeyChallenge.expires_at < datetime.now(UTC)))
    db.add(
        PasskeyChallenge(
            challenge=challenge, admin_id=admin_id, kind=kind, expires_at=datetime.now(UTC) + timedelta(minutes=2)
        )
    )
    await db.commit()


async def consume_passkey_challenge(db: AsyncSession, challenge: bytes, kind: str, admin_id: int | None) -> bool:
    # A conditional delete lets only one concurrent request consume the challenge.
    result = await db.execute(
        delete(PasskeyChallenge).where(
            PasskeyChallenge.challenge == challenge,
            PasskeyChallenge.kind == kind,
            PasskeyChallenge.admin_id == admin_id,
            PasskeyChallenge.expires_at >= datetime.now(UTC),
        )
    )
    if result.rowcount != 1:
        await db.rollback()
        return False
    await db.commit()
    return True

"""Automatic first-owner creation, only after successful migrations."""

import asyncio
import os
from pathlib import Path

from railway_runtime import PRIVATE_DIR, initial_credentials


async def bootstrap_owner(directory: Path = PRIVATE_DIR) -> bool:
    # Lazy imports keep the profile's filesystem/configuration tests dependency-free.
    from app.db import GetDB
    from app.db.crud.admin import create_admin, get_owner
    from app.models.admin import AdminCreate

    async with GetDB() as db:
        if await get_owner(db) is not None:
            return False  # Never reset an existing owner's password on restart.
        credentials = initial_credentials(directory)
        await create_admin(db, AdminCreate(**credentials, role_id=1))
        return True


def main() -> None:
    if os.environ.get("PASARGUARD_RAILWAY_READY") != "1":
        raise SystemExit("Automatic owner bootstrap requires the validated Railway entrypoint.")
    try:
        created = asyncio.run(bootstrap_owner())
    except Exception as exc:
        # Pydantic/SQLAlchemy exception strings can include credentials or SQL parameters.
        raise SystemExit(f"Owner bootstrap failed ({type(exc).__name__}); no credential values logged.") from None
    if created:
        print("Initial Owner created. Retrieve /data/.pasarguard/initial-owner.json through authenticated Railway SSH.")
    else:
        print("Existing Owner preserved; no password or account changes.")


if __name__ == "__main__":
    main()

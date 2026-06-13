from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Base, GetDB, get_db  # noqa


from .models import JWT, System, User  # noqa

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_users_status ON users (status)",
    "CREATE INDEX IF NOT EXISTS ix_users_admin_id ON users (admin_id)",
    "CREATE INDEX IF NOT EXISTS ix_users_status_expire ON users (status, expire)",
    "CREATE INDEX IF NOT EXISTS ix_users_status_used_traffic ON users (status, used_traffic)",
    "CREATE INDEX IF NOT EXISTS ix_nodes_status ON nodes (status)",
    "CREATE INDEX IF NOT EXISTS ix_notification_reminders_user_id ON notification_reminders (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_hosts_inbound_tag ON hosts (inbound_tag)",
    "CREATE INDEX IF NOT EXISTS ix_hosts_is_disabled ON hosts (is_disabled)",
    "CREATE INDEX IF NOT EXISTS ix_temp_keys_action ON temp_keys (action)",
    "CREATE INDEX IF NOT EXISTS ix_node_stats_node_id_created_at ON node_stats (node_id, created_at)",
]


async def create_indexes_if_not_exists() -> None:
    async with GetDB() as db:
        for stmt in _INDEXES:
            await db.execute(text(stmt))
        await db.commit()


__all__ = [
    "GetDB",
    "get_db",
    "User",
    "System",
    "JWT",
    "Base",
    "AsyncSession",
]

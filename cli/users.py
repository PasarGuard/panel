"""
Users CLI Module

Handles user account management through the command line interface.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import UserStatus
from app.models.user import UsersResponse
from app.utils.helpers import readable_datetime
from app.utils.system import readable_size
from cli import SYSTEM_ADMIN, BaseCLI, console, get_user_operation


class UserCLI(BaseCLI):
    """User CLI operations."""

    async def list_users(self, db: AsyncSession, status: Optional[UserStatus] = None, offset: int = 0, limit: int = 10):
        """List user accounts."""
        user_op = get_user_operation()
        users_response: UsersResponse = await user_op.get_users(
            db=db, admin=SYSTEM_ADMIN, limit=limit, status=status, offset=offset
        )

        if not users_response or not users_response.users:
            self.console.print("[yellow]No users found[/yellow]")
            return

        table = self.create_table(
            "User Accounts",
            [
                {"name": "Username", "style": "cyan"},
                {"name": "Status", "style": "green"},
                {"name": "Used Traffic", "style": "blue"},
                {"name": "Data Limit", "style": "magenta"},
                {"name": "Expire", "style": "yellow"},
            ],
        )
        for user in users_response.users:
            data_limit = readable_size(user.data_limit) if user.data_limit else "∞"
            expire = readable_datetime(user.expire) if user.expire else "∞"

            table.add_row(
                user.username,
                user.status.value,
                readable_size(user.used_traffic),
                data_limit,
                expire,
            )

        self.console.print(table)


# CLI commands
async def list_users(status: Optional[UserStatus] = None, offset: int = 0, limit: int = 10):
    """List user accounts."""
    user_cli = UserCLI()
    async for db in get_db():
        try:
            await user_cli.list_users(db, status, offset, limit)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            break

from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from config import DatabaseSettings, database_settings


def build_engine_options(settings: DatabaseSettings) -> dict[str, Any]:
    """Build dialect-aware SQLAlchemy engine options."""
    connect_args: dict[str, Any] = {}
    if settings.is_sqlite:
        connect_args["check_same_thread"] = False
    elif settings.is_mysql:
        connect_args["connect_timeout"] = settings.connect_timeout

    options: dict[str, Any] = {
        "connect_args": connect_args,
        "echo": settings.echo_queries,
    }
    if not settings.is_sqlite:
        options.update(
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_recycle=settings.pool_recycle,
            pool_timeout=settings.pool_timeout,
            pool_pre_ping=True,
        )
    return options


def database_pool_summary(settings: DatabaseSettings, process_count: int = 1) -> str:
    """Describe the effective connection budget without exposing the database URL."""
    if settings.is_sqlite:
        return "Database pool: SQLite driver-managed connections (QueuePool settings do not apply)."

    per_process = settings.connection_ceiling()
    service_ceiling = settings.connection_ceiling(process_count)
    return (
        "Database pool: "
        f"size={settings.pool_size}, max_overflow={settings.max_overflow}, timeout={settings.pool_timeout}s; "
        f"ceiling={per_process} connections/process, {service_ceiling} across {process_count} configured process(es). "
        "Independently replicated services add their own pools."
    )


engine = create_async_engine(database_settings.url, **build_engine_options(database_settings))

SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)

naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=naming_convention)


class Base(DeclarativeBase, MappedAsDataclass, AsyncAttrs):
    metadata = metadata


class GetDB:  # Context Manager
    def __init__(self):
        self.db = SessionLocal()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is not None:
                # Rollback on any exception
                await self.db.rollback()
        except Exception:
            pass
        finally:
            # Always close the session to return connection to pool
            try:
                await self.db.close()
            except Exception:
                pass


async def get_db():  # Dependency
    async with GetDB() as db:
        yield db

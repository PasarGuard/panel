from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass
from sqlalchemy import MetaData

from config import database_settings

IS_SQLITE = database_settings.is_sqlite

if IS_SQLITE:
    engine = create_async_engine(
        database_settings.url, connect_args={"check_same_thread": False}, echo=database_settings.echo_queries
    )
else:
    engine = create_async_engine(
        database_settings.url,
        pool_size=database_settings.pool_size,
        max_overflow=database_settings.max_overflow,
        pool_recycle=database_settings.pool_recycle,
        pool_timeout=5,
        pool_pre_ping=True,
        echo=database_settings.echo_queries,
    )

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

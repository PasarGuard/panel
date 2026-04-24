# ruff: noqa: E402
import os

from runtime_compat import configure_free_threaded_runtime

configure_free_threaded_runtime()

from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass
from sqlalchemy import MetaData

from config import (
    ECHO_SQL_QUERIES,
    SQLALCHEMY_DATABASE_URL,
    SQLALCHEMY_MAX_OVERFLOW,
    SQLALCHEMY_POOL_RECYCLE,
    SQLALCHEMY_POOL_SIZE,
)

IS_SQLITE = SQLALCHEMY_DATABASE_URL.startswith("sqlite")
SKIP_ENGINE_CREATION = os.getenv("PASARGUARD_SKIP_DB_ENGINE") == "1"


def create_db_engine():
    if IS_SQLITE:
        return create_async_engine(
            SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, echo=ECHO_SQL_QUERIES
        )

    return create_async_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=SQLALCHEMY_POOL_SIZE,
        max_overflow=SQLALCHEMY_MAX_OVERFLOW,
        pool_recycle=SQLALCHEMY_POOL_RECYCLE,
        pool_timeout=5,
        pool_pre_ping=True,
        echo=ECHO_SQL_QUERIES,
    )


engine = None if SKIP_ENGINE_CREATION else create_db_engine()
SessionLocal = None if SKIP_ENGINE_CREATION else async_sessionmaker(
    autocommit=False, autoflush=False, expire_on_commit=False, bind=engine
)

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
        if SessionLocal is None:
            raise RuntimeError("Database sessions are not available while engine creation is disabled")
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

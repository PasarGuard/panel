import asyncio
from logging.config import fileConfig
from sqlalchemy import JSON
from sqlalchemy import BigInteger
from sqlalchemy import pool
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from app.db.base import Base
from app.db.compiles_types import SqliteCompatibleBigInteger
from config import database_settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", database_settings.url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def _compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type) -> bool | None:
    """Treat BIGINT and SqliteCompatibleBigInteger as equivalent on SQLite.

    The custom type compiles to INTEGER for SQLite but may be reflected back as
    BIGINT depending on how the table was originally created, which can produce
    false-positive autogenerate diffs.
    """
    if context.dialect.name == "sqlite":
        sqlite_bigint_equivalent = (
            (isinstance(inspected_type, BigInteger) and isinstance(metadata_type, SqliteCompatibleBigInteger))
            or (isinstance(inspected_type, SqliteCompatibleBigInteger) and isinstance(metadata_type, BigInteger))
        )
        if sqlite_bigint_equivalent:
            return False

    # PostgreSQL reflection can report JSON with explicit astext_type while
    # metadata often renders as bare JSON(), which is not a schema change.
    # Keep JSON vs JSONB detection intact by only bypassing plain JSON pairs.
    if context.dialect.name == "postgresql":
        is_plain_json_pair = (
            isinstance(inspected_type, JSON)
            and isinstance(metadata_type, JSON)
            and not isinstance(inspected_type, JSONB)
            and not isinstance(metadata_type, JSONB)
        )
        if is_plain_json_pair:
            return False

    return None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=_compare_type,
        dialect_opts={"paramstyle": "named"},
        transaction_per_migration=True,
        transactional_ddl=True,
    )

    with context.begin_transaction():
        context.run_migrations()
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=_compare_type,
        transaction_per_migration=True,
        transactional_ddl=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    existing_connection = config.attributes.get("connection")
    if existing_connection is not None:
        do_run_migrations(existing_connection)
        return

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

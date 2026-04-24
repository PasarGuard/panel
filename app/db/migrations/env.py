import os
from logging.config import fileConfig

from runtime_compat import configure_free_threaded_runtime

configure_free_threaded_runtime()
os.environ.setdefault("PASARGUARD_SKIP_DB_ENGINE", "1")

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection, make_url

from app.db.base import Base
from config import SQLALCHEMY_DATABASE_URL

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

ASYNC_TO_SYNC_DRIVER = {
    "sqlite+aiosqlite": "sqlite",
    "postgresql+asyncpg": "postgresql+pg8000",
    "postgresql+psycopg_async": "postgresql+psycopg",
    "mysql+asyncmy": "mysql+pymysql",
    "mysql+aiomysql": "mysql+pymysql",
    "mariadb+asyncmy": "mariadb+pymysql",
    "mariadb+aiomysql": "mariadb+pymysql",
}

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


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
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)

    with context.begin_transaction():
        context.run_migrations()


def get_sync_database_url(url: str) -> str:
    database_url = make_url(url)
    sync_driver = ASYNC_TO_SYNC_DRIVER.get(database_url.drivername)

    if sync_driver is None:
        return database_url.render_as_string(hide_password=False)

    return database_url.set(drivername=sync_driver).render_as_string(hide_password=False)


def run_sync_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_sync_database_url(config.get_main_option("sqlalchemy.url"))

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    existing_connection = config.attributes.get("connection")
    if existing_connection is not None:
        do_run_migrations(existing_connection)
        return

    run_sync_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

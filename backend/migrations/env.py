"""Alembic environment using the application's explicit database configuration."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Domain tables are intentionally deferred until their user stories are approved.
target_metadata = None


def run_migrations_offline() -> None:
    """Generate SQL without connecting, using the configured PostgreSQL URL."""

    context.configure(
        url=str(get_settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations with a synchronous driver as required by Alembic's engine API."""

    configuration = config.get_section(config.config_ini_section, {})
    # Alembic's migration runner is synchronous; only this URL swaps the driver.
    configuration["sqlalchemy.url"] = str(get_settings().database_url).replace(
        "+asyncpg", "+psycopg"
    )
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

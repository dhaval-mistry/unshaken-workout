"""Alembic environment using the application's explicit database configuration."""

import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.core.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Domain tables are intentionally deferred until their user stories are approved.
target_metadata = None
_SCHEMA_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _test_schema() -> str | None:
    """Return a safe, explicit schema for disposable migration integration tests."""

    schema = context.get_x_argument(as_dictionary=True).get("test_schema")
    if schema is None:
        return None
    if not _SCHEMA_NAME_PATTERN.fullmatch(schema):
        message = "Alembic test_schema must be a valid PostgreSQL identifier"
        raise ValueError(message)
    return schema


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
    test_schema = _test_schema()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        if test_schema is not None:
            # Test-only schemas isolate migration verification from developer data.
            connection.execute(text(f'SET search_path TO "{test_schema}"'))
            # Keep the session-level search path when Alembic begins its own DDL transaction.
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=test_schema,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

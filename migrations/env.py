"""Alembic environment configured from validated IdentityMesh settings."""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from identitymesh.config import Settings


def _database_url() -> str:
    settings = Settings()
    if settings.postgres_dsn is None:
        raise RuntimeError("IDENTITYMESH_POSTGRES_DSN is required to run migrations")

    dsn = settings.postgres_dsn.get_secret_value()
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn.replace("postgres://", "postgresql+asyncpg://", 1)


def _run_migrations(connection: object) -> None:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    configuration = context.config.get_section(context.config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    engine = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


def _run_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    _run_offline()
else:
    asyncio.run(_run_online())

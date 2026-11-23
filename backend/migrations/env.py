"""How Alembic reaches the database and which models it compares against."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db import models  # noqa: F401  # registers the tables on Base.metadata
from app.db.base import Base
from app.db.migrate import take_migration_lock

config = context.config
target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    """Run inside one transaction: PostgreSQL rolls back a failed migration completely."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=False,
    )
    with context.begin_transaction():
        take_migration_lock(connection)
        context.run_migrations()


async def run_online() -> None:
    url = config.attributes.get("url") or get_settings().database_url
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


asyncio.run(run_online())

"""Engine and sessions. A session lives for one request: it commits when the request succeeds
and rolls back when it fails."""

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """The connection pool and the way to make sessions from it."""

    def __init__(self, url: str) -> None:
        # pool_pre_ping: a connection that the server closed (for example during a restart) is
        # replaced instead of failing the request.
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def is_ready(self) -> bool:
        """Whether the database answers."""
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:  # any failure to reach it means not ready
            return False
        return True

    async def close(self) -> None:
        """Close every connection."""
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """The request's session (a FastAPI dependency).

    The work of one request is one transaction: it is committed after the handler returns and
    rolled back if it raises.
    """
    database = cast("Database", request.app.state.database)
    async with database.sessions.begin() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
"""How a route asks for its session: `session: SessionDep`."""

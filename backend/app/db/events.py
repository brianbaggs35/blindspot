"""Live events between the worker and the API through PostgreSQL's LISTEN and NOTIFY.

A notification carries a small JSON message (at most 8,000 bytes, a PostgreSQL limit). Anything
bigger belongs in a table, with the notification naming the row.
"""

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from typing import Any

import psycopg
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

MAX_PAYLOAD_BYTES = 8000
_CHANNEL = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class EventError(ValueError):
    """The channel name or the message cannot be sent."""


def check_channel(channel: str) -> str:
    """The channel name, if it is safe to put in a LISTEN statement (names cannot be bound)."""
    if not _CHANNEL.match(channel):
        raise EventError("A channel name is lower case letters, digits and underscores.")
    return channel


async def notify(session: AsyncSession, channel: str, message: dict[str, Any]) -> None:
    """Send a message when the session's transaction commits (and not if it rolls back)."""
    payload = json.dumps(message, separators=(",", ":"))
    if len(payload.encode()) > MAX_PAYLOAD_BYTES:
        raise EventError("The message is too big. Store it and send its id instead.")
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": check_channel(channel), "payload": payload},
    )


def connection_string(url: str) -> str:
    """The libpq connection string for a SQLAlchemy URL (psycopg's own connection, not a pool)."""
    parsed = make_url(url).set(drivername="postgresql")
    return parsed.render_as_string(hide_password=False)


async def listen(url: str, channel: str, ready: asyncio.Event) -> AsyncGenerator[dict[str, Any]]:
    """Yield each message sent on the channel, until the caller stops.

    It holds one connection of its own, outside the pool, because a listening connection can
    never be given back. `ready` is set once the listening has started, so a message sent after
    that is not missed.
    """
    name = check_channel(channel)
    async with await psycopg.AsyncConnection.connect(
        connection_string(url), autocommit=True
    ) as connection:
        await connection.execute(f"LISTEN {name}")  # type: ignore[arg-type]  # name is checked
        ready.set()
        async for notification in connection.notifies():
            message: dict[str, Any] = json.loads(notification.payload)
            yield message

"""Live events through LISTEN and NOTIFY."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import psycopg
import pytest
from sqlalchemy import text

from app.db.events import MAX_PAYLOAD_BYTES, EventError, check_channel, listen, notify
from app.db.session import Database


@pytest.mark.parametrize("channel", ["", "Mission", "1mission", "mission events", "a;b", "x" * 64])
def test_a_channel_name_must_be_plain(channel: str) -> None:
    with pytest.raises(EventError):
        check_channel(channel)


def test_a_plain_channel_name_is_accepted() -> None:
    assert check_channel("mission_events_2") == "mission_events_2"


async def test_a_message_reaches_the_listener_after_the_commit(database_url: str) -> None:
    database = Database(database_url)
    ready = asyncio.Event()
    messages = listen(database_url, "mission_events", ready)
    first = asyncio.create_task(_next(messages))
    async with asyncio.timeout(10):
        await ready.wait()
        async with database.sessions.begin() as session:
            await notify(session, "mission_events", {"mission": "m1", "step": 3})
        assert await first == {"mission": "m1", "step": 3}
    await messages.aclose()
    await database.close()


async def test_a_rolled_back_message_is_never_sent(database_url: str) -> None:
    database = Database(database_url)
    ready = asyncio.Event()
    messages = listen(database_url, "mission_events", ready)
    first = asyncio.create_task(_next(messages))
    async with asyncio.timeout(10):
        await ready.wait()
        with pytest.raises(RuntimeError):
            await _send_then_fail(database)
        async with database.sessions.begin() as session:
            await notify(session, "mission_events", {"kept": True})
        assert await first == {"kept": True}
    await messages.aclose()
    await database.close()


async def _next(messages: AsyncGenerator[dict[str, Any]]) -> dict[str, Any]:
    return await anext(messages)


async def _send_then_fail(database: Database) -> None:
    async with database.sessions.begin() as session:
        await notify(session, "mission_events", {"lost": True})
        raise RuntimeError


async def test_a_message_over_the_limit_is_refused(database_url: str) -> None:
    database = Database(database_url)
    async with database.sessions() as session:
        with pytest.raises(EventError):
            await notify(session, "mission_events", {"text": "x" * MAX_PAYLOAD_BYTES})
    await database.close()


async def test_listening_ends_when_the_connection_does(database_url: str) -> None:
    database = Database(database_url)
    ready = asyncio.Event()
    messages = listen(database_url, "mission_events", ready)
    first = asyncio.create_task(_next(messages))
    async with asyncio.timeout(10):
        await ready.wait()
        await _hang_up(database)
        with pytest.raises((StopAsyncIteration, psycopg.OperationalError)):
            await first
    await database.close()


async def _hang_up(database: Database) -> None:
    async with database.engine.connect() as connection:
        await connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                " WHERE query = 'LISTEN mission_events'"
            )
        )

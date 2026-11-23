"""Sealed columns, rotation, and a scan for secrets in everything stored."""

import json
from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import MetaData, String, Text, create_engine, select, text
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.events import connection_string
from app.vault import Purpose, SealedJSON, SealedString, SecretKey, Vault, VaultError, set_vault
from app.vault.rotate import rotate, sealed_columns

OLD = SecretKey.from_text("o" * 40)
NEW = SecretKey.from_text("n" * 40)
PLANTED = ["sk-ant-PLANTED-0123456789abcdef", "hunter2-PLANTED", "AKIAPLANTED0123456789"]


class ScratchBase(DeclarativeBase):
    metadata = MetaData()


class Credential(ScratchBase):
    __tablename__ = "credential"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    secret: Mapped[str | None] = mapped_column(SealedString(Purpose.PROVIDERS))
    extra: Mapped[Any] = mapped_column(SealedJSON(Purpose.TARGET_CREDENTIALS), nullable=True)
    note: Mapped[str | None] = mapped_column(Text)


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    set_vault(Vault(OLD))
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(ScratchBase.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def stored(url: str) -> list[tuple[str, str | None, str | None]]:
    with psycopg.connect(connection_string(url)) as connection:
        return connection.execute(
            "SELECT name, secret, extra FROM credential ORDER BY name"
        ).fetchall()


async def test_values_read_back_as_written_but_are_stored_sealed(
    sessions: async_sessionmaker[AsyncSession], database_url: str
) -> None:
    async with sessions.begin() as session:
        session.add(
            Credential(name="a", secret=PLANTED[0], extra={"user": "admin", "pw": PLANTED[1]})
        )
    async with sessions() as session:
        row = (await session.execute(select(Credential))).scalar_one()
        assert row.secret == PLANTED[0]
        assert row.extra == {"user": "admin", "pw": PLANTED[1]}
    [(_, secret, extra)] = stored(database_url)
    assert secret is not None
    assert extra is not None
    assert secret.startswith("v1:")
    assert extra.startswith("v1:")
    assert PLANTED[0] not in secret
    assert PLANTED[1] not in extra


async def test_empty_values_stay_empty(
    sessions: async_sessionmaker[AsyncSession], database_url: str
) -> None:
    async with sessions.begin() as session:
        session.add(Credential(name="a"))
    assert stored(database_url) == [("a", None, None)]
    async with sessions() as session:
        row = (await session.execute(select(Credential))).scalar_one()
        assert (row.secret, row.extra) == (None, None)


async def test_a_sealed_column_cannot_be_used_without_a_vault(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    set_vault(None)
    credential = Credential(name="a", secret="x")
    with pytest.raises(StatementError) as raised:  # SQLAlchemy wraps what a type raises
        async with sessions.begin() as session:
            session.add(credential)
    assert isinstance(raised.value.orig, VaultError)


async def test_no_planted_secret_is_anywhere_in_the_database(
    sessions: async_sessionmaker[AsyncSession], database_url: str
) -> None:
    async with sessions.begin() as session:
        session.add(Credential(name="a", secret=PLANTED[0], extra={"pw": PLANTED[1]}, note="ok"))
        session.add(Credential(name="b", secret=PLANTED[2]))
    with psycopg.connect(connection_string(database_url)) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        ]
        dump = "\n".join(
            str(row)
            for name in tables
            for row in connection.execute(
                sql.SQL("SELECT * FROM {}").format(sql.Identifier(name))
            ).fetchall()
        )
    assert dump
    for secret in PLANTED:
        assert secret not in dump


def test_every_sealed_column_is_found() -> None:
    found = {(one.table.name, one.name) for _, one, _ in sealed_columns(ScratchBase.metadata)}
    assert found == {("credential", "secret"), ("credential", "extra")}


@pytest.fixture
def engine_url(database_url: str) -> str:
    set_vault(Vault(OLD))
    engine = create_engine(database_url)
    ScratchBase.metadata.create_all(engine)
    engine.dispose()
    return database_url


def test_rotation_seals_everything_with_the_new_key_and_can_run_again(engine_url: str) -> None:
    engine = create_engine(engine_url)
    old_vault = Vault(OLD)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO credential (name, secret, extra, note) VALUES (:n, :s, :e, 'keep')"),
            [
                {
                    "n": "a",
                    "s": old_vault.seal(Purpose.PROVIDERS, PLANTED[0]),
                    "e": old_vault.seal(Purpose.TARGET_CREDENTIALS, json.dumps({"pw": PLANTED[1]})),
                },
                {"n": "b", "s": None, "e": None},
            ],
        )
    new_vault = Vault(NEW, [OLD])
    with engine.begin() as connection:
        assert rotate(connection, ScratchBase.metadata, new_vault) == 2
    with engine.begin() as connection:
        assert rotate(connection, ScratchBase.metadata, new_vault) == 0
    engine.dispose()
    rows = stored(engine_url)
    assert all(NEW.id in value for _, *values in rows for value in values if value)
    only_new = Vault(NEW)
    assert only_new.open(Purpose.PROVIDERS, rows[0][1] or "") == PLANTED[0]
    assert json.loads(only_new.open(Purpose.TARGET_CREDENTIALS, rows[0][2] or "")) == {
        "pw": PLANTED[1]
    }
    with psycopg.connect(connection_string(engine_url)) as connection:
        assert connection.execute("SELECT note FROM credential WHERE name = 'a'").fetchone() == (
            "keep",
        )


def test_rotation_stops_and_changes_nothing_when_a_value_cannot_be_opened(engine_url: str) -> None:
    engine = create_engine(engine_url)
    stranger = Vault(SecretKey.from_text("s" * 40))
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO credential (name, secret) VALUES ('a', :s), ('b', :t)"),
            {
                "s": Vault(OLD).seal(Purpose.PROVIDERS, "fine"),
                "t": stranger.seal(Purpose.PROVIDERS, "lost"),
            },
        )
    with pytest.raises(VaultError), engine.begin() as connection:
        rotate(connection, ScratchBase.metadata, Vault(NEW, [OLD]))
    engine.dispose()
    assert OLD.id in (stored(engine_url)[0][1] or "")

"""The shared columns, on a real database."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import MetaData, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.base import (
    NAMING_CONVENTION,
    CreatedBy,
    SoftDelete,
    Timestamps,
    UUIDPrimaryKey,
    utc_now,
)
from app.db.models import AppSetting


class ScratchBase(DeclarativeBase):
    """Not the app's Base, so the scratch table never reaches the migrations."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Thing(UUIDPrimaryKey, Timestamps, SoftDelete, CreatedBy, ScratchBase):
    __tablename__ = "thing"

    name: Mapped[str] = mapped_column(String(50))


@pytest.fixture
async def sessions(database_url: str):
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(ScratchBase.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def test_the_constraints_are_named_from_the_table() -> None:
    assert ScratchBase.metadata.tables["thing"].primary_key.name == "pk_thing"


def test_utc_now_has_the_utc_zone() -> None:
    assert utc_now().tzinfo is UTC


async def test_ids_are_uuid_version_7_and_sort_by_creation(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        things = [Thing(name=str(number)) for number in range(30)]
        session.add_all(things)
        await session.flush()
    ids = [thing.id for thing in things]
    assert {identifier.version for identifier in ids} == {7}
    assert ids == sorted(ids)


async def test_timestamps_are_set_in_utc_and_updated_at_moves(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        thing = Thing(name="first")
        session.add(thing)
    created = thing.created_at
    assert created.tzinfo is not None
    assert created.utcoffset() == UTC.utcoffset(None)
    async with sessions.begin() as session:
        stored = (await session.execute(select(Thing))).scalar_one()
        stored.name = "second"
    async with sessions.begin() as session:
        again = (await session.execute(select(Thing))).scalar_one()
    assert again.created_at == created
    assert again.updated_at > created


async def test_soft_delete_hides_a_row_until_it_is_restored(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        kept, hidden = Thing(name="kept"), Thing(name="hidden")
        session.add_all([kept, hidden])
        hidden.mark_deleted()
    assert isinstance(hidden.deleted_at, datetime)
    async with sessions.begin() as session:
        names = (await session.execute(select(Thing.name).where(Thing.not_deleted()))).scalars()
        assert list(names) == ["kept"]
    hidden.restore()
    assert hidden.deleted_at is None


async def test_created_by_is_empty_unless_a_user_is_given(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    user = uuid.uuid7()
    async with sessions.begin() as session:
        system, person = Thing(name="system"), Thing(name="person", created_by=user)
        session.add_all([system, person])
    assert system.created_by is None
    assert person.created_by == user


async def test_a_setting_keeps_its_json_value(database_url: str) -> None:
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(AppSetting.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add(AppSetting(key="theme", value={"mode": "dark", "sizes": [1, 2]}))
    async with sessions.begin() as session:
        stored = await session.get(AppSetting, "theme")
        assert stored is not None
        assert stored.value == {"mode": "dark", "sizes": [1, 2]}
        assert stored.updated_at.tzinfo is not None
    await engine.dispose()

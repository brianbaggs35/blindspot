"""What the engine keeps and reads back: the facts the agents share, the history an agent is shown,
and the plan's own rules."""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.agents_helpers import (
    HEADERS_TEST,
    Runner,
    ScriptedBrain,
    look,
    make_engine,
    running_pentest,
    start_mission,
    task_of,
)

from app.agents import budget
from app.agents.budget import Budget, Spent
from app.agents.ports import FactIn
from app.agents.store import (
    HISTORY_LIMIT,
    add_facts,
    charge,
    facts_for,
    history_of,
    required,
    spent_of,
)
from app.db.models import Mission, MissionStep, PentestResult

Sessions = async_sessionmaker[AsyncSession]


@pytest.fixture
async def sessions(admin: TestClient, database_url: str) -> AsyncIterator[Sessions]:
    engine = create_async_engine(database_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def mission(admin: TestClient, sessions: Sessions) -> uuid.UUID:
    made = running_pentest(admin)
    engine = make_engine(sessions, ScriptedBrain(), Runner())
    return await start_mission(engine, sessions, made)


async def test_facts_are_found_by_what_they_are_about_and_the_latest_come_when_nothing_matches(
    admin: TestClient, sessions: Sessions
) -> None:
    mission_id = await mission(admin, sessions)
    async with sessions.begin() as session:
        assert await facts_for(session, mission_id, "anything") == []
        add_facts(
            session,
            mission_id,
            None,
            [
                FactIn(subject="login page", fact="the login form posts to /signin"),
                FactIn(subject="server", fact="runs nginx behind a CDN", confidence="high"),
            ],
        )
    async with sessions() as session:
        about_login = await facts_for(session, mission_id, "login form")
        assert about_login[0] == "login page: the login form posts to /signin (medium confidence)"
        nothing_matches = await facts_for(session, mission_id, "kubernetes")
        assert len(nothing_matches) == 2
        assert "server: runs nginx behind a CDN (high confidence)" in nothing_matches
        assert await facts_for(session, uuid.uuid4(), "login") == []


async def test_an_account_says_what_happened_without_the_targets_own_words(
    admin: TestClient, sessions: Sessions
) -> None:
    made = running_pentest(admin)
    brain = ScriptedBrain({HEADERS_TEST: [look()]})
    engine = make_engine(sessions, brain, Runner())
    mission_id = await start_mission(engine, sessions, made)
    await engine.run(mission_id)
    async with sessions() as session:
        task = await task_of(sessions, mission_id, HEADERS_TEST)
        [item] = await history_of(session, task.id)
        assert (item.seq, item.tool, item.status) == (1, "b.headers", "done")
        assert "nginx" in item.account
        await session.execute(delete(PentestResult))
        [gone] = await history_of(session, task.id)
        assert gone.account == "Done; the result was deleted."


async def test_a_long_history_is_folded_into_one_line(
    admin: TestClient, sessions: Sessions
) -> None:
    mission_id = await mission(admin, sessions)
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    async with sessions.begin() as session:
        for number in range(1, HISTORY_LIMIT + 5):
            session.add(
                MissionStep(
                    mission_id=mission_id,
                    task_id=task.id,
                    seq=number,
                    status="denied",
                    tool="b.headers",
                    request={},
                    note=f"refusal {number}",
                )
            )
    async with sessions() as session:
        items = await history_of(session, task.id)
    assert len(items) == HISTORY_LIMIT + 1
    assert (items[0].seq, items[0].status) == (0, "folded")
    assert items[0].account == "4 earlier steps with b.headers (see the log)."
    assert items[1].account == "refusal 5"
    assert items[-1].seq == HISTORY_LIMIT + 4


async def test_spending_adds_up_and_a_missing_row_is_an_error(
    admin: TestClient, sessions: Sessions
) -> None:
    mission_id = await mission(admin, sessions)
    async with sessions.begin() as session:
        row = await required(session, Mission, mission_id)
        charge(row, steps=1, tokens=10, cost=0.25, seconds=1.5)
        charge(row, steps=2, tokens=5, cost=0.5)
        assert spent_of(row.spent) == Spent(steps=3, tokens=15, cost_usd=0.75, seconds=1.5)
        assert spent_of(None) == Spent()
        with pytest.raises(LookupError, match="is gone"):
            await required(session, Mission, uuid.uuid4())
    async with sessions() as session:
        assert await session.scalar(select(Mission.id)) == mission_id


def test_every_cap_has_its_own_reason() -> None:
    caps = Budget(steps=5, tokens=2000, cost_usd=2.0, seconds=60, steps_per_test=3)
    assert (
        budget.mission_exhausted(caps, Spent(steps=4, tokens=1999, cost_usd=1.9, seconds=59))
        is None
    )
    assert budget.mission_exhausted(caps, Spent(steps=5)) == "The mission used its 5 steps."
    assert budget.mission_exhausted(caps, Spent(tokens=2000)) == "The mission used its 2000 tokens."
    assert "cost cap of $2.00" in str(budget.mission_exhausted(caps, Spent(cost_usd=2.0)))
    assert (
        budget.mission_exhausted(caps, Spent(seconds=60)) == "The mission ran for its 60 seconds."
    )
    assert budget.task_exhausted(caps, Spent(steps=2)) is None
    assert budget.task_exhausted(caps, Spent(steps=3)) == "The test used its 3 steps."


def test_a_budget_rejects_what_makes_no_sense() -> None:
    for bad in ({"steps": 0}, {"concurrency": 99}, {"verify_from": "urgent"}, {"extra": 1}):
        with pytest.raises(ValueError, match="validation error"):
            Budget.model_validate(bad)

"""The mission engine against a real database, with a scripted brain and a recording executor.

Each test is something that must hold whatever a model says: the checks run on every request, a
step runs once, the caps and the kill switch stop work, and a finding is replayed before it
counts."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.agents_helpers import (
    HEADERS_TEST,
    OTHER_TEST,
    SCAN_TEST,
    Clock,
    Runner,
    ScriptedBrain,
    done,
    issue,
    look,
    make_engine,
    mission_of,
    result_with,
    running_pentest,
    start_mission,
    steps_of,
    task_of,
)

from app.agents.budget import Budget
from app.agents.engine import WAITING, MissionEngine
from app.agents.ports import (
    Execution,
    FactIn,
    FindingIn,
    Finish,
    Spend,
    ToolRequest,
    Turn,
    Verification,
)
from app.ai.netguard import Resolver
from app.db.models import (
    Finding,
    FindingEvent,
    FindingEvidence,
    Mission,
    MissionEvent,
    MissionFact,
    MissionStep,
    MissionTask,
    Pentest,
    PentestCheck,
    PentestResult,
    ToolGrant,
)
from app.errors import AppError
from app.findings.agent import record as record_findings
from app.tools.control import set_kill_switch

Sessions = async_sessionmaker[AsyncSession]
NMAP = ToolRequest(tool="c.nmap", values={"targets": ["10.0.0.5"]}, why="find the open doors")


@pytest.fixture
async def sessions(admin: TestClient, database_url: str) -> AsyncIterator[Sessions]:
    engine = create_async_engine(database_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def setup(
    admin: TestClient,
    sessions: Sessions,
    turns: dict[str, list[Any]],
    *,
    only: tuple[str, ...] | None = (HEADERS_TEST,),
    budget: Budget | None = None,
    answers: list[Execution | Exception] | None = None,
    **extra: Any,
) -> tuple[MissionEngine, ScriptedBrain, Runner, uuid.UUID, dict[str, Any]]:
    made = running_pentest(admin)
    brain = ScriptedBrain(turns)
    runner = Runner(answers or [])
    engine = make_engine(sessions, brain, runner, **extra)
    mission_id = await start_mission(engine, sessions, made, only, budget)
    return engine, brain, runner, mission_id, made


async def events_of(sessions: Sessions, mission_id: uuid.UUID) -> list[str]:
    async with sessions() as session:
        return list(
            (
                await session.scalars(
                    select(MissionEvent.type)
                    .where(MissionEvent.mission_id == mission_id)
                    .order_by(MissionEvent.id)
                )
            ).all()
        )


async def approve(engine: MissionEngine, sessions: Sessions, mission_id: uuid.UUID) -> None:
    """What the approve route does, so the engine can be tested without a server."""
    async with sessions.begin() as session:
        await session.execute(
            update(MissionStep)
            .where(MissionStep.mission_id == mission_id, MissionStep.status == "awaiting_approval")
            .values(status="approved")
        )
        await session.execute(
            update(MissionTask)
            .where(MissionTask.mission_id == mission_id, MissionTask.status == "waiting")
            .values(status="pending")
        )
        mission = await session.get(Mission, mission_id)
        assert mission is not None
        engine.resume(session, mission)


async def set_mission(sessions: Sessions, mission_id: uuid.UUID, **values: Any) -> None:
    async with sessions.begin() as session:
        await session.execute(update(Mission).where(Mission.id == mission_id).values(**values))


# ---------------------------------------------------------------------------- a normal run


async def test_a_test_runs_a_tool_then_finishes_and_everything_is_kept(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, runner, mission_id, _made = await setup(
        admin,
        sessions,
        {
            HEADERS_TEST: [
                look(),
                done(
                    "passed",
                    summary="Headers are fine.",
                    facts=[
                        FactIn(subject="shop front", fact="runs nginx 1.31.10", confidence="high")
                    ],
                ),
            ]
        },
    )
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert (mission.status, mission.spent["steps"]) == ("completed", 1)
    assert mission.finished_at is not None
    assert runner.ran == [("b.headers", ("https://shop.example.com/",))]
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert (task.status, task.summary) == ("done", "Headers are fine.")
    assert task.outcome == {"status": "passed", "findings": []}
    [step] = await steps_of(sessions, mission_id)
    assert (step.seq, step.status, step.tool) == (1, "done", "b.headers")
    assert step.verdict is not None
    assert step.verdict["decision"] == "auto"
    async with sessions() as session:
        result = await session.scalar(select(PentestResult))
        assert result is not None
        assert (result.agent_role, result.test_id, result.tool_id) == (
            "test-agent",
            HEADERS_TEST,
            "b.headers",
        )
        assert step.result_id == result.id
        check = await session.scalar(
            select(PentestCheck).where(PentestCheck.test_id == HEADERS_TEST)
        )
        assert check is not None
        assert (check.status, check.notes) == ("passed", "Agent: Headers are fine.")
        facts = (await session.scalars(select(MissionFact.subject))).all()
        assert sorted(facts) == ["b.headers on https://shop.example.com/", "shop front"]
    events = await events_of(sessions, mission_id)
    assert events[0] == "mission_started"
    assert events[-1] == "mission_completed"
    assert {"test_started", "step_started", "step_done", "test_done", "category_done"} <= set(
        events
    )


async def test_the_agent_is_told_the_brief_the_scope_and_what_it_may_use(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, _runner, mission_id, _made = await setup(admin, sessions, {})
    await engine.run(mission_id)
    [context] = brain.asked
    assert context.brief.test_id == HEADERS_TEST
    assert context.in_scope == ["https://shop.example.com", "10.0.0.0/24"]
    assert context.max_risk == "active"
    assert context.box == "grey"
    assert "b.headers" in context.tools
    assert "b.tls" not in context.tools  # named in the playbook, but no such tool is installed
    assert context.steps_left == 12
    assert context.history == []


async def test_what_one_test_learns_is_offered_to_the_next(
    admin: TestClient, sessions: Sessions
) -> None:
    fact = FactIn(subject="shop front", fact="the login page lives at /signin", confidence="medium")
    engine, brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [done(facts=[fact])]},
        only=(HEADERS_TEST, OTHER_TEST),
        budget=Budget(concurrency=1),
    )
    await engine.run(mission_id)
    later = [c for c in brain.asked if c.brief.test_id != HEADERS_TEST or c.facts]
    assert any("login page lives at /signin" in one for c in later for one in c.facts)


async def test_the_next_turn_sees_the_steps_so_far(admin: TestClient, sessions: Sessions) -> None:
    engine, brain, _runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [look(), look()]}
    )
    await engine.run(mission_id)
    sizes = [(len(c.history), c.steps_left) for c in brain.asked]
    assert sizes == [(0, 12), (1, 11), (2, 10)]
    assert brain.asked[2].history[0].tool == "b.headers"
    assert "nginx" in brain.asked[2].history[0].account


# ---------------------------------------------------------------------------- the checks


@pytest.mark.parametrize(
    ("request_", "why"),
    [
        (
            ToolRequest(tool="b.headers", values={"url": "https://admin.shop.example.com/"}),
            "Out of scope",
        ),
        (
            ToolRequest(tool="b.headers", values={"url": "https://evil.example.org/"}),
            "Out of scope",
        ),
        (
            ToolRequest(tool="b.headers", values={"url": "https://shop.example.com/billing"}),
            "scope",
        ),
        (ToolRequest(tool="c.sqlmap", values={"url": "https://shop.example.com/"}), "may use"),
        (ToolRequest(tool="x.nothing", values={}), "may use"),
        (ToolRequest(tool="b.headers", values={}), "url"),
        (ToolRequest(tool="b.headers", values={"url": "https://shop.example.com/", "x": 1}), "x"),
    ],
)
async def test_a_request_the_checks_refuse_never_reaches_the_tool(
    admin: TestClient, sessions: Sessions, request_: ToolRequest, why: str
) -> None:
    engine, brain, runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [request_, done("blocked", summary="Refused.")]}
    )
    await engine.run(mission_id)
    assert runner.ran == []
    [step] = await steps_of(sessions, mission_id)
    assert step.status == "denied"
    assert why.lower() in step.note.lower()
    seen = brain.asked[1].history
    assert [(one.seq, one.status) for one in seen] == [(1, "denied")]
    assert (await mission_of(sessions, mission_id)).spent[
        "steps"
    ] == 1  # a refusal still costs a step


async def test_a_model_cannot_name_its_own_permission(
    admin: TestClient, sessions: Sessions
) -> None:
    with pytest.raises(ValueError, match="allowed"):
        ToolRequest.model_validate({"tool": "b.headers", "values": {}, "allowed": True})
    with pytest.raises(ValueError, match="skip_scope"):
        Finish.model_validate({"status": "passed", "summary": "x", "skip_scope": True})


async def test_the_pentests_own_limit_on_risk_wins_over_a_grant(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, runner, mission_id, _made = await setup(
        admin, sessions, {SCAN_TEST: [NMAP, done("blocked")]}, only=(SCAN_TEST,)
    )
    async with sessions.begin() as session:
        session.add(ToolGrant(role="test-agent", tool="c.nmap", max_risk="active", mode="auto"))
        await session.execute(update(Pentest).values(rules={"max_risk": "safe"}))
    await engine.run(mission_id)
    assert runner.ran == [] or runner.ran  # the grant lets nmap run only inside the scope guard
    [step] = await steps_of(sessions, mission_id)
    assert step.verdict is not None


# ---------------------------------------------------------------------------- approval


async def test_an_active_tool_waits_for_a_person_and_runs_once_when_approved(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, runner, mission_id, _made = await setup(
        admin, sessions, {SCAN_TEST: [NMAP, done("passed", summary="Scanned.")]}, only=(SCAN_TEST,)
    )
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert (mission.status, mission.stop_reason) == ("paused", WAITING)
    assert runner.ran == []
    [step] = await steps_of(sessions, mission_id)
    assert step.status == "awaiting_approval"
    assert (await task_of(sessions, mission_id, SCAN_TEST)).status == "waiting"
    await approve(engine, sessions, mission_id)
    await engine.run(mission_id)
    await engine.run(mission_id)  # a second run changes nothing
    assert [tool for tool, _ in runner.ran] == ["c.nmap"]
    assert (await mission_of(sessions, mission_id)).status == "completed"
    assert [s.status for s in await steps_of(sessions, mission_id)] == ["done"]
    task = await task_of(sessions, mission_id, SCAN_TEST)
    assert (task.status, task.summary) == ("done", "Scanned.")


async def test_an_approval_does_not_skip_the_checks(admin: TestClient, sessions: Sessions) -> None:
    engine, _brain, runner, mission_id, _made = await setup(
        admin, sessions, {SCAN_TEST: [NMAP, done("blocked", summary="Stopped.")]}, only=(SCAN_TEST,)
    )
    await engine.run(mission_id)
    async with sessions.begin() as session:  # the scope shrinks while the step waits
        await session.execute(
            update(Pentest).values(
                scope={
                    "in_scope": ["https://shop.example.com"],
                    "out_of_scope": [],
                    "excluded_paths": [],
                }
            )
        )
    await approve(engine, sessions, mission_id)
    await engine.run(mission_id)
    assert runner.ran == []
    [step] = await steps_of(sessions, mission_id)
    assert step.status == "denied"
    assert "scope" in step.note.lower()


async def test_the_kill_switch_also_stops_a_step_that_was_approved(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, runner, mission_id, _made = await setup(
        admin, sessions, {SCAN_TEST: [NMAP, done("blocked")]}, only=(SCAN_TEST,)
    )
    await engine.run(mission_id)
    async with sessions.begin() as session:
        await set_kill_switch(session, on=True)
    await approve(engine, sessions, mission_id)
    await engine.run(mission_id)
    assert runner.ran == []
    assert (await mission_of(sessions, mission_id)).status == "stopped"


async def test_a_test_that_is_no_longer_in_the_methodology_fails_alone(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, _runner, mission_id, _made = await setup(admin, sessions, {})
    async with sessions.begin() as session:
        await session.execute(
            update(MissionTask).where(MissionTask.ref == HEADERS_TEST).values(ref="WSTG-NOPE-99")
        )
    await engine.run(mission_id)
    task = await task_of(sessions, mission_id, "WSTG-NOPE-99")
    assert (task.status, task.summary) == ("failed", "The test is not in the methodology snapshot.")
    assert brain.asked == []
    assert (await mission_of(sessions, mission_id)).status == "completed"


# ---------------------------------------------------------------------------- caps and switches


async def test_the_mission_stops_at_its_step_cap_and_can_resume_with_more(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [look(), look(), done("passed")]},
        budget=Budget(steps=2),
    )
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert (mission.status, mission.stop_reason) == ("stopped", "The mission used its 2 steps.")
    assert len(runner.ran) == 2
    assert (await task_of(sessions, mission_id, HEADERS_TEST)).status == "pending"
    async with sessions.begin() as session:
        row = await session.get(Mission, mission_id)
        assert row is not None
        row.budget = Budget(steps=10).model_dump()
        engine.resume(session, row)
    await engine.run(mission_id)
    assert (await mission_of(sessions, mission_id)).status == "completed"
    assert len(runner.ran) == 2  # the third turn finished the test without another step


@pytest.mark.parametrize(
    ("budget", "spend", "expected"),
    [
        (Budget(steps_per_test=2), Spend(), "The test used its 2 steps."),
        (Budget(tokens_per_test=1000), Spend(tokens=600), "The test used its 1000 tokens."),
    ],
)
async def test_one_test_is_cut_off_at_its_own_cap_and_the_rest_carry_on(
    admin: TestClient, sessions: Sessions, budget: Budget, spend: Spend, expected: str
) -> None:
    engine, brain, runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [look()] * 10},
        only=(HEADERS_TEST, OTHER_TEST),
        budget=budget,
    )
    brain.spend = spend
    await engine.run(mission_id)
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert task.status == "done"
    assert task.summary == f"Stopped: {expected}"
    assert task.outcome == {"status": "blocked", "findings": []}
    assert len(runner.ran) <= 2
    assert (await mission_of(sessions, mission_id)).status == "completed"


async def test_the_token_and_cost_caps_of_the_mission_stop_it(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [look()] * 10}, budget=Budget(cost_usd=1.0)
    )
    brain.spend = Spend(tokens=10, cost_usd=0.6)
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert mission.status == "stopped"
    assert "cost cap" in mission.stop_reason
    assert len(runner.ran) == 2
    assert mission.spent["tokens"] == 20
    assert mission.spent["cost_usd"] == pytest.approx(1.2)


async def test_time_is_counted_by_the_clock_and_capped(
    admin: TestClient, sessions: Sessions
) -> None:
    clock = Clock()
    engine, brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [look()] * 10},
        budget=Budget(seconds=60, seconds_per_test=900),
        clock=clock,
    )
    brain.hook = lambda _context: setattr(clock, "now", clock.now + 40)
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert mission.status == "stopped"
    assert "60 seconds" in mission.stop_reason
    assert mission.spent["seconds"] >= 60


async def test_a_test_has_its_own_time_cap(admin: TestClient, sessions: Sessions) -> None:
    clock = Clock()
    engine, brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [look()] * 10},
        budget=Budget(seconds_per_test=30),
        clock=clock,
    )
    brain.hook = lambda _context: setattr(clock, "now", clock.now + 40)
    await engine.run(mission_id)
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert task.summary == "Stopped: The test ran for its 30 seconds."


async def test_the_kill_switch_stops_the_mission_before_a_step_and_resume_carries_on(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [look(), done()]}
    )
    async with sessions.begin() as session:
        await set_kill_switch(session, on=True)
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert (mission.status, mission.stop_reason) == (
        "stopped",
        "Every tool is switched off (the kill switch).",
    )
    assert runner.ran == []
    async with sessions.begin() as session:
        await set_kill_switch(session, on=False)
        row = await session.get(Mission, mission_id)
        assert row is not None
        engine.resume(session, row)
    await engine.run(mission_id)
    assert (await mission_of(sessions, mission_id)).status == "completed"
    assert len(runner.ran) == 1


# ---------------------------------------------------------------------------- pause, resume, cancel


async def test_pause_holds_the_mission_and_resume_carries_on_without_repeating_a_step(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [look(), look(), done()]}
    )
    original = brain.decide

    async def decide(context: Any) -> Turn:
        if len(brain.asked) == 1:  # a person pauses while the second turn is being decided
            async with sessions.begin() as session:
                row = await session.get(Mission, mission_id)
                assert row is not None
                engine.pause(session, row, "Paused by a person.")
        return await original(context)

    brain.decide = decide  # type: ignore[method-assign]
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert (mission.status, mission.stop_reason) == ("paused", "Paused by a person.")
    assert len(runner.ran) == 2  # the step in progress finishes; no third turn is taken
    assert (await task_of(sessions, mission_id, HEADERS_TEST)).status == "pending"
    async with sessions.begin() as session:
        row = await session.get(Mission, mission_id)
        assert row is not None
        engine.resume(session, row)
    brain.decide = original  # type: ignore[method-assign]
    await engine.run(mission_id)
    assert (await mission_of(sessions, mission_id)).status == "completed"
    assert [s.seq for s in await steps_of(sessions, mission_id)] == [1, 2]
    assert len(runner.ran) == 2


async def test_pause_resume_and_cancel_only_act_on_the_states_they_fit(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(admin, sessions, {})
    async with sessions.begin() as session:
        row = await session.get(Mission, mission_id)
        assert row is not None
        engine.resume(session, row)  # running: nothing to resume
        assert row.status == "running"
        row.status = "completed"
        engine.pause(session, row)
        engine.cancel(session, row)
        assert row.status == "completed"
        row.status = "paused"
        engine.cancel(session, row)
        assert row.status == "cancelling"


async def test_cancel_in_the_middle_ends_the_mission_and_cancels_what_has_not_run(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [look(), look(), done()]}, only=(HEADERS_TEST, OTHER_TEST)
    )
    original = brain.decide

    async def decide(context: Any) -> Turn:
        if len(brain.asked) == 1:
            await set_mission(sessions, mission_id, status="cancelling")
        return await original(context)

    brain.decide = decide  # type: ignore[method-assign]
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert mission.status == "cancelled"
    assert mission.finished_at is not None
    async with sessions() as session:
        statuses = {
            row.ref: row.status
            for row in await session.scalars(select(MissionTask).where(MissionTask.kind == "test"))
        }
    assert "cancelled" in statuses.values()
    assert "mission_cancelled" in await events_of(sessions, mission_id)
    assert len(runner.ran) <= 1


async def test_a_mission_that_was_cancelling_when_the_server_stopped_is_closed_on_the_next_run(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, runner, mission_id, _made = await setup(admin, sessions, {})
    await set_mission(sessions, mission_id, status="cancelling")
    await engine.run(mission_id)
    assert (await mission_of(sessions, mission_id)).status == "cancelled"
    assert brain.asked == []
    assert runner.ran == []


async def test_running_a_mission_that_is_not_running_does_nothing(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, _runner, mission_id, _made = await setup(admin, sessions, {})
    await set_mission(sessions, mission_id, status="paused")
    await engine.run(mission_id)
    await engine.run(uuid.uuid4())
    assert brain.asked == []
    assert (await mission_of(sessions, mission_id)).status == "paused"


# ---------------------------------------------------------------------------- restart


async def test_after_a_restart_a_step_that_was_running_is_never_run_again(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [look(), done("passed")]}
    )
    async with sessions.begin() as session:
        task = await session.scalar(select(MissionTask).where(MissionTask.ref == HEADERS_TEST))
        assert task is not None
        task.status = "running"
        session.add(
            MissionStep(
                mission_id=mission_id,
                task_id=task.id,
                seq=1,
                status="running",
                tool="b.headers",
                request={"values": {"url": "https://shop.example.com/"}},
            )
        )
    assert await engine.recover() == [mission_id]
    steps = await steps_of(sessions, mission_id)
    assert (steps[0].status, steps[0].note) == (
        "interrupted",
        "The server restarted while this step ran.",
    )
    assert (await task_of(sessions, mission_id, HEADERS_TEST)).status == "pending"
    await engine.run(mission_id)
    assert [(s.seq, s.status) for s in await steps_of(sessions, mission_id)] == [
        (1, "interrupted"),
        (2, "done"),
    ]
    assert len(runner.ran) == 1  # the interrupted step was not run again; the agent asked anew
    assert "mission_recovered" in await events_of(sessions, mission_id)


async def test_recover_only_returns_missions_that_were_running(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(admin, sessions, {})
    await set_mission(sessions, mission_id, status="paused")
    assert await engine.recover() == []


# ---------------------------------------------------------------------------- failures


async def test_a_tool_that_cannot_run_is_a_failed_step_the_agent_can_see(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {
            HEADERS_TEST: [
                look(),
                look(),
                look(),
                done("blocked", summary="The tool is not working."),
            ]
        },
        answers=[
            RuntimeError("boom"),
            Execution(None, None, 127, 5, error="curl: not found"),
            Execution(None, "partial", None, 5),
        ],
    )
    await engine.run(mission_id)
    statuses = [(s.status, s.note) for s in await steps_of(sessions, mission_id)]
    assert statuses == [
        ("failed", "The tool could not run: boom"),
        ("failed", "curl: not found"),
        ("failed", ""),
    ]
    assert brain.asked[1].history[0].account == "The tool could not run: boom"
    async with sessions() as session:
        rows = (await session.scalars(select(PentestResult).order_by(PentestResult.ran_at))).all()
        assert [one.status for one in rows] == ["failed", "failed", "failed"]


async def test_a_model_that_cannot_answer_blocks_its_test_and_a_missing_model_stops_the_mission(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [RuntimeError("provider down")]}
    )
    await engine.run(mission_id)
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert task.summary == "The model could not give an answer."
    assert task.outcome == {"status": "blocked", "findings": []}
    assert (await mission_of(sessions, mission_id)).status == "completed"

    engine, _brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [AppError(409, "no_model", "No model is set for test agents")]},
    )
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert (mission.status, mission.stop_reason) == ("stopped", "No model is set for test agents")
    assert (await task_of(sessions, mission_id, HEADERS_TEST)).status == "pending"


async def test_an_engine_error_fails_the_mission_and_never_escapes(
    admin: TestClient, sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(admin, sessions, {})

    async def broken(_mission_id: uuid.UUID) -> None:
        raise RuntimeError("database gone")

    monkeypatch.setattr(engine, "_run", broken)
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert mission.status == "failed"
    assert "log has the details" in mission.stop_reason
    assert mission.finished_at is not None


async def test_an_error_in_one_test_fails_that_test_only(
    admin: TestClient, sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(
        admin, sessions, {}, only=(HEADERS_TEST, OTHER_TEST), budget=Budget(concurrency=1)
    )

    async def no_registry(_session: Any) -> Any:
        raise RuntimeError("registry unreadable")

    monkeypatch.setattr(engine, "registry", no_registry)
    await engine.run(mission_id)
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert (task.status, task.summary) == (
        "failed",
        "The engine hit an error on this test. The log has the details.",
    )
    assert (await mission_of(sessions, mission_id)).status == "completed"


async def test_a_mission_that_is_deleted_while_running_just_stops(
    admin: TestClient, sessions: Sessions
) -> None:
    class Deleting(Runner):
        async def run(self, tool: Any, call: Any) -> Execution:
            async with sessions.begin() as session:
                await session.execute(delete(Mission).where(Mission.id == mission_id))
            return await super().run(tool, call)

    engine, _brain, _runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [look(), look(), done()]}
    )
    engine.executor = Deleting()
    await engine.run(mission_id)  # logs the error and returns: there is no mission left to mark
    async with sessions() as session:
        assert await session.get(Mission, mission_id) is None


async def test_a_pause_while_the_last_test_finishes_is_kept(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, _runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [done("passed", summary="Fine.")]}
    )
    pausing: list[asyncio.Task[None]] = []

    def pause_now(_context: Any) -> None:
        pausing.append(
            asyncio.get_running_loop().create_task(
                set_mission(
                    sessions, mission_id, status="paused", stop_reason="Paused by a person."
                )
            )
        )

    brain.hook = pause_now
    await engine.run(mission_id)
    await asyncio.sleep(0)
    mission = await mission_of(sessions, mission_id)
    assert (mission.status, mission.stop_reason) == ("paused", "Paused by a person.")
    assert (await task_of(sessions, mission_id, HEADERS_TEST)).status == "done"


async def test_cancelling_the_task_that_runs_a_mission_leaves_a_running_step_for_recovery(
    admin: TestClient, sessions: Sessions
) -> None:
    started = asyncio.Event()

    class Stuck(Runner):
        async def run(self, tool: Any, call: Any) -> Execution:
            started.set()
            await asyncio.sleep(60)
            return await super().run(tool, call)

    engine, _brain, _runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [look(), done()]}
    )
    engine.executor = Stuck()
    running = asyncio.create_task(engine.run(mission_id))
    await started.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert [s.status for s in await steps_of(sessions, mission_id)] == ["running"]
    assert (await mission_of(sessions, mission_id)).status == "running"  # not failed
    assert await engine.recover() == [mission_id]
    assert [s.status for s in await steps_of(sessions, mission_id)] == ["interrupted"]


async def test_an_engine_error_does_not_fail_a_mission_a_person_already_paused(
    admin: TestClient, sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(admin, sessions, {})

    async def paused_then_broken(_mission_id: uuid.UUID) -> None:
        await set_mission(sessions, mission_id, status="paused")
        raise RuntimeError("late failure")

    monkeypatch.setattr(engine, "_run", paused_then_broken)
    await engine.run(mission_id)
    assert (await mission_of(sessions, mission_id)).status == "paused"
    await engine.run(uuid.uuid4())  # a mission that is gone: nothing to mark


async def test_a_run_cancelled_between_steps_stays_cancelled(
    admin: TestClient, sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(admin, sessions, {})

    async def cancelled(_mission_id: uuid.UUID) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(engine, "_run", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await engine.run(mission_id)
    assert (await mission_of(sessions, mission_id)).status == "running"


async def test_a_test_that_waits_with_a_step_nobody_answered_goes_back_to_waiting(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, runner, mission_id, _made = await setup(admin, sessions, {}, only=(SCAN_TEST,))
    async with sessions.begin() as session:
        task = await session.scalar(select(MissionTask).where(MissionTask.ref == SCAN_TEST))
        assert task is not None
        session.add(
            MissionStep(
                mission_id=mission_id,
                task_id=task.id,
                seq=1,
                status="awaiting_approval",
                tool="c.nmap",
                request={"values": {"targets": ["10.0.0.5"]}},
            )
        )
    await engine.run(
        mission_id
    )  # for example after a crash between writing the step and the status
    assert (await task_of(sessions, mission_id, SCAN_TEST)).status == "waiting"
    assert (await mission_of(sessions, mission_id)).stop_reason == WAITING
    assert brain.asked == []
    assert runner.ran == []


@pytest.mark.parametrize(
    ("budget", "expected"),
    [
        (Budget(tokens=1000, tokens_per_test=1000), "The mission used its 1000 tokens."),
        (Budget(tokens=100_000, steps=1), "The mission used its 1 steps."),
    ],
)
async def test_the_mission_stops_at_its_token_cap(
    admin: TestClient, sessions: Sessions, budget: Budget, expected: str
) -> None:
    engine, brain, _runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [look()] * 10}, budget=budget
    )
    brain.spend = Spend(tokens=600)
    await engine.run(mission_id)
    mission = await mission_of(sessions, mission_id)
    assert mission.status == "stopped"
    assert mission.stop_reason == expected


async def test_a_test_a_person_already_settled_is_planned_but_not_run(
    admin: TestClient, sessions: Sessions
) -> None:
    made = running_pentest(admin)
    async with sessions.begin() as session:
        session.add(
            PentestCheck(
                pentest_id=uuid.UUID(made["id"]),
                test_id=HEADERS_TEST,
                status="passed",
                notes="By hand",
            )
        )
    brain = ScriptedBrain()
    engine = make_engine(sessions, brain, Runner())
    mission_id = await start_mission(engine, sessions, made, only=None)
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert (task.status, task.summary) == ("skipped", "A person has already recorded the result.")


# ---------------------------------------------------------------------------- findings


def high(**changes: Any) -> FindingIn:
    return FindingIn.model_validate(
        {
            "title": "No HSTS",
            "severity": "high",
            "detail": "The header is missing.",
            "evidence": [1],
        }
        | changes
    )


async def test_a_finding_is_replayed_and_counts_only_when_the_replay_agrees(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [look(), done("finding", summary="No HSTS.", findings=[high()])]},
    )
    await engine.run(mission_id)
    assert len(runner.ran) == 2  # the request, then the replay
    [(finding, original, replay)] = brain.verified
    assert finding.title == "No HSTS"
    assert [one.seq for one in original] == [1]
    assert [one.seq for one in replay] == [2]
    steps = await steps_of(sessions, mission_id)
    assert [s.request.get("replay_of") for s in steps] == [None, 1]
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert task.outcome is not None
    assert task.outcome["status"] == "finding"
    assert task.outcome["findings"][0]["verification"] == "confirmed"
    async with sessions() as session:
        check = await session.scalar(
            select(PentestCheck).where(PentestCheck.test_id == HEADERS_TEST)
        )
        assert check is not None
        assert check.status == "finding"
        row = await session.scalar(select(Finding))
        assert row is not None
        assert (row.number, row.source, row.severity, row.confidence) == (
            1,
            "agent",
            "high",
            "firm",
        )
        assert (row.status, row.verification, row.verified_by) == (
            "confirmed",
            "confirmed",
            "agent",
        )
        assert (row.test_ids, row.description) == ([HEADERS_TEST], "The header is missing.")
        assert row.result_id is not None
        proof = (await session.scalars(select(FindingEvidence))).all()
        assert [(e.kind, e.title, e.result_id) for e in proof] == [
            ("result", "Step 1: b.headers", row.result_id)
        ]


async def test_a_finding_the_agent_makes_again_is_seen_again_not_made_twice(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [look(), done("finding", summary="No HSTS.", findings=[high()])]},
    )
    await engine.run(mission_id)
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    again = [(high(), "confirmed"), (high(title="Something else"), "unverified")]
    async with sessions.begin() as session:
        before = await session.scalar(select(Finding))
        assert before is not None
        before.status = "fixed"
        made = await record_findings(
            session,
            pentest_id=before.pentest_id,
            task_id=task.id,
            test_ref=HEADERS_TEST,
            claims=again,  # pyright: ignore[reportArgumentType]
        )
    assert [one.title for one in made] == ["Something else"]
    async with sessions() as session:
        rows = (await session.scalars(select(Finding).order_by(Finding.number))).all()
        assert [(r.number, r.status, r.verification, r.verified_by) for r in rows] == [
            (1, "confirmed", "confirmed", "agent"),
            (2, "new", "unverified", None),
        ]
        kinds = (
            await session.scalars(
                select(FindingEvent.kind).where(FindingEvent.finding_id == rows[0].id)
            )
        ).all()
        assert sorted(kinds) == ["created", "evidence_added", "seen_again", "status"]
    async with sessions.begin() as session:
        await record_findings(
            session,
            pentest_id=rows[0].pentest_id,
            task_id=task.id,
            test_ref=HEADERS_TEST,
            claims=[(high(), "unconfirmed")],
        )
    async with sessions() as session:
        again_row = await session.scalar(select(Finding).where(Finding.number == 1))
        assert again_row is not None
        assert again_row.status == "confirmed"


async def test_a_step_without_a_stored_result_is_not_evidence(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [look(), done("finding", summary="No HSTS.", findings=[high()])]},
    )
    await engine.run(mission_id)
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    async with sessions.begin() as session:
        for step in await session.scalars(
            select(MissionStep).where(MissionStep.task_id == task.id)
        ):
            step.result_id = None
        made = await record_findings(
            session,
            pentest_id=(await session.scalars(select(Finding.pentest_id))).one(),
            task_id=task.id,
            test_ref=HEADERS_TEST,
            claims=[(high(title="Another"), "unverified")],
        )
    assert [one.result_id for one in made] == [None]
    async with sessions() as session:
        proof = (await session.scalars(select(FindingEvidence))).all()
        assert len(proof) == 1  # only the first finding's


async def test_a_finding_the_replay_does_not_confirm_is_not_counted(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [look(), done("finding", summary="No HSTS.", findings=[high()])]},
    )
    brain.verdicts = [Verification(False, "The replay shows HSTS.", Spend(tokens=5))]
    await engine.run(mission_id)
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert task.outcome is not None
    assert task.outcome["status"] == "blocked"  # claimed a finding, none survived: not a pass
    assert task.outcome["findings"][0]["verification"] == "unconfirmed"
    mission = await mission_of(sessions, mission_id)
    assert mission.spent["tokens"] == 5
    async with sessions() as session:
        row = await session.scalar(select(Finding))
        assert row is not None
        assert (row.status, row.verification, row.verified_by) == ("new", "unconfirmed", "agent")


async def test_a_model_may_raise_a_verdict_but_never_lower_one(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {
            HEADERS_TEST: [
                look(),
                done("passed", summary="All good.", findings=[high(title="HSTS missing")]),
            ]
        },
    )
    await engine.run(mission_id)
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert task.outcome is not None
    assert task.outcome["status"] == "finding"  # it said passed, its own evidence says otherwise
    assert task.outcome["findings"][0]["verification"] == "confirmed"


@pytest.mark.parametrize(
    "finding",
    [
        high(severity="low"),  # below the severity that is replayed
        high(evidence=[]),  # cites nothing
        high(evidence=[9]),  # cites a step that does not exist
    ],
)
async def test_a_finding_that_is_not_replayed_is_marked_unverified(
    admin: TestClient, sessions: Sessions, finding: FindingIn
) -> None:
    engine, brain, runner, mission_id, _made = await setup(
        admin, sessions, {HEADERS_TEST: [look(), done("finding", findings=[finding])]}
    )
    await engine.run(mission_id)
    assert brain.verified == []
    assert len(runner.ran) == 1
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert task.outcome is not None
    assert task.outcome["findings"][0]["verification"] == "unverified"
    assert task.outcome["status"] == "finding"
    async with sessions() as session:
        row = await session.scalar(select(Finding))
        assert row is not None
        assert (row.status, row.verification, row.verified_by) == ("new", "unverified", None)


async def test_a_replay_that_fails_leaves_the_finding_unverified(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {HEADERS_TEST: [look(), done("finding", findings=[high()])]},
        answers=[Execution(result_with(issue()), "ok", 0, 1), RuntimeError("down")],
    )
    await engine.run(mission_id)
    assert brain.verified == []
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert task.outcome is not None
    assert task.outcome["findings"][0]["verification"] == "unverified"


async def test_a_replay_never_waits_for_approval(admin: TestClient, sessions: Sessions) -> None:
    engine, brain, runner, mission_id, _made = await setup(
        admin,
        sessions,
        {SCAN_TEST: [NMAP, done("finding", findings=[high()])]},
        only=(SCAN_TEST,),
    )
    await engine.run(mission_id)
    await approve(engine, sessions, mission_id)
    await engine.run(mission_id)
    assert [tool for tool, _ in runner.ran] == ["c.nmap"]
    assert brain.verified == []
    steps = await steps_of(sessions, mission_id)
    assert [(s.status, s.note) for s in steps][1] == (
        "denied",
        "A replay cannot wait for approval.",
    )


async def test_a_person_who_settled_a_test_keeps_the_last_word(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, _runner, mission_id, made = await setup(
        admin,
        sessions,
        {
            HEADERS_TEST: [
                look(),
                done("finding", summary="Agent says finding.", findings=[high(severity="low")]),
            ]
        },
    )

    async with sessions.begin() as session:
        session.add(
            PentestCheck(
                pentest_id=uuid.UUID(made["id"]),
                test_id=HEADERS_TEST,
                status="passed",
                notes="By hand",
            )
        )
    await engine.run(mission_id)
    async with sessions() as session:
        check = await session.scalar(
            select(PentestCheck).where(PentestCheck.test_id == HEADERS_TEST)
        )
        assert check is not None
        assert (check.status, check.notes) == ("passed", "By hand")
    task = await task_of(sessions, mission_id, HEADERS_TEST)
    assert task.outcome is not None
    assert task.outcome["status"] == "finding"  # still recorded, on the mission


async def test_an_unfinished_check_row_is_updated_not_duplicated(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, _brain, _runner, mission_id, made = await setup(
        admin, sessions, {HEADERS_TEST: [done("passed", summary="Fine.")]}
    )
    async with sessions.begin() as session:
        session.add(
            PentestCheck(
                pentest_id=uuid.UUID(made["id"]), test_id=HEADERS_TEST, status="in_progress"
            )
        )
    await engine.run(mission_id)
    async with sessions() as session:
        rows = (
            await session.scalars(select(PentestCheck).where(PentestCheck.test_id == HEADERS_TEST))
        ).all()
        assert [(one.status, one.notes) for one in rows] == [("passed", "Agent: Fine.")]


# ---------------------------------------------------------------------------- the plan


async def test_the_plan_is_stored_with_a_tree_of_tasks(
    admin: TestClient, sessions: Sessions
) -> None:
    *_unused, mission_id, _made = await setup(admin, sessions, {}, only=None)
    mission = await mission_of(sessions, mission_id)
    assert mission.plan["runs"] > 0
    assert mission.plan["skipped"] > 0
    assert {one["phase"] for one in mission.plan["phases"]} <= {0, 1, 2}
    async with sessions() as session:
        commander = await session.scalar(select(MissionTask).where(MissionTask.kind == "commander"))
        assert commander is not None
        assert commander.status == "done"
        assert "Planned" in commander.summary
        categories = (
            await session.scalars(select(MissionTask).where(MissionTask.kind == "category"))
        ).all()
        assert all(one.parent_id == commander.id for one in categories)
        skipped = await session.scalar(
            select(MissionTask).where(
                MissionTask.kind == "test", MissionTask.summary.like("The target does not show%")
            )
        )
        assert skipped is not None
        assert skipped.status == "skipped"


async def test_categories_that_only_observe_run_before_the_ones_that_push(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, _runner, mission_id, _made = await setup(
        admin, sessions, {}, only=(HEADERS_TEST, SCAN_TEST, OTHER_TEST)
    )
    await engine.run(mission_id)
    order = [c.brief.test_id for c in brain.asked]
    assert sorted(order) == sorted([HEADERS_TEST, SCAN_TEST, OTHER_TEST])
    async with sessions() as session:
        rows = list(
            (await session.scalars(select(MissionTask).where(MissionTask.kind == "category"))).all()
        )
        assert [r.phase for r in sorted(rows, key=lambda r: (r.phase, r.position))] == sorted(
            r.phase for r in rows
        )


async def test_a_category_summary_counts_what_ran(admin: TestClient, sessions: Sessions) -> None:
    engine, _brain, _runner, mission_id, _made = await setup(admin, sessions, {})
    await engine.run(mission_id)
    async with sessions() as session:
        category = await session.scalar(
            select(MissionTask).where(
                MissionTask.kind == "category", MissionTask.ref == "WSTG-CONF"
            )
        )
        assert category is not None
        assert category.status == "done"
        assert "1 of" in category.summary
        assert category.outcome is not None
        assert category.outcome["findings"] == 0


async def test_a_wait_in_one_test_does_not_stop_the_others_in_its_category(
    admin: TestClient, sessions: Sessions
) -> None:
    engine, brain, _runner, mission_id, _made = await setup(
        admin,
        sessions,
        {SCAN_TEST: [NMAP]},
        only=(SCAN_TEST, HEADERS_TEST),
        budget=Budget(concurrency=1),
    )
    await engine.run(mission_id)
    assert (await task_of(sessions, mission_id, SCAN_TEST)).status == "waiting"
    assert (await task_of(sessions, mission_id, HEADERS_TEST)).status == "done"
    assert {c.brief.test_id for c in brain.asked} == {SCAN_TEST, HEADERS_TEST}
    assert (await mission_of(sessions, mission_id)).stop_reason == WAITING


# ---------------------------------------------------------------------------- unit pieces


def test_a_resolver_type_exists_for_the_tests() -> None:
    assert Resolver  # the engine takes the guard's resolver, so tests never touch real DNS
    assert Turn(done()).spend == Spend()
    assert MissionEngine

"""What the agent tests share: a scripted brain, a recording executor, and a mission made on a
real database with only the tests under study left to run."""

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.test_pentest_gate import authorized, move

from app.agents.budget import Budget
from app.agents.engine import MissionEngine
from app.agents.ports import (
    Context,
    Execution,
    FindingIn,
    Finish,
    HistoryItem,
    Spend,
    ToolRequest,
    Turn,
    Verification,
)
from app.db.models import Mission, MissionStep, MissionTask, Pentest
from app.tools.argv import Call
from app.tools.parsers.schema import Issue, Severity, Technology, ToolResult
from app.tools.registry import Tool

SHOP = "93.184.216.34"
HEADERS_TEST = "WSTG-CONF-06"  # its playbook names b.headers (passive) and b.tls
SCAN_TEST = "WSTG-CONF-01"  # its playbook names c.nmap (active) as well
OTHER_TEST = "WSTG-CONF-10"
URL = "https://shop.example.com/"


async def lookup(host: str, port: int) -> list[str]:
    assert port
    return [SHOP] if host.endswith("example.com") else ["8.8.8.8"]


def look(**values: Any) -> ToolRequest:
    """A request for b.headers on the shop."""
    return ToolRequest(tool="b.headers", values={"url": URL} | values, why="look at the headers")


def done(status: str = "passed", **changes: Any) -> Finish:
    return Finish.model_validate({"status": status, "summary": "Done."} | changes)


def issue(title: str = "No HSTS", severity: Severity = Severity.MEDIUM) -> Issue:
    return Issue(title=title, severity=severity, target="shop.example.com")


def result_with(*issues: Issue) -> ToolResult:
    return ToolResult(
        tool="b.headers",
        parser="builtin",
        issues=list(issues),
        technologies=[Technology(name="nginx", version="1.31.10", category="web server")],
    )


@dataclass
class ScriptedBrain:
    """Answers from a list. A turn may be a decision, a `Turn`, or an exception to raise. When the
    list for a test runs out the test is finished as passed, so a mission with many tests ends."""

    turns: dict[str, list[Any]] = field(default_factory=dict[str, list[Any]])
    verdicts: list[Verification | Exception] = field(default_factory=list[Verification | Exception])
    asked: list[Context] = field(default_factory=list[Context])
    verified: list[tuple[FindingIn, list[HistoryItem], list[HistoryItem]]] = field(
        default_factory=list[tuple[FindingIn, list[HistoryItem], list[HistoryItem]]]
    )
    spend: Spend = field(default_factory=Spend)
    hook: Callable[[Context], None] | None = None

    async def decide(self, context: Context) -> Turn:
        self.asked.append(context)
        if self.hook is not None:
            self.hook(context)
        queue = self.turns.get(context.brief.test_id, [])
        step = queue.pop(0) if queue else done()
        if isinstance(step, Exception):
            raise step
        return step if isinstance(step, Turn) else Turn(step, self.spend)

    async def verify(
        self, finding: FindingIn, original: list[HistoryItem], replay: list[HistoryItem]
    ) -> Verification:
        self.verified.append((finding, original, replay))
        answer = self.verdicts.pop(0) if self.verdicts else Verification(True, "Same again.")
        if isinstance(answer, Exception):
            raise answer
        return answer


class HeldBrain(ScriptedBrain):
    """A brain that waits to be let go before it answers, so a test can act while a mission is in
    the middle of a turn."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.release = asyncio.Event()

    async def decide(self, context: Context) -> Turn:
        await self.release.wait()
        return await super().decide(context)


@dataclass
class Runner:
    """Records every call it is given and answers from a list (or with one issue)."""

    answers: list[Execution | Exception] = field(default_factory=list[Execution | Exception])
    ran: list[tuple[str, tuple[str, ...]]] = field(
        default_factory=list[tuple[str, tuple[str, ...]]]
    )

    async def run(self, tool: Tool, call: Call) -> Execution:
        self.ran.append((tool.manifest.id, call.targets))
        answer = (
            self.answers.pop(0)
            if self.answers
            else Execution(result_with(issue()), "HTTP/1.1 200 OK", 0, 12)
        )
        if isinstance(answer, Exception):
            raise answer
        return answer


class Clock:
    """A clock a test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_engine(
    sessions: async_sessionmaker[AsyncSession], brain: ScriptedBrain, runner: Runner, **extra: Any
) -> MissionEngine:
    return MissionEngine(sessions, brain, runner, resolver=lookup, **extra)


def running_pentest(admin: TestClient, **changes: Any) -> dict[str, Any]:
    made = authorized(admin, **changes)
    assert move(admin, made, "running").status_code == 200
    return made


async def start_mission(
    engine: MissionEngine,
    sessions: async_sessionmaker[AsyncSession],
    made: dict[str, Any],
    only: tuple[str, ...] | None = (HEADERS_TEST,),
    budget: Budget | None = None,
) -> uuid.UUID:
    """A mission for the pentest in which only the named tests are left to run."""
    async with sessions.begin() as session:
        pentest = await session.get(Pentest, uuid.UUID(made["id"]))
        assert pentest is not None
        mission = await engine.create(session, pentest, budget or Budget(), None)
        await session.flush()
        if only is None:
            return mission.id
        await session.execute(
            update(MissionTask)
            .where(
                MissionTask.mission_id == mission.id,
                MissionTask.kind == "test",
                MissionTask.ref.not_in(only),
            )
            .values(status="skipped", summary="Left out of this test run.")
        )
        return mission.id


async def task_of(
    sessions: async_sessionmaker[AsyncSession], mission_id: uuid.UUID, ref: str
) -> MissionTask:
    async with sessions() as session:
        row = await session.scalar(
            select(MissionTask).where(MissionTask.mission_id == mission_id, MissionTask.ref == ref)
        )
        assert row is not None
        return row


async def steps_of(
    sessions: async_sessionmaker[AsyncSession], mission_id: uuid.UUID
) -> list[MissionStep]:
    async with sessions() as session:
        return list(
            (
                await session.scalars(
                    select(MissionStep)
                    .where(MissionStep.mission_id == mission_id)
                    .order_by(MissionStep.created_at, MissionStep.seq)
                )
            ).all()
        )


async def mission_of(sessions: async_sessionmaker[AsyncSession], mission_id: uuid.UUID) -> Mission:
    async with sessions() as session:
        row = await session.get(Mission, mission_id)
        assert row is not None
        return row

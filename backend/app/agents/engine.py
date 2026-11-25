"""The mission engine: deterministic orchestration over rows in the database.

What it guarantees, and where:

* Every tool request goes through `authorize` (the scope guard and the permission policy) and the
  tool's own manifest checks, in `_check`, whatever the model said.
* A step is written before it runs and runs once. A finished step is read back, never repeated; a
  step that was running when the server stopped is marked interrupted (`recover`).
* Step, token, cost and time caps, the kill switch, pause and cancel are read from the database
  before every step (`_gate`).
* A finding is replayed by a verifier before it counts as confirmed, and a model can raise a
  test's verdict but never lower one the evidence set (`_conclude`).
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import cast

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.budget import Budget, Spent, mission_exhausted, task_exhausted
from app.agents.plan import SETTLED, plan_mission
from app.agents.ports import (
    Brain,
    Brief,
    Context,
    Execution,
    Executor,
    FactIn,
    FindingIn,
    Finish,
    HistoryItem,
    Spend,
    ToolRequest,
)
from app.agents.store import (
    account_of,
    add_facts,
    charge,
    emit,
    facts_for,
    history_of,
    required,
    spent_of,
)
from app.ai.netguard import Resolver, system_resolver
from app.ai.roles import AgentRole
from app.db.base import utc_now
from app.db.models import (
    CheckStatus,
    Mission,
    MissionStep,
    MissionTask,
    Pentest,
    PentestCheck,
)
from app.errors import AppError
from app.methodology.spec import RiskClass, Test
from app.pentests.checklist import rows_of, snapshot
from app.results.service import Run, record_result, summary_of
from app.tools.argv import Call, build_call
from app.tools.authorize import Verdict, authorize
from app.tools.control import kill_switch_on
from app.tools.params import ToolInputError
from app.tools.parsers.schema import Severity
from app.tools.policy import ApprovalMode
from app.tools.registry import Registry, Tool, load_registry

log = structlog.get_logger()

ROLE = AgentRole.TEST_AGENT.value
SEVERITIES = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
MAX_OUTCOME_FINDINGS = 50
WAITING = "Waiting for a person to approve a step."

Clock = Callable[[], float]
Now = Callable[[], datetime]


class Gate(Enum):
    GO = "go"
    PAUSE = "pause"  # a person paused it, or it waits for one
    CANCEL = "cancel"
    STOP = "stop"  # a cap or the kill switch


@dataclass(frozen=True)
class Gated:
    gate: Gate
    reason: str = ""


@dataclass(frozen=True)
class Assignment:
    """What one test agent's loop carries from turn to turn."""

    mission_id: uuid.UUID
    task_id: uuid.UUID
    test: Test
    budget: Budget
    registry: Registry
    base_seconds: float
    started: float


@dataclass(frozen=True)
class Checked:
    """What the engine decided about a request before anything runs."""

    tool: Tool | None
    call: Call | None
    verdict: Verdict | None
    refusal: str | None


class MissionEngine:
    """Runs missions. `brain` decides what each test agent does next; `executor` runs the tools the
    engine allows."""

    def __init__(  # the engine's collaborators, each swapped in tests
        self,
        sessions: async_sessionmaker[AsyncSession],
        brain: Brain,
        executor: Executor,
        *,
        resolver: Resolver = system_resolver,
        now: Now = utc_now,
        clock: Clock = time.monotonic,
        registry: Callable[[AsyncSession], Awaitable[Registry]] = load_registry,
    ) -> None:
        self.sessions = sessions
        self.brain = brain
        self.executor = executor
        self.resolver = resolver
        self.now = now
        self.clock = clock
        self.registry = registry
        self._segments: dict[uuid.UUID, tuple[float, float]] = {}

    # ------------------------------------------------------------------ making a mission

    async def create(
        self, session: AsyncSession, pentest: Pentest, budget: Budget, created_by: uuid.UUID | None
    ) -> Mission:
        """Plan a mission for the pentest and store it, ready to run."""
        spec = await snapshot(session, pentest)
        checks = await rows_of(session, pentest.id)
        plan = plan_mission(
            spec, checks, list(pentest.features), RiskClass(pentest.rules["max_risk"])
        )
        runs = sum(1 for one in plan for p in one.tests if p.skip is None)
        skipped = sum(1 for one in plan for p in one.tests if p.skip is not None)
        mission = Mission(
            pentest_id=pentest.id,
            status="running",
            budget=budget.model_dump(),
            plan={
                "phases": [
                    {"category": one.id, "phase": one.phase, "tests": len(one.tests)}
                    for one in plan
                ],
                "runs": runs,
                "skipped": skipped,
            },
            started_at=self.now(),
            created_by=created_by,
        )
        session.add(mission)
        await session.flush()
        commander = MissionTask(
            mission_id=mission.id,
            kind="commander",
            ref="commander",
            name="Mission Commander",
            status="done",
            summary=(
                f"Planned {runs} tests in {len(plan)} categories; {skipped} will not run. "
                "Categories that only observe go first, then active ones, then intrusive ones."
            ),
        )
        session.add(commander)
        await session.flush()
        for index, category in enumerate(plan):
            row = MissionTask(
                mission_id=mission.id,
                parent_id=commander.id,
                kind="category",
                ref=category.id,
                name=category.name,
                phase=category.phase,
                position=index,
            )
            session.add(row)
            await session.flush()
            for number, planned in enumerate(category.tests):
                session.add(
                    MissionTask(
                        mission_id=mission.id,
                        parent_id=row.id,
                        kind="test",
                        ref=planned.test.id,
                        name=planned.test.name,
                        phase=category.phase,
                        position=number,
                        status="skipped" if planned.skip else "pending",
                        summary=planned.skip or "",
                    )
                )
        emit(session, mission.id, "mission_started", runs=runs, skipped=skipped)
        return mission

    # ------------------------------------------------------------------ control

    def pause(self, session: AsyncSession, mission: Mission, reason: str = "") -> None:
        if mission.status == "running":
            mission.status = "paused"
            mission.stop_reason = reason
            emit(session, mission.id, "mission_paused", reason=reason)

    def resume(self, session: AsyncSession, mission: Mission) -> None:
        if mission.status in ("paused", "stopped"):
            mission.status = "running"
            mission.stop_reason = ""
            emit(session, mission.id, "mission_resumed")

    def cancel(self, session: AsyncSession, mission: Mission) -> None:
        if mission.status in ("running", "paused", "stopped", "pending"):
            mission.status = "cancelling"
            emit(session, mission.id, "mission_cancelling")

    async def recover(self) -> list[uuid.UUID]:
        """After a restart: a step that was running is marked interrupted (it is never run again by
        the engine; the agent may ask for it again, visibly), tasks that were running go back to
        pending, and the ids of the missions that should carry on are returned."""
        async with self.sessions.begin() as session:
            await session.execute(
                update(MissionStep)
                .where(MissionStep.status == "running")
                .values(status="interrupted", note="The server restarted while this step ran.")
            )
            await session.execute(
                update(MissionTask).where(MissionTask.status == "running").values(status="pending")
            )
            running = (
                await session.scalars(select(Mission.id).where(Mission.status == "running"))
            ).all()
            for mission_id in running:
                emit(session, mission_id, "mission_recovered")
            return list(running)

    # ------------------------------------------------------------------ running

    async def run(self, mission_id: uuid.UUID) -> None:
        """Work through the mission until it is done, paused, cancelled or stopped."""
        try:
            await self._run(mission_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("mission_failed", mission=str(mission_id))
            async with self.sessions.begin() as session:
                mission = await session.get(Mission, mission_id)
                if mission is not None and mission.status == "running":
                    mission.status = "failed"
                    mission.stop_reason = "The engine hit an error. The log has the details."
                    mission.finished_at = self.now()
                    emit(session, mission_id, "mission_failed")

    async def _run(self, mission_id: uuid.UUID) -> None:
        async with self.sessions.begin() as session:
            mission = await session.get(Mission, mission_id)
            if mission is not None and mission.status == "cancelling":
                await self.finish_cancel(session, mission)
            if mission is None or mission.status != "running":
                return
            self._segments[mission_id] = (self.clock(), spent_of(mission.spent).seconds)
        while True:
            async with self.sessions.begin() as session:
                category = await session.scalar(
                    select(MissionTask)
                    .where(
                        MissionTask.mission_id == mission_id,
                        MissionTask.kind == "category",
                        MissionTask.status.in_(("pending", "running")),
                    )
                    .order_by(MissionTask.phase, MissionTask.position)
                    .limit(1)
                )
                if category is None:
                    break
                category.status = "running"
                category_id = category.id
            gated = await self._run_category(mission_id, category_id)
            if gated.gate is not Gate.GO:
                await self._settle(mission_id, gated)
                return
        await self._complete(mission_id)

    async def _settle(self, mission_id: uuid.UUID, gated: Gated) -> None:
        """Record why a mission stopped going on."""
        async with self.sessions.begin() as session:
            mission = await required(session, Mission, mission_id)
            self._save_seconds(mission)
            if gated.gate is Gate.CANCEL:
                await self.finish_cancel(session, mission)
            elif gated.gate is Gate.PAUSE and gated.reason == WAITING:
                self.pause(session, mission, WAITING)
            elif gated.gate is Gate.STOP and mission.status == "running":
                mission.status = "stopped"
                mission.stop_reason = gated.reason
                emit(session, mission_id, "mission_stopped", reason=gated.reason)

    async def finish_cancel(self, session: AsyncSession, mission: Mission) -> None:
        """Mark what has not run as cancelled and close the mission."""
        await session.execute(
            update(MissionTask)
            .where(
                MissionTask.mission_id == mission.id,
                MissionTask.status.in_(("pending", "running", "waiting")),
            )
            .values(status="cancelled")
        )
        mission.status = "cancelled"
        mission.finished_at = self.now()
        emit(session, mission.id, "mission_cancelled")

    async def _complete(self, mission_id: uuid.UUID) -> None:
        async with self.sessions.begin() as session:
            mission = await required(session, Mission, mission_id)
            if mission.status != "running":
                return  # a person paused or cancelled it while the last test finished
            self._save_seconds(mission)
            mission.status = "completed"
            mission.finished_at = self.now()
            emit(session, mission_id, "mission_completed", **mission.spent)

    def _save_seconds(self, mission: Mission) -> None:
        mission.spent = (
            spent_of(mission.spent)
            .model_copy(
                update={"seconds": self._elapsed(mission.id, spent_of(mission.spent).seconds)}
            )
            .model_dump()
        )

    def _elapsed(self, mission_id: uuid.UUID, stored: float) -> float:
        started, base = self._segments.get(mission_id, (self.clock(), stored))
        return round(base + (self.clock() - started), 3)

    async def _gate(self, mission_id: uuid.UUID) -> Gated:
        """May the mission take another step? Read fresh from the database every time."""
        async with self.sessions.begin() as session:
            mission = await required(session, Mission, mission_id)
            if mission.status in ("cancelling", "cancelled"):
                return Gated(Gate.CANCEL)
            if mission.status != "running":
                return Gated(Gate.PAUSE, mission.stop_reason)
            if await kill_switch_on(session):
                return Gated(Gate.STOP, "Every tool is switched off (the kill switch).")
            spent = spent_of(mission.spent)
            spent = spent.model_copy(update={"seconds": self._elapsed(mission_id, spent.seconds)})
            reason = mission_exhausted(Budget.model_validate(mission.budget), spent)
            return Gated(Gate.STOP, reason) if reason else Gated(Gate.GO)

    async def _run_category(self, mission_id: uuid.UUID, category_id: uuid.UUID) -> Gated:
        """The category agent: runs its tests side by side up to the mission's limit, then merges
        what they found into the category's summary."""
        async with self.sessions.begin() as session:
            mission = await required(session, Mission, mission_id)
            limit = Budget.model_validate(mission.budget).concurrency
            ids = (
                await session.scalars(
                    select(MissionTask.id)
                    .where(MissionTask.parent_id == category_id, MissionTask.status == "pending")
                    .order_by(MissionTask.position)
                )
            ).all()
        gate = asyncio.Semaphore(limit)

        async def one(task_id: uuid.UUID) -> Gated:
            async with gate:
                return await self._run_test(mission_id, task_id)

        async with asyncio.TaskGroup() as group:
            running = [group.create_task(one(task_id)) for task_id in ids]
        stops = [r.result() for r in running if r.result().gate is not Gate.GO]
        if stops:
            return stops[0]
        return await self._close_category(mission_id, category_id)

    async def _close_category(self, mission_id: uuid.UUID, category_id: uuid.UUID) -> Gated:
        async with self.sessions.begin() as session:
            category = await required(session, MissionTask, category_id)
            tests = (
                await session.scalars(
                    select(MissionTask).where(MissionTask.parent_id == category_id)
                )
            ).all()
            counts: dict[str, int] = {}
            for one in tests:
                counts[one.status] = counts.get(one.status, 0) + 1
            if counts.get("waiting"):
                category.status = "pending"  # picked up again after the approval
                return Gated(Gate.PAUSE, WAITING)
            findings = sum(_findings_in(one) for one in tests)
            ran = len(tests) - counts.get("skipped", 0)
            category.status = "done"
            category.outcome = {"counts": counts, "findings": findings}
            category.summary = (
                f"{ran} of {len(tests)} tests ran: "
                + ", ".join(f"{n} {name}" for name, n in sorted(counts.items()))
                + f". {findings} findings."
            )
            emit(session, mission_id, "category_done", category_id, counts=counts)
        return Gated(Gate.GO)

    # ------------------------------------------------------------------ one test

    async def _run_test(self, mission_id: uuid.UUID, task_id: uuid.UUID) -> Gated:
        """The test agent's loop. Never raises: an unexpected error fails only this test."""
        try:
            return await self._test_loop(mission_id, task_id)
        except Exception:
            log.exception("test_failed", task=str(task_id))
            async with self.sessions.begin() as session:
                task = await required(session, MissionTask, task_id)
                task.status = "failed"
                task.summary = "The engine hit an error on this test. The log has the details."
                emit(session, mission_id, "test_failed", task_id)
            return Gated(Gate.GO)

    async def _test_loop(self, mission_id: uuid.UUID, task_id: uuid.UUID) -> Gated:
        started = self.clock()
        async with self.sessions.begin() as session:
            task = await required(session, MissionTask, task_id)
            mission = await required(session, Mission, mission_id)
            pentest = await required(session, Pentest, mission.pentest_id)
            found = (await snapshot(session, pentest)).find(task.ref)
            if found is None:
                task.status = "failed"
                task.summary = "The test is not in the methodology snapshot."
                return Gated(Gate.GO)
            run = Assignment(
                mission_id=mission_id,
                task_id=task_id,
                test=found[1],
                budget=Budget.model_validate(mission.budget),
                registry=await self.registry(session),
                base_seconds=spent_of(task.spent).seconds,
                started=started,
            )
            task.status = "running"
            emit(session, mission_id, "test_started", task_id, test=task.ref)
        while (ended := await self._advance(run)) is None:
            continue
        return ended

    async def _advance(self, run: Assignment) -> Gated | None:
        """One turn of the test agent's loop. Returns how the test ended, or None to go on."""
        gated = await self._gate(run.mission_id)
        if gated.gate is not Gate.GO:
            await self._park(run.task_id)
            return gated
        async with self.sessions.begin() as session:
            task = await required(session, MissionTask, run.task_id)
            seconds = round(run.base_seconds + (self.clock() - run.started), 3)
            task.spent = spent_of(task.spent).model_copy(update={"seconds": seconds}).model_dump()
            spent = spent_of(task.spent)
            steps = (
                await session.scalars(
                    select(MissionStep)
                    .where(MissionStep.task_id == run.task_id)
                    .order_by(MissionStep.seq)
                )
            ).all()
            approved = next((s.id for s in steps if s.status == "approved"), None)
            waiting = any(s.status == "awaiting_approval" for s in steps)
            next_seq = max((s.seq for s in steps), default=0) + 1
        if waiting:
            await self._set_status(run.task_id, "waiting")
            return Gated(Gate.GO)
        if approved is not None:
            await self._execute_approved(run, approved)
            return None
        exhausted = task_exhausted(run.budget, spent)
        if exhausted:
            await self._conclude(run, Finish(status="blocked", summary=f"Stopped: {exhausted}"))
            return Gated(Gate.GO)
        return await self._decide(run, spent, next_seq)

    async def _decide(self, run: Assignment, spent: Spent, next_seq: int) -> Gated | None:
        """Ask the brain what to do next and do it."""
        context = await self._context(run, spent)
        try:
            turn = await self.brain.decide(context)
        except AppError as error:
            await self._park(run.task_id)
            return Gated(Gate.STOP, error.title)
        except Exception:
            log.exception("brain_failed", task=str(run.task_id))
            await self._conclude(
                run, Finish(status="blocked", summary="The model could not give an answer.")
            )
            return Gated(Gate.GO)
        await self._pay(run.mission_id, run.task_id, turn.spend)
        if isinstance(turn.decision, Finish):
            await self._conclude(run, turn.decision)
            return Gated(Gate.GO)
        outcome = await self._request(run, next_seq, turn.decision)
        if outcome == "waiting":
            await self._set_status(run.task_id, "waiting")
            return Gated(Gate.GO)
        return None

    async def _park(self, task_id: uuid.UUID) -> None:
        """Leave a test that was stopped from outside ready to carry on."""
        async with self.sessions.begin() as session:
            task = await required(session, MissionTask, task_id)
            task.status = "pending"

    async def _set_status(self, task_id: uuid.UUID, status: str) -> None:
        async with self.sessions.begin() as session:
            task = await required(session, MissionTask, task_id)
            task.status = status

    async def _pay(self, mission_id: uuid.UUID, task_id: uuid.UUID, spend: Spend) -> None:
        async with self.sessions.begin() as session:
            mission = await required(session, Mission, mission_id)
            task = await required(session, MissionTask, task_id)
            for row in (mission, task):
                charge(row, tokens=spend.tokens, cost=spend.cost_usd)

    async def _context(self, run: Assignment, spent: Spent) -> Context:
        async with self.sessions.begin() as session:
            mission = await required(session, Mission, run.mission_id)
            pentest = await required(session, Pentest, mission.pentest_id)
            test = run.test
            history = await history_of(session, run.task_id)
            facts = await facts_for(
                session, run.mission_id, " ".join([test.name, *test.objectives[:3]])
            )
        playbook = test.playbook
        return Context(
            mission_id=str(run.mission_id),
            pentest_name=pentest.name,
            box=pentest.box,
            in_scope=list(pentest.scope.get("in_scope", [])),
            max_risk=pentest.rules["max_risk"],
            brief=Brief(
                test_id=test.id,
                name=test.name,
                risk_class=test.risk_class.value,
                objectives=list(test.objectives),
                instructions=playbook.instructions,
                safe_steps=list(playbook.safe_steps),
                active_steps=list(playbook.active_steps),
                intrusive_steps=list(playbook.intrusive_steps),
                evidence_wanted=list(playbook.evidence),
                success=playbook.success,
                failure=playbook.failure,
            ),
            tools={
                tool.manifest.id: tool.manifest.explain
                for name in playbook.tools
                if (tool := run.registry.get(name)) is not None
            },
            history=history,
            facts=facts,
            steps_left=run.budget.steps_per_test - spent.steps,
        )

    # ------------------------------------------------------------------ one step

    async def _check(
        self,
        session: AsyncSession,
        pentest: Pentest,
        run: Assignment,
        tool_id: str,
        values: Mapping[str, object],
    ) -> Checked:
        """The deterministic part: the tool must be one the test names and one that exists, the
        values must fit its manifest, and `authorize` must agree. Nothing a model wrote is read
        here except the tool id and the values, and both are checked."""
        tool = run.registry.get(tool_id)
        if tool is None or tool_id not in run.test.playbook.tools:
            return Checked(None, None, None, f"{tool_id} is not a tool this test may use.")
        try:
            call = build_call(tool.manifest, dict(values))
        except ToolInputError as error:
            return Checked(tool, None, None, str(error))
        verdict = await authorize(session, pentest, ROLE, tool, call, resolver=self.resolver)
        refusal = verdict.reason if verdict.mode is ApprovalMode.DENY else None
        return Checked(tool, call, verdict, refusal)

    def _refuse(
        self,
        session: AsyncSession,
        step: MissionStep,
        mission: Mission,
        task: MissionTask,
        *,
        reason: str,
    ) -> str:
        step.status = "denied"
        step.note = reason
        charge(mission, steps=1)
        charge(task, steps=1)
        emit(session, mission.id, "step_denied", task.id, seq=step.seq, reason=reason)
        return "denied"

    async def _request(
        self, run: Assignment, seq: int, request: ToolRequest, *, replay_of: int | None = None
    ) -> str:
        """Check a request and, when it passes, run it once. Returns `done`, `denied`, `failed` or
        `waiting` (a person must approve it first)."""
        async with self.sessions.begin() as session:
            mission = await required(session, Mission, run.mission_id)
            task = await required(session, MissionTask, run.task_id)
            pentest = await required(session, Pentest, mission.pentest_id)
            step = MissionStep(
                mission_id=run.mission_id,
                task_id=run.task_id,
                seq=seq,
                status="planned",
                tool=request.tool[:32],
                request={"values": request.values, "why": request.why, "replay_of": replay_of},
            )
            session.add(step)
            await session.flush()
            checked = await self._check(session, pentest, run, request.tool, request.values)
            step.verdict = checked.verdict.record() if checked.verdict else None
            if checked.tool is None or checked.call is None or checked.verdict is None:
                return self._refuse(
                    session, step, mission, task, reason=checked.refusal or "Refused."
                )
            if checked.refusal is not None:
                return self._refuse(session, step, mission, task, reason=checked.refusal)
            if checked.verdict.mode is ApprovalMode.ASK:
                if replay_of is not None:
                    return self._refuse(
                        session, step, mission, task, reason="A replay cannot wait for approval."
                    )
                step.status = "awaiting_approval"
                step.note = checked.verdict.reason
                emit(session, run.mission_id, "approval_needed", run.task_id, seq=seq)
                return "waiting"
            await self._claim(session, step.id, ("planned",))
            tool, call, step_id = checked.tool, checked.call, step.id
            emit(session, run.mission_id, "step_started", run.task_id, seq=seq, tool=request.tool)
        return await self._run_step(run, step_id, seq, tool, call)

    async def _claim(
        self, session: AsyncSession, step_id: uuid.UUID, from_: tuple[str, ...]
    ) -> None:
        """Mark the step running. A step is only ever claimed once: this writes the claim in the
        same transaction that decided to run it, and a step that is not in `from_` is not changed
        (the engine reads the steps of a test one loop at a time, so nothing else claims it)."""
        await session.execute(
            update(MissionStep)
            .where(MissionStep.id == step_id, MissionStep.status.in_(from_))
            .values(status="running")
        )

    async def _run_step(
        self, run: Assignment, step_id: uuid.UUID, seq: int, tool: Tool, call: Call
    ) -> str:
        started = self.clock()
        try:
            execution = await self.executor.run(tool, call)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.exception("tool_failed", tool=tool.manifest.id)
            execution = Execution(None, None, None, 0, error=f"The tool could not run: {error}")
        failed = execution.error is not None or execution.result is None
        status = "failed" if failed else "done"
        async with self.sessions.begin() as session:
            mission = await required(session, Mission, run.mission_id)
            task = await required(session, MissionTask, run.task_id)
            step = await required(session, MissionStep, step_id)
            row = record_result(
                session,
                mission.pentest_id,
                source="tool",
                title=f"{tool.manifest.name} (mission step {seq})",
                status="failed" if failed else "ok",
                result=execution.result,
                raw=execution.raw if execution.raw is not None else execution.error,
                run=Run(
                    tool_id=tool.manifest.id,
                    agent_role=ROLE,
                    test_id=task.ref,
                    command=list(call.argv),
                    exit_code=execution.exit_code,
                    duration_ms=execution.duration_ms or int((self.clock() - started) * 1000),
                ),
            )
            await session.flush()
            step.result_id = row.id
            step.status = status
            step.note = execution.error or ""
            charge(mission, steps=1)
            charge(task, steps=1)
            lines = [] if failed else summary_of(row).summary
            if lines:
                add_facts(
                    session,
                    run.mission_id,
                    run.task_id,
                    [_fact_of(tool.manifest.id, call, lines)],
                    source=row.id,
                )
            emit(
                session,
                run.mission_id,
                "step_done",
                run.task_id,
                seq=seq,
                tool=tool.manifest.id,
                status=status,
            )
        return status

    async def _execute_approved(self, run: Assignment, step_id: uuid.UUID) -> None:
        """Run a step a person approved. It is checked again: an approval never skips the scope
        guard, and the kill switch and a changed policy still apply."""
        async with self.sessions.begin() as session:
            mission = await required(session, Mission, run.mission_id)
            step = await required(session, MissionStep, step_id)
            task = await required(session, MissionTask, run.task_id)
            pentest = await required(session, Pentest, mission.pentest_id)
            checked = await self._check(
                session, pentest, run, step.tool, dict(step.request["values"])
            )
            if checked.tool is None or checked.call is None or checked.refusal is not None:
                self._refuse(session, step, mission, task, reason=checked.refusal or "Refused.")
                return
            await self._claim(session, step_id, ("approved",))
            tool, call, seq = checked.tool, checked.call, step.seq
            emit(session, run.mission_id, "step_started", run.task_id, seq=seq, tool=step.tool)
        await self._run_step(run, step_id, seq, tool, call)

    # ------------------------------------------------------------------ finishing a test

    async def _conclude(self, run: Assignment, finish: Finish) -> None:
        """Check the agent's answer against the evidence, replay what needs it, record the verdict
        on the checklist, and keep the facts."""
        findings: list[dict[str, object]] = []
        for finding in finish.findings[:MAX_OUTCOME_FINDINGS]:
            verification = await self._verify(run, finding)
            findings.append({**finding.model_dump(mode="json"), "verification": verification})
        confirmed = [f for f in findings if f["verification"] != "unconfirmed"]
        # A model may raise a test's verdict, never lower one the evidence set.
        status = "finding" if confirmed else finish.status
        if status == "finding" and not confirmed:
            status = "blocked"
        async with self.sessions.begin() as session:
            task = await required(session, MissionTask, run.task_id)
            mission = await required(session, Mission, run.mission_id)
            task.status = "done"
            task.summary = finish.summary
            task.outcome = {"status": status, "findings": findings}
            add_facts(session, run.mission_id, run.task_id, finish.facts)
            await self._write_check(session, mission.pentest_id, task.ref, status, finish.summary)
            emit(
                session,
                run.mission_id,
                "test_done",
                run.task_id,
                test=run.test.id,
                status=status,
                findings=len(findings),
            )

    async def _write_check(
        self, session: AsyncSession, pentest_id: uuid.UUID, test_id: str, status: str, summary: str
    ) -> None:
        """Put the result on the checklist, unless a person already settled this test."""
        row = await session.scalar(
            select(PentestCheck).where(
                PentestCheck.pentest_id == pentest_id, PentestCheck.test_id == test_id
            )
        )
        if row is not None and row.status in SETTLED:
            return
        note = f"Agent: {summary}"[:4000]
        if row is None:
            session.add(
                PentestCheck(pentest_id=pentest_id, test_id=test_id, status=status, notes=note)
            )
        else:
            row.status = CheckStatus(status).value
            row.notes = note

    async def _verify(self, run: Assignment, finding: FindingIn) -> str:
        """`confirmed`, `unconfirmed` or `unverified` (below the severity that is replayed, or the
        evidence cannot be replayed). The replay is an ordinary step: it passes the same checks."""
        if SEVERITIES.index(finding.severity) < SEVERITIES.index(Severity(run.budget.verify_from)):
            return "unverified"
        async with self.sessions.begin() as session:
            done = {
                one.seq: one
                for one in (
                    await session.scalars(
                        select(MissionStep).where(
                            MissionStep.task_id == run.task_id, MissionStep.status == "done"
                        )
                    )
                ).all()
            }
            cited = next((done[n] for n in finding.evidence if n in done), None)
            if cited is None:
                return "unverified"
            original = [
                HistoryItem(cited.seq, cited.tool, cited.status, await account_of(session, cited))
            ]
            replay = ToolRequest(
                tool=cited.tool, values=dict(cited.request["values"]), why="replay"
            )
            highest = await session.scalar(
                select(func.max(MissionStep.seq)).where(MissionStep.task_id == run.task_id)
            )
            seq = (highest or 0) + 1
        if await self._request(run, seq, replay, replay_of=cited.seq) != "done":
            return "unverified"
        async with self.sessions.begin() as session:
            again = await session.scalars(
                select(MissionStep).where(
                    MissionStep.task_id == run.task_id, MissionStep.seq == seq
                )
            )
            replayed = [
                HistoryItem(one.seq, one.tool, one.status, await account_of(session, one))
                for one in again
            ]
        verdict = await self.brain.verify(finding, original, replayed)
        await self._pay(run.mission_id, run.task_id, verdict.spend)
        return "confirmed" if verdict.confirmed else "unconfirmed"


def _findings_in(task: MissionTask) -> int:
    outcome = cast("dict[str, object]", task.outcome or {})
    found = outcome.get("findings")
    return len(cast("list[object]", found)) if isinstance(found, list) else 0


def _fact_of(tool_id: str, call: Call, lines: list[str]) -> FactIn:
    target = ", ".join(call.targets)[:100] or "the target"
    return FactIn(subject=f"{tool_id} on {target}", fact=" ".join(lines)[:1900], confidence="high")

"""Missions: the agent runs of a pentest. Anyone signed in can watch; starting, pausing, resuming,
cancelling and approving a step need an administrator.

A mission only starts when the pentest is running (an administrator has attested to the scope),
and every step it takes goes through the same checks as a tool run by hand. Nothing here lets a
person or a model skip them: an approval lets one checked step go ahead, and the engine checks it
again before it runs.
"""

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, BackgroundTasks, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.engine import WAITING, plan_for
from app.agents.plan import summarize
from app.agents.schemas import (
    EventOut,
    EventPage,
    MissionDetail,
    MissionList,
    MissionOut,
    PreviewOut,
    ResumeIn,
    StartIn,
    StepList,
    StepOut,
    TaskOut,
)
from app.agents.settings import active_versions, default_budget, preset_named, with_changes
from app.agents.store import emit, required
from app.agents.supervisor import MissionSupervisor
from app.auth import audit
from app.auth.deps import Admin, SignedIn
from app.db.models import Mission, MissionEvent, MissionStep, MissionTask, Pentest, PentestStatus
from app.db.session import SessionDep
from app.errors import AppError
from app.pentests.service import ensure_editable, find

router = APIRouter(prefix="/api", tags=["missions"])

LIVE = ("pending", "running", "paused", "cancelling", "stopped")
MAX_EVENTS = 500


def _runner(request: Request) -> MissionSupervisor:
    """The supervisor that runs missions. There is none until a tool runner is connected."""
    runner = cast("MissionSupervisor | None", request.app.state.missions)
    if runner is None:
        raise AppError(
            409,
            "no_runner",
            "Agents cannot run yet",
            "No tool runner is connected to this server, so a mission has nothing to run its "
            "tools with.",
        )
    return runner


async def _mission(session: AsyncSession, pentest_id: uuid.UUID, mission_id: uuid.UUID) -> Mission:
    row = await session.get(Mission, mission_id)
    if row is None or row.pentest_id != pentest_id:
        raise AppError(404, "mission_not_found", "There is no such mission")
    return row


async def _step(session: AsyncSession, mission: Mission, step_id: uuid.UUID) -> MissionStep:
    row = await session.get(MissionStep, step_id)
    if row is None or row.mission_id != mission.id:
        raise AppError(404, "step_not_found", "There is no such step")
    if row.status != "awaiting_approval":
        raise AppError(409, "not_waiting", "This step is not waiting for approval")
    return row


async def _preview_of(
    session: AsyncSession, pentest: Pentest, body: StartIn, *, runner_ready: bool
) -> PreviewOut:
    """Resolve the caps and the limit a start asks for, and plan against them."""
    chosen = preset_named(body.preset) if body.preset else None
    if body.preset and chosen is None:
        raise AppError(422, "unknown_preset", "There is no such preset")
    budget = body.budget
    if budget is None:
        base = await default_budget(session)
        budget = with_changes(base, chosen.changes) if chosen else base
    plan, limit = await plan_for(
        session,
        pentest,
        max_risk=body.max_risk or (chosen.max_risk if chosen else None),
        only=frozenset(body.only) if body.only else None,
    )
    return PreviewOut(
        summary=summarize(plan),
        budget=budget,
        max_risk=limit,
        prompts=await active_versions(session),
        in_scope=list(pentest.scope.get("in_scope", [])),
        runner_ready=runner_ready,
    )


async def _startable(session: AsyncSession, pentest_id: uuid.UUID) -> Pentest:
    pentest = await find(session, pentest_id)
    ensure_editable(pentest)
    if pentest.status != PentestStatus.RUNNING.value:
        raise AppError(
            409,
            "pentest_not_running",
            "The pentest is not running",
            "Authorize and start the pentest first. Agents only work on a running pentest.",
        )
    return pentest


@router.post("/pentests/{pentest_id}/missions/preview")
async def preview_mission(
    pentest_id: uuid.UUID, body: StartIn, request: Request, _who: Admin, session: SessionDep
) -> PreviewOut:
    """What a start with these choices would run, skip and cost at most, before anyone confirms."""
    pentest = await _startable(session, pentest_id)
    return await _preview_of(
        session, pentest, body, runner_ready=request.app.state.missions is not None
    )


@router.post("/pentests/{pentest_id}/missions", status_code=201)
async def start_mission(
    pentest_id: uuid.UUID,
    *,
    body: StartIn,
    request: Request,
    background: BackgroundTasks,
    who: Admin,
    session: SessionDep,
) -> MissionOut:
    """Plan the pentest's tests and start the agents on them."""
    runner = _runner(request)
    pentest = await _startable(session, pentest_id)
    if not body.confirmed:
        raise AppError(
            422,
            "confirm_required",
            "Confirm the scope first",
            "Starting agents means testing everything in scope. Confirm that it is authorized.",
        )
    live = await session.scalar(
        select(Mission.id).where(Mission.pentest_id == pentest_id, Mission.status.in_(LIVE))
    )
    if live is not None:
        raise AppError(
            409,
            "mission_active",
            "This pentest already has a mission in progress",
            "Cancel it, or wait for it to finish, before starting another.",
        )
    preview = await _preview_of(session, pentest, body, runner_ready=True)
    mission = await runner.engine.create(
        session,
        pentest,
        preview.budget,
        who.user.id,
        prompts=preview.prompts,
        max_risk=preview.max_risk,
        only=frozenset(body.only) if body.only else None,
    )
    audit.record(
        session,
        request,
        "mission.start",
        actor=who.user,
        target=("mission", mission.id),
        detail={"pentest": str(pentest_id), **mission.plan},
    )
    background.add_task(runner.launch_after_response, mission.id)  # after the request has committed
    return MissionOut.of(mission)


@router.get("/pentests/{pentest_id}/missions")
async def list_missions(pentest_id: uuid.UUID, _who: SignedIn, session: SessionDep) -> MissionList:
    """The pentest's missions, newest first."""
    await find(session, pentest_id)
    rows = await session.scalars(
        select(Mission)
        .where(Mission.pentest_id == pentest_id)
        .order_by(Mission.created_at.desc(), Mission.id.desc())
    )
    return MissionList(missions=[MissionOut.of(one) for one in rows])


@router.get("/pentests/{pentest_id}/missions/{mission_id}")
async def get_mission(
    pentest_id: uuid.UUID, mission_id: uuid.UUID, _who: SignedIn, session: SessionDep
) -> MissionDetail:
    """A mission with its tree of tasks (the commander, the categories and their tests)."""
    await find(session, pentest_id)
    mission = await _mission(session, pentest_id, mission_id)
    tasks = await session.scalars(
        select(MissionTask)
        .where(MissionTask.mission_id == mission_id)
        .order_by(MissionTask.phase, MissionTask.position, MissionTask.created_at)
    )
    return MissionDetail(mission=MissionOut.of(mission), tasks=[TaskOut.of(t) for t in tasks])


@router.get("/pentests/{pentest_id}/missions/{mission_id}/steps")
async def list_steps(  # the filters of one page
    pentest_id: uuid.UUID,
    mission_id: uuid.UUID,
    _who: SignedIn,
    session: SessionDep,
    *,
    task: uuid.UUID | None = None,
    status: Annotated[str | None, Query(max_length=18)] = None,
) -> StepList:
    """The steps of a mission: what each agent asked for, what the checks said, and how it ended.
    `status=awaiting_approval` lists what is waiting for a person."""
    await find(session, pentest_id)
    await _mission(session, pentest_id, mission_id)
    query = select(MissionStep).where(MissionStep.mission_id == mission_id)
    if task is not None:
        query = query.where(MissionStep.task_id == task)
    if status:
        query = query.where(MissionStep.status == status)
    rows = await session.scalars(query.order_by(MissionStep.created_at, MissionStep.seq))
    return StepList(steps=[StepOut.of(one) for one in rows])


@router.get("/pentests/{pentest_id}/missions/{mission_id}/events")
async def list_events(
    pentest_id: uuid.UUID,
    mission_id: uuid.UUID,
    _who: SignedIn,
    session: SessionDep,
    *,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_EVENTS)] = 200,
) -> EventPage:
    """The log of a mission after a cursor, oldest first. Ask again with `next_after` to follow
    it live."""
    await find(session, pentest_id)
    await _mission(session, pentest_id, mission_id)
    rows = (
        await session.scalars(
            select(MissionEvent)
            .where(MissionEvent.mission_id == mission_id, MissionEvent.id > after)
            .order_by(MissionEvent.id)
            .limit(limit)
        )
    ).all()
    return EventPage(
        events=[EventOut.of(one) for one in rows],
        next_after=rows[-1].id if rows else after,
    )


@router.post("/pentests/{pentest_id}/missions/{mission_id}/pause")
async def pause_mission(
    pentest_id: uuid.UUID,
    mission_id: uuid.UUID,
    *,
    request: Request,
    who: Admin,
    session: SessionDep,
) -> MissionOut:
    """Stop taking steps. The step in progress finishes first."""
    runner = _runner(request)
    mission = await _mission(session, pentest_id, mission_id)
    if mission.status != "running":
        raise AppError(409, "not_running", "This mission is not running")
    runner.engine.pause(session, mission, "Paused by a person.")
    audit.record(session, request, "mission.pause", actor=who.user, target=("mission", mission.id))
    return MissionOut.of(mission)


@router.post("/pentests/{pentest_id}/missions/{mission_id}/resume")
async def resume_mission(
    pentest_id: uuid.UUID,
    mission_id: uuid.UUID,
    *,
    body: ResumeIn,
    request: Request,
    background: BackgroundTasks,
    who: Admin,
    session: SessionDep,
) -> MissionOut:
    """Carry on a paused or stopped mission, with larger caps when it stopped on one."""
    runner = _runner(request)
    pentest = await find(session, pentest_id)
    ensure_editable(pentest)
    mission = await _mission(session, pentest_id, mission_id)
    if mission.status not in ("paused", "stopped"):
        raise AppError(409, "not_resumable", "This mission is not paused or stopped")
    if pentest.status != PentestStatus.RUNNING.value:
        raise AppError(409, "pentest_not_running", "The pentest is not running")
    if body.budget is not None:
        mission.budget = body.budget.model_dump()
    runner.engine.resume(session, mission)
    audit.record(session, request, "mission.resume", actor=who.user, target=("mission", mission.id))
    background.add_task(runner.launch_after_response, mission.id)
    return MissionOut.of(mission)


@router.post("/pentests/{pentest_id}/missions/{mission_id}/cancel")
async def cancel_mission(
    pentest_id: uuid.UUID,
    mission_id: uuid.UUID,
    *,
    request: Request,
    who: Admin,
    session: SessionDep,
) -> MissionOut:
    """End the mission. What has not run is cancelled, what has run stays in the results."""
    runner = _runner(request)
    mission = await _mission(session, pentest_id, mission_id)
    if mission.status not in ("running", "paused", "stopped", "pending"):
        raise AppError(409, "not_cancellable", "This mission is already over or being cancelled")
    runner.engine.cancel(session, mission)
    if not runner.active(mission.id):  # nothing is running it, so close it here
        await runner.engine.finish_cancel(session, mission)
    audit.record(session, request, "mission.cancel", actor=who.user, target=("mission", mission.id))
    return MissionOut.of(mission)


async def _answer(  # noqa: PLR0913  # the same few inputs as the two routes that call it
    pentest_id: uuid.UUID,
    mission_id: uuid.UUID,
    step_id: uuid.UUID,
    *,
    request: Request,
    background: BackgroundTasks,
    who: Admin,
    session: AsyncSession,
    approved: bool,
) -> StepOut:
    runner = _runner(request)
    mission = await _mission(session, pentest_id, mission_id)
    step = await _step(session, mission, step_id)
    step.status = "approved" if approved else "denied"
    step.note = ("Approved" if approved else "Denied") + f" by {who.user.username}."
    emit(
        session,
        mission.id,
        "step_approved" if approved else "step_denied",
        step.task_id,
        seq=step.seq,
        by=who.user.username,
    )
    task = await required(session, MissionTask, step.task_id)
    task.status = "pending"
    if mission.status == "paused" and mission.stop_reason == WAITING:
        runner.engine.resume(session, mission)
    audit.record(
        session,
        request,
        "mission.approve" if approved else "mission.deny",
        actor=who.user,
        target=("mission", mission.id),
        detail={"step": step.seq, "tool": step.tool},
    )
    background.add_task(runner.launch_after_response, mission.id)
    return StepOut.of(step)


@router.post("/pentests/{pentest_id}/missions/{mission_id}/steps/{step_id}/approve")
async def approve_step(  # the request, the ids and the three dependencies
    pentest_id: uuid.UUID,
    mission_id: uuid.UUID,
    step_id: uuid.UUID,
    *,
    request: Request,
    background: BackgroundTasks,
    who: Admin,
    session: SessionDep,
) -> StepOut:
    """Let one step that was waiting go ahead. It is checked again right before it runs."""
    return await _answer(
        pentest_id,
        mission_id,
        step_id,
        request=request,
        background=background,
        who=who,
        session=session,
        approved=True,
    )


@router.post("/pentests/{pentest_id}/missions/{mission_id}/steps/{step_id}/deny")
async def deny_step(  # the request, the ids and the three dependencies
    pentest_id: uuid.UUID,
    mission_id: uuid.UUID,
    step_id: uuid.UUID,
    *,
    request: Request,
    background: BackgroundTasks,
    who: Admin,
    session: SessionDep,
) -> StepOut:
    """Refuse one step that was waiting. The agent sees that and chooses something else."""
    return await _answer(
        pentest_id,
        mission_id,
        step_id,
        request=request,
        background=background,
        who=who,
        session=session,
        approved=False,
    )

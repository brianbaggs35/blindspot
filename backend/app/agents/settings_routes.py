"""The Agents page: every agent in the hierarchy with how it has done, the caps and presets new
missions start from, and the versions of the prompts. Anyone signed in can read; changing a cap or
a prompt needs an administrator and is recorded in the audit log.

A prompt is never edited: a change adds a version, and a mission keeps the version it started with.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import Float, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.budget import Budget
from app.agents.prompts import AGENTS, BUILTIN, LABELS, MAX_PROMPT
from app.agents.settings import (
    BUILTIN_VERSION,
    PRESETS,
    Preset,
    activate,
    active_versions,
    add_version,
    default_budget,
    save_budget,
    versions_of,
    with_changes,
)
from app.auth import audit
from app.auth.deps import Admin, SignedIn
from app.db.models import AgentPrompt, Methodology, MissionTask, User
from app.db.session import SessionDep
from app.errors import AppError
from app.methodology.routes import seed
from app.methodology.spec import MethodologySpec, RiskClass
from app.methodology.store import overrides, stored, with_overrides

router = APIRouter(prefix="/api/agents", tags=["agents"])

PromptText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=20, max_length=MAX_PROMPT)
]
AgentName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z-]{1,23}$")]
FINISHED = ("done", "failed")
LIVE_TASK = ("running", "waiting")


class Stats(BaseModel):
    """How one agent has done over every mission so far."""

    runs: int = 0
    succeeded: int = 0
    failed: int = 0
    success_rate: float | None = None
    cost_per_run_usd: float | None = None
    last_run: datetime | None = None
    active: bool = False


class Node(BaseModel):
    """An agent: the commander, a category agent, or the test agent for one test."""

    id: str
    name: str
    kind: str
    risk_class: str | None = None
    tools: list[str] = Field(default_factory=list[str])
    stats: Stats
    children: list[Node] = Field(default_factory=list["Node"])


class MethodologyChoice(BaseModel):
    id: str
    name: str


class Overview(BaseModel):
    methodology_id: str | None
    methodologies: list[MethodologyChoice]
    commander: Node | None
    runner_ready: bool


class PresetOut(BaseModel):
    id: str
    name: str
    summary: str
    max_risk: RiskClass
    budget: Budget


class VersionOut(BaseModel):
    version: int
    note: str
    created_at: datetime | None
    created_by: str | None
    active: bool


class PromptOut(BaseModel):
    agent: str
    label: str
    active: int
    versions: list[VersionOut]


class SettingsOut(BaseModel):
    budget: Budget
    built_in_budget: Budget
    presets: list[PresetOut]
    prompts: list[PromptOut]
    max_prompt: int


class PromptBody(BaseModel):
    agent: str
    version: int
    note: str
    body: str


class PromptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=20, max_length=MAX_PROMPT)
    ]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    activate: bool = True


class ActivateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Annotated[int, Field(ge=0, le=100_000)]


def _agent(name: str) -> str:
    if name not in AGENTS:
        raise AppError(404, "unknown_agent", "There is no such agent prompt")
    return name


def _rate(done: int, failed: int) -> float | None:
    return round(done / (done + failed), 3) if done + failed else None


async def _stats(session: AsyncSession, kind: str, refs: list[str]) -> dict[str, Stats]:
    """What the finished tasks of each agent came to. Tasks that were skipped or cancelled are not
    runs."""
    cost = func.sum(func.coalesce(MissionTask.spent["cost_usd"].astext.cast(Float), 0.0))
    rows = await session.execute(
        select(
            MissionTask.ref,
            MissionTask.status,
            func.count(),
            func.max(MissionTask.updated_at),
            cost,
        )
        .where(MissionTask.kind == kind, MissionTask.ref.in_(refs))
        .group_by(MissionTask.ref, MissionTask.status)
    )
    out = {ref: Stats() for ref in refs}
    spent: dict[str, float] = {}
    for ref, status, count, latest, total in rows.all():
        stat = out[ref]
        if status in FINISHED:
            stat.runs += count
            if status == "done":
                stat.succeeded += count
            else:
                stat.failed += count
            spent[ref] = spent.get(ref, 0.0) + float(total or 0)
            stat.last_run = latest if stat.last_run is None else max(stat.last_run, latest)
        stat.active = stat.active or status in LIVE_TASK
    for ref, stat in out.items():
        stat.success_rate = _rate(stat.succeeded, stat.failed)
        stat.cost_per_run_usd = round(spent.get(ref, 0.0) / stat.runs, 4) if stat.runs else None
    return out


async def _spec(session: AsyncSession, methodology_id: str) -> MethodologySpec:
    found = await stored(session, methodology_id)
    if found is None:
        raise AppError(404, "not_found", "There is no such methodology")
    return with_overrides(found.spec, await overrides(session, methodology_id))


@router.get("/overview")
async def overview(
    request: Request,
    _who: SignedIn,
    session: SessionDep,
    methodology: Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9-]{1,31}$")] = None,
) -> Overview:
    """The hierarchy for a methodology: the commander, a category agent for each category and a
    test agent for each test, each with how it has done."""
    await seed(session)
    choices = [
        MethodologyChoice(id=row.id, name=row.name)
        for row in await session.scalars(
            select(Methodology).where(Methodology.enabled.is_(True)).order_by(Methodology.name)
        )
    ]
    runner_ready = request.app.state.missions is not None
    chosen = methodology or (choices[0].id if choices else None)
    if chosen is None:
        return Overview(
            methodology_id=None, methodologies=choices, commander=None, runner_ready=runner_ready
        )
    spec = await _spec(session, chosen)
    categories = await _stats(session, "category", [c.id for c in spec.categories])
    tests = await _stats(session, "test", [t.id for c in spec.categories for t in c.tests])
    commander = (await _stats(session, "commander", ["commander"]))["commander"]
    tree = Node(
        id="commander",
        name="Mission Commander",
        kind="commander",
        stats=commander,
        children=[
            Node(
                id=category.id,
                name=category.name,
                kind="category",
                stats=categories[category.id],
                children=[
                    Node(
                        id=test.id,
                        name=test.name,
                        kind="test",
                        risk_class=test.risk_class.value,
                        tools=list(test.playbook.tools),
                        stats=tests[test.id],
                    )
                    for test in category.tests
                ],
            )
            for category in spec.categories
        ],
    )
    return Overview(
        methodology_id=chosen, methodologies=choices, commander=tree, runner_ready=runner_ready
    )


def _preset_out(preset: Preset, base: Budget) -> PresetOut:
    return PresetOut(
        id=preset.id,
        name=preset.name,
        summary=preset.summary,
        max_risk=preset.max_risk,
        budget=with_changes(base, preset.changes),
    )


async def _prompts(session: AsyncSession) -> list[PromptOut]:
    live = await active_versions(session)
    names = {
        user.id: user.display_name
        for user in await session.scalars(select(User).where(User.id.in_(await _authors(session))))
    }
    out: list[PromptOut] = []
    for agent in AGENTS:
        versions = [
            VersionOut(
                version=BUILTIN_VERSION,
                note="Built in",
                created_at=None,
                created_by=None,
                active=live[agent] == BUILTIN_VERSION,
            )
        ] + [
            VersionOut(
                version=row.version,
                note=row.note,
                created_at=row.created_at,
                created_by=names.get(row.created_by) if row.created_by else None,
                active=live[agent] == row.version,
            )
            for row in await versions_of(session, agent)
        ]
        out.append(
            PromptOut(agent=agent, label=LABELS[agent], active=live[agent], versions=versions)
        )
    return out


async def _authors(session: AsyncSession) -> list[Any]:
    rows = await session.scalars(select(AgentPrompt.created_by).distinct())
    return [one for one in rows if one is not None]


@router.get("/settings")
async def read_settings(_who: SignedIn, session: SessionDep) -> SettingsOut:
    """The caps new missions start with, the presets, and the prompt versions."""
    base = await default_budget(session)
    return SettingsOut(
        budget=base,
        built_in_budget=Budget(),
        presets=[_preset_out(one, base) for one in PRESETS],
        prompts=await _prompts(session),
        max_prompt=MAX_PROMPT,
    )


@router.put("/settings/budget")
async def save_defaults(body: Budget, request: Request, who: Admin, session: SessionDep) -> Budget:
    """Change the caps a mission starts with when nobody picks others."""
    before = await default_budget(session)
    await save_budget(session, body)
    changed = {
        key: value for key, value in body.model_dump().items() if value != before.model_dump()[key]
    }
    audit.record(
        session,
        request,
        "agents.budget",
        actor=who.user,
        detail={"changed": changed},
    )
    return body


@router.get("/prompts/{agent}/{version}")
async def read_prompt(
    agent: Annotated[str, Path()], version: int, _who: SignedIn, session: SessionDep
) -> PromptBody:
    """The text of one version. Version 0 is the built-in text."""
    _agent(agent)
    if version != BUILTIN_VERSION:
        row = await session.scalar(
            select(AgentPrompt).where(AgentPrompt.agent == agent, AgentPrompt.version == version)
        )
        if row is None:
            raise AppError(404, "unknown_version", "There is no such version")
        return PromptBody(agent=agent, version=version, note=row.note, body=row.body)
    return PromptBody(agent=agent, version=0, note="Built in", body=BUILTIN[agent])


@router.post("/prompts/{agent}", status_code=201)
async def add_prompt(
    agent: AgentName, body: PromptIn, request: Request, who: Admin, session: SessionDep
) -> PromptOut:
    """Add a version of a prompt. It is never edited afterwards. By default new missions use it."""
    _agent(agent)
    row = await add_version(session, agent, body.body, body.note, who.user.id)
    audit.record(
        session,
        request,
        "agents.prompt_add",
        actor=who.user,
        target=("agent_prompt", row.id),
        detail={"agent": agent, "version": row.version},
    )
    if body.activate:
        await activate(session, agent, row.version)
        audit.record(
            session,
            request,
            "agents.prompt_activate",
            actor=who.user,
            detail={"agent": agent, "version": row.version},
        )
    return next(one for one in await _prompts(session) if one.agent == agent)


@router.post("/prompts/{agent}/activate")
async def activate_prompt(
    agent: AgentName, body: ActivateIn, request: Request, who: Admin, session: SessionDep
) -> PromptOut:
    """Choose the version new missions use. Version 0 puts back the built-in text."""
    _agent(agent)
    if not await activate(session, agent, body.version):
        raise AppError(404, "unknown_version", "There is no such version")
    audit.record(
        session,
        request,
        "agents.prompt_activate",
        actor=who.user,
        detail={"agent": agent, "version": body.version},
    )
    return next(one for one in await _prompts(session) if one.agent == agent)

"""What an administrator can change about the agents: the caps a new mission starts with, the
presets to start from, and which version of each prompt new missions use.

Prompt versions are only ever added. A mission keeps the versions it started with, so changing a
prompt never changes a mission that is already running, and what an agent was told stays readable.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.budget import Budget
from app.agents.prompts import AGENTS, BUILTIN
from app.db.models import AgentPrompt, AppSetting, Mission
from app.methodology.spec import RiskClass

BUDGET_KEY = "agents.budget"
PROMPTS_KEY = "agents.prompts"
BUILTIN_VERSION = 0


@dataclass(frozen=True)
class Preset:
    """A way to start a mission: the most intrusive thing it may do, and what to change in the
    default caps."""

    id: str
    name: str
    summary: str
    max_risk: RiskClass
    changes: dict[str, Any] = field(default_factory=dict[str, Any])


PRESETS = (
    Preset(
        "passive-recon",
        "Passive recon only",
        "Only tests that observe: nothing is sent to the target that it was not built to expect.",
        RiskClass.SAFE,
        {"steps_per_test": 6, "seconds_per_test": 300},
    ),
    Preset(
        "safe-full",
        "Safe full assessment",
        "Every test that observes or sends ordinary probing requests. Nothing intrusive.",
        RiskClass.ACTIVE,
    ),
    Preset(
        "deep-dive",
        "Deep dive (asks before intrusive steps)",
        "Every test, with longer runs. Intrusive steps always wait for an administrator.",
        RiskClass.INTRUSIVE,
        {"steps_per_test": 25, "tokens_per_test": 250_000, "seconds_per_test": 1800},
    ),
)


def preset_named(preset_id: str) -> Preset | None:
    return next((one for one in PRESETS if one.id == preset_id), None)


async def _read(session: AsyncSession, key: str) -> object:
    row = await session.get(AppSetting, key)
    return None if row is None else row.value


async def _write(session: AsyncSession, key: str, value: object) -> None:
    await session.execute(
        insert(AppSetting)
        .values(key=key, value=value)
        .on_conflict_do_update(
            index_elements=["key"], set_={"value": value, "updated_at": func.now()}
        )
    )


async def default_budget(session: AsyncSession) -> Budget:
    """The caps a new mission starts with. A stored value that no longer fits falls back to the
    built-in caps rather than stopping every mission."""
    stored = await _read(session, BUDGET_KEY)
    try:
        return Budget.model_validate(stored) if stored is not None else Budget()
    except ValidationError:
        return Budget()


async def save_budget(session: AsyncSession, budget: Budget) -> None:
    await _write(session, BUDGET_KEY, budget.model_dump())


def with_changes(base: Budget, changes: dict[str, Any]) -> Budget:
    return Budget.model_validate({**base.model_dump(), **changes})


async def active_versions(session: AsyncSession) -> dict[str, int]:
    """The version of each prompt a mission started now would use."""
    stored = await _read(session, PROMPTS_KEY)
    chosen = cast("dict[str, object]", stored) if isinstance(stored, dict) else {}
    out: dict[str, int] = {}
    for agent in AGENTS:
        version = chosen.get(agent, BUILTIN_VERSION)
        out[agent] = version if isinstance(version, int) else BUILTIN_VERSION
    return out


async def versions_of(session: AsyncSession, agent: str) -> list[AgentPrompt]:
    rows = await session.scalars(
        select(AgentPrompt).where(AgentPrompt.agent == agent).order_by(AgentPrompt.version)
    )
    return list(rows)


async def add_version(
    session: AsyncSession, agent: str, body: str, note: str, created_by: uuid.UUID
) -> AgentPrompt:
    """Add the next version of a prompt (the first one stored is version 1; 0 is the built-in)."""
    # Two administrators adding at once must not both take the same number.
    await session.execute(select(func.pg_advisory_xact_lock(AGENTS.index(agent) + 7000)))
    newest = await session.scalar(
        select(func.max(AgentPrompt.version)).where(AgentPrompt.agent == agent)
    )
    row = AgentPrompt(
        agent=agent, version=(newest or 0) + 1, body=body, note=note, created_by=created_by
    )
    session.add(row)
    await session.flush()
    return row


async def activate(session: AsyncSession, agent: str, version: int) -> bool:
    """Make a version the one new missions use. False when there is no such version."""
    if version != BUILTIN_VERSION:
        found = await session.scalar(
            select(AgentPrompt.id).where(AgentPrompt.agent == agent, AgentPrompt.version == version)
        )
        if found is None:
            return False
    await _write(session, PROMPTS_KEY, {**await active_versions(session), agent: version})
    return True


async def body_of(session: AsyncSession, agent: str, version: int) -> str:
    """The text of a version. A version that is gone reads as the built-in text."""
    if version != BUILTIN_VERSION:
        body = await session.scalar(
            select(AgentPrompt.body).where(
                AgentPrompt.agent == agent, AgentPrompt.version == version
            )
        )
        if body is not None:
            return body
    return BUILTIN[agent]


async def mission_prompt(session: AsyncSession, mission_id: uuid.UUID, agent: str) -> str:
    """The prompt a mission started with."""
    mission = await session.get(Mission, mission_id)
    used = cast("dict[str, int]", mission.prompts) if mission is not None else {}
    return await body_of(session, agent, used.get(agent, BUILTIN_VERSION))

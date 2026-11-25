"""What the engine reads and writes in the database, a small piece at a time."""

import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.budget import Spent
from app.agents.ports import FactIn, HistoryItem
from app.db.models import (
    Mission,
    MissionEvent,
    MissionFact,
    MissionStep,
    MissionTask,
    PentestResult,
)
from app.results.service import summary_of

ACCOUNT_LIMIT = 700
HISTORY_LIMIT = 16  # steps shown in full; older ones are folded into one line
_ENGLISH = text("'english'")


def emit(
    session: AsyncSession,
    mission_id: uuid.UUID,
    kind: str,
    task_id: uuid.UUID | None = None,
    **data: Any,
) -> None:
    """Add an event to the mission's log. It is saved with the rest of the unit of work."""
    session.add(MissionEvent(mission_id=mission_id, task_id=task_id, type=kind, data=data))


def spent_of(stored: Any) -> Spent:
    return Spent.model_validate(stored or {})


def charge(
    row: Mission | MissionTask,
    *,
    steps: int = 0,
    tokens: int = 0,
    cost: float = 0.0,
    seconds: float = 0.0,
) -> None:
    """Add to what a mission or a task has used (a new value is assigned, so the change is seen)."""
    updated = spent_of(row.spent).add(steps=steps, tokens=tokens, cost_usd=cost, seconds=seconds)
    row.spent = updated.model_dump()


def add_facts(
    session: AsyncSession,
    mission_id: uuid.UUID,
    task_id: uuid.UUID | None,
    facts: list[FactIn],
    *,
    source: uuid.UUID | None = None,
) -> None:
    for one in facts:
        session.add(
            MissionFact(
                mission_id=mission_id,
                task_id=task_id,
                subject=one.subject,
                fact=one.fact,
                confidence=one.confidence,
                source_result_id=source,
            )
        )


async def facts_for(session: AsyncSession, mission_id: uuid.UUID, query: str) -> list[str]:
    """What the agents learned that is about `query` (PostgreSQL full-text search), best first; the
    latest facts when nothing matches."""
    rank = func.ts_rank(
        func.to_tsvector(_ENGLISH, MissionFact.subject + " " + MissionFact.fact),
        func.websearch_to_tsquery(_ENGLISH, query),
    )
    match = func.to_tsvector(_ENGLISH, MissionFact.subject + " " + MissionFact.fact).op("@@")(
        func.websearch_to_tsquery(_ENGLISH, query)
    )
    found = (
        await session.scalars(
            select(MissionFact)
            .where(MissionFact.mission_id == mission_id, match)
            .order_by(rank.desc(), MissionFact.created_at.desc())
            .limit(10)
        )
    ).all()
    if not found:
        found = (
            await session.scalars(
                select(MissionFact)
                .where(MissionFact.mission_id == mission_id)
                .order_by(MissionFact.created_at.desc())
                .limit(10)
            )
        ).all()
    return [f"{one.subject}: {one.fact} ({one.confidence} confidence)" for one in found]


async def account_of(session: AsyncSession, step: MissionStep) -> str:
    """What the agent is told about how a step ended: short, and never what the target said in its
    own words beyond the counts and titles in the result."""
    if step.status == "done" and step.result_id is not None:
        row = await session.get(PentestResult, step.result_id)
        if row is None:  # the result was deleted since
            return "Done; the result was deleted."
        lines = summary_of(row).summary
        return " ".join(lines)[:ACCOUNT_LIMIT] or "Done; the tool reported nothing."
    return (step.note or step.status)[:ACCOUNT_LIMIT]


async def history_of(session: AsyncSession, task_id: uuid.UUID) -> list[HistoryItem]:
    steps = (
        await session.scalars(
            select(MissionStep).where(MissionStep.task_id == task_id).order_by(MissionStep.seq)
        )
    ).all()
    items = [
        HistoryItem(one.seq, one.tool, one.status, await account_of(session, one)) for one in steps
    ]
    if len(items) <= HISTORY_LIMIT:
        return items
    older, recent = items[:-HISTORY_LIMIT], items[-HISTORY_LIMIT:]
    tools = sorted({one.tool for one in older})
    digest = HistoryItem(
        0, "-", "folded", f"{len(older)} earlier steps with {', '.join(tools)} (see the log)."
    )
    return [digest, *recent]


async def required[T](session: AsyncSession, model: type[T], key: uuid.UUID) -> T:
    """The row, or an error when it is gone (the engine only asks for rows it has just seen)."""
    row = await session.get(model, key)
    if row is None:
        raise LookupError(f"{model.__name__} {key} is gone")
    return row

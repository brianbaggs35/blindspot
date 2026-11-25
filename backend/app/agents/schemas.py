"""What the missions API takes and gives."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.budget import Budget
from app.db.models import Mission, MissionEvent, MissionStep, MissionTask


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget: Budget = Field(default_factory=Budget)


class ResumeIn(BaseModel):
    """Resuming may raise the caps, for a mission that stopped on one."""

    model_config = ConfigDict(extra="forbid")

    budget: Budget | None = None


class MissionOut(BaseModel):
    id: uuid.UUID
    pentest_id: uuid.UUID
    status: str
    budget: dict[str, Any]
    spent: dict[str, Any]
    plan: dict[str, Any]
    stop_reason: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, row: Mission) -> MissionOut:
        return cls(
            id=row.id,
            pentest_id=row.pentest_id,
            status=row.status,
            budget=row.budget,
            spent=row.spent,
            plan=row.plan,
            stop_reason=row.stop_reason,
            started_at=row.started_at,
            finished_at=row.finished_at,
            created_at=row.created_at,
        )


class TaskOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    kind: str
    ref: str
    name: str
    phase: int
    position: int
    status: str
    summary: str
    outcome: dict[str, Any] | None
    spent: dict[str, Any]

    @classmethod
    def of(cls, row: MissionTask) -> TaskOut:
        return cls(
            id=row.id,
            parent_id=row.parent_id,
            kind=row.kind,
            ref=row.ref,
            name=row.name,
            phase=row.phase,
            position=row.position,
            status=row.status,
            summary=row.summary,
            outcome=row.outcome,
            spent=row.spent,
        )


class MissionDetail(BaseModel):
    mission: MissionOut
    tasks: list[TaskOut]


class MissionList(BaseModel):
    missions: list[MissionOut]


class StepOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    seq: int
    status: str
    tool: str
    request: dict[str, Any]
    verdict: dict[str, Any] | None
    result_id: uuid.UUID | None
    note: str
    created_at: datetime

    @classmethod
    def of(cls, row: MissionStep) -> StepOut:
        return cls(
            id=row.id,
            task_id=row.task_id,
            seq=row.seq,
            status=row.status,
            tool=row.tool,
            request=row.request,
            verdict=row.verdict,
            result_id=row.result_id,
            note=row.note,
            created_at=row.created_at,
        )


class StepList(BaseModel):
    steps: list[StepOut]


class EventOut(BaseModel):
    id: int
    task_id: uuid.UUID | None
    type: str
    data: dict[str, Any]
    created_at: datetime

    @classmethod
    def of(cls, row: MissionEvent) -> EventOut:
        return cls(
            id=row.id,
            task_id=row.task_id,
            type=row.type,
            data=row.data,
            created_at=row.created_at,
        )


class EventPage(BaseModel):
    """Events after a cursor. Ask again with `next_after` for the ones that follow."""

    events: list[EventOut]
    next_after: int

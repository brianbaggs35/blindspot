"""The audit trail, for administrators."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.auth.deps import ADMIN
from app.auth.schemas import AuditOut, AuditPage
from app.db.models import AuditEvent
from app.db.session import SessionDep

router = APIRouter(prefix="/api/audit", tags=["audit"], dependencies=[Depends(ADMIN)])


@router.get("")
async def list_events(
    session: SessionDep,
    *,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    outcome: Annotated[str | None, Query(pattern="^(success|failure)$")] = None,
    actor: Annotated[str | None, Query(max_length=100)] = None,
    since: datetime | None = None,
) -> AuditPage:
    """The newest events first. `before` is the `next_before` of the page before (ids are
    ordered by time); the other parameters narrow the list."""
    query = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit + 1)
    if before is not None:
        query = query.where(AuditEvent.id < before)
    if action is not None:
        query = query.where(AuditEvent.action == action)
    if outcome is not None:
        query = query.where(AuditEvent.outcome == outcome)
    if actor is not None:
        query = query.where(AuditEvent.actor_name == actor)
    if since is not None:
        query = query.where(AuditEvent.created_at >= since)
    rows = list(await session.scalars(query))
    page = rows[:limit]
    return AuditPage(
        items=[AuditOut.model_validate(row) for row in page],
        next_before=page[-1].id if len(rows) > limit else None,
    )

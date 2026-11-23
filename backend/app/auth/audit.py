"""The audit trail: who did what, when and from where. Rows are only added."""

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent, User


def client_address(request: Request) -> str | None:
    """Where the request came from (nginx passes the real address on)."""
    return request.client.host if request.client else None


def client_agent(request: Request) -> str | None:
    """The browser, shortened to fit the column."""
    agent = request.headers.get("user-agent")
    return agent[:256] if agent else None


def record(
    session: AsyncSession,
    request: Request,
    action: str,
    *,
    actor: User | str | None = None,
    outcome: str = "success",
    target: tuple[str, uuid.UUID | str] | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Add an event to the trail. It is saved with the rest of the request. `actor` is the user,
    or for a failed sign-in the name that was typed. Never put a secret in `detail`: it is shown to
    administrators."""
    session.add(
        AuditEvent(
            actor_id=actor.id if isinstance(actor, User) else None,
            actor_name=(actor.username if isinstance(actor, User) else actor),
            action=action,
            outcome=outcome,
            target_type=target[0] if target else None,
            target_id=str(target[1]) if target else None,
            ip_address=client_address(request),
            user_agent=client_agent(request),
            detail=detail,
        )
    )

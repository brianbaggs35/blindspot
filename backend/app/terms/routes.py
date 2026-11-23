"""Showing the terms and recording that a person accepted them."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.auth import audit
from app.auth.deps import SignedIn
from app.db.base import utc_now
from app.db.models import User
from app.db.session import SessionDep
from app.errors import AppError
from app.terms.text import SECTIONS, TITLE, VERSION, Section

router = APIRouter(prefix="/api/terms", tags=["terms"])


class TermsOut(BaseModel):
    title: str
    version: str
    accepted: bool
    accepted_at: datetime | None
    sections: tuple[Section, ...]


class AcceptIn(BaseModel):
    """The version the person read, so an answer to old words is never taken for the new ones."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[str, StringConstraints(min_length=1, max_length=32)]


def accepted_current(user: User) -> bool:
    """Whether this person has accepted the terms as they are now."""
    return user.terms_accepted


def view(user: User) -> TermsOut:
    current = accepted_current(user)
    return TermsOut(
        title=TITLE,
        version=VERSION,
        accepted=current,
        accepted_at=user.terms_accepted_at if current else None,
        sections=SECTIONS,
    )


def require_accepted(user: User) -> None:
    """Refuse an action that needs the terms to have been accepted."""
    if not accepted_current(user):
        raise AppError(
            403,
            "terms_not_accepted",
            "Accept the terms of use first",
            "Open the terms of use, read them and accept them to continue.",
        )


@router.get("")
async def read_terms(who: SignedIn) -> TermsOut:
    """The current terms and whether the signed-in person has accepted them. A viewer can read and
    accept them too: accepting is something a person does for their own account."""
    return view(who.user)


@router.post("/accept")
async def accept_terms(
    body: AcceptIn, request: Request, who: SignedIn, session: SessionDep
) -> TermsOut:
    """Record that the signed-in person read and accepted this version."""
    if body.version != VERSION:
        raise AppError(
            409,
            "terms_changed",
            "The terms changed while you were reading them",
            "Read them again, then accept.",
        )
    user = who.user
    if not accepted_current(user):
        user.terms_version = VERSION
        user.terms_accepted_at = utc_now()
        audit.record(
            session,
            request,
            "terms.accept",
            actor=user,
            target=("user", user.id),
            detail={"version": VERSION},
        )
        await session.flush()
    return view(user)

"""Passkey routes: add, list, rename and remove your own, and sign in with one."""

import uuid
from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select

from app.auth import audit, passkeys
from app.auth.deps import PUBLIC, SignedIn
from app.auth.passwords import verify_password
from app.auth.ratelimit import FailureLimiter
from app.auth.routes import set_cookie, too_many
from app.auth.schemas import Password, Strict, UserOut
from app.auth.service import start_session
from app.config import get_settings
from app.db.base import utc_now
from app.db.models import Passkey
from app.db.session import SessionDep
from app.errors import AppError, problem

router = APIRouter(prefix="/api/auth/passkeys", tags=["passkeys"])

PasskeyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class PasskeyOut(BaseModel):
    """A passkey as its owner sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None
    backup_eligible: bool
    backed_up: bool
    transports: list[str]


class Ceremony(BaseModel):
    """What the browser is given to start making or using a passkey."""

    challenge_id: uuid.UUID
    options: dict[str, Any]


class ReauthIn(Strict):
    """Adding a passkey asks for the password again."""

    password: Password


class RegisterIn(Strict):
    """The browser's new credential."""

    challenge_id: uuid.UUID
    name: PasskeyName
    credential: dict[str, Any]


class LoginIn(Strict):
    """The browser's answer to a sign-in challenge."""

    challenge_id: uuid.UUID
    credential: dict[str, Any] = Field(max_length=16)


class RenameIn(Strict):
    """A new name for a passkey."""

    name: PasskeyName


def _limiter(request: Request) -> FailureLimiter:
    return cast("FailureLimiter", request.app.state.passkey_limiter)


def _password_limiter(request: Request) -> FailureLimiter:
    return cast("FailureLimiter", request.app.state.limiter)


async def _reauthenticate(
    request: Request, who: SignedIn, session: SessionDep, password: str
) -> JSONResponse | None:
    """Passkeys are added and removed only by someone who knows the password: a stolen session
    alone cannot plant its own way back in. Returns the refusal, or None when it is the password."""
    limiter = _password_limiter(request)
    address = audit.client_address(request) or "unknown"
    if wait := limiter.blocked_for(address):
        return too_many(request, wait)
    correct, _ = await verify_password(who.user.password_hash, password)
    if correct:
        return None
    limiter.record_failure(address)
    audit.record(session, request, "auth.reauthenticate", actor=who.user, outcome="failure")
    return problem(request, 403, "current_password_wrong", "The password is wrong")


@router.get("")
async def list_passkeys(who: SignedIn, session: SessionDep) -> list[PasskeyOut]:
    """Your passkeys."""
    rows = await session.scalars(
        select(Passkey).where(Passkey.user_id == who.user.id).order_by(Passkey.created_at)
    )
    return [PasskeyOut.model_validate(row) for row in rows]


@router.post("/register/options", response_model=Ceremony)
async def registration_options(
    body: ReauthIn, request: Request, who: SignedIn, session: SessionDep
) -> Ceremony | JSONResponse:
    """Start adding a passkey. Asks for the password again."""
    if refusal := await _reauthenticate(request, who, session, body.password):
        return refusal
    if await passkeys.count_passkeys(session, who.user.id) >= passkeys.MAX_PER_ACCOUNT:
        raise AppError(409, "too_many_passkeys", "An account can have 20 passkeys at most")
    challenge_id, options = await passkeys.registration_options(
        session, get_settings(), who.user, utc_now()
    )
    return Ceremony(challenge_id=challenge_id, options=options)


@router.post("/register", status_code=201, response_model=PasskeyOut)
async def register(
    body: RegisterIn, request: Request, who: SignedIn, session: SessionDep
) -> PasskeyOut | JSONResponse:
    """Finish adding a passkey."""
    limiter, address = _limiter(request), audit.client_address(request) or "unknown"
    if wait := limiter.blocked_for(address):
        return too_many(request, wait)
    if await passkeys.count_passkeys(session, who.user.id) >= passkeys.MAX_PER_ACCOUNT:
        raise AppError(409, "too_many_passkeys", "An account can have 20 passkeys at most")
    try:
        passkey = await passkeys.register(
            session,
            get_settings(),
            who.user,
            challenge_id=body.challenge_id,
            credential=body.credential,
            name=body.name,
            now=utc_now(),
        )
    except passkeys.PasskeyError as error:
        limiter.record_failure(address)
        audit.record(
            session,
            request,
            "passkey.add",
            actor=who.user,
            outcome="failure",
            detail={"reason": error.reason[:200]},
        )
        return problem(request, 400, "passkey_refused", "The passkey could not be added")
    audit.record(session, request, "passkey.add", actor=who.user, target=("passkey", passkey.id))
    return PasskeyOut.model_validate(passkey)


@router.patch("/{passkey_id}")
async def rename(
    passkey_id: uuid.UUID, body: RenameIn, request: Request, who: SignedIn, session: SessionDep
) -> PasskeyOut:
    """Rename one of your passkeys."""
    passkey = await _mine(session, who, passkey_id)
    passkey.name = body.name
    audit.record(session, request, "passkey.rename", actor=who.user, target=("passkey", passkey.id))
    return PasskeyOut.model_validate(passkey)


@router.delete("/{passkey_id}", status_code=204)
async def remove(
    passkey_id: uuid.UUID, body: ReauthIn, request: Request, who: SignedIn, session: SessionDep
) -> Response:
    """Remove one of your passkeys. Asks for the password again."""
    if refusal := await _reauthenticate(request, who, session, body.password):
        return refusal
    passkey = await _mine(session, who, passkey_id)
    await session.delete(passkey)
    audit.record(session, request, "passkey.remove", actor=who.user, target=("passkey", passkey.id))
    return Response(status_code=204)


async def _mine(session: SessionDep, who: SignedIn, passkey_id: uuid.UUID) -> Passkey:
    passkey = await session.scalar(
        select(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == who.user.id)
    )
    if passkey is None:
        raise AppError(404, "not_found", "There is no such passkey")
    return passkey


@router.post("/login/options", dependencies=[Depends(PUBLIC)], response_model=Ceremony)
async def login_options(request: Request, session: SessionDep) -> Ceremony | JSONResponse:
    """Start signing in with a passkey. No username is needed."""
    if wait := _limiter(request).blocked_for(audit.client_address(request) or "unknown"):
        return too_many(request, wait)
    challenge_id, options = await passkeys.authentication_options(
        session, get_settings(), utc_now()
    )
    return Ceremony(challenge_id=challenge_id, options=options)


@router.post("/login", dependencies=[Depends(PUBLIC)], response_model=UserOut)
async def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep
) -> UserOut | JSONResponse:
    """Finish signing in with a passkey. Failures count against the address, apart from the
    password's own lockout, and all look the same."""
    limiter, address = _limiter(request), audit.client_address(request) or "unknown"
    if wait := limiter.blocked_for(address):
        return too_many(request, wait)
    settings, now = get_settings(), utc_now()
    try:
        user, passkey = await passkeys.authenticate(
            session,
            settings,
            challenge_id=body.challenge_id,
            credential=body.credential,
            now=now,
        )
    except passkeys.PasskeyError as error:
        limiter.record_failure(address)
        audit.record(
            session,
            request,
            "passkey.clone_suspected" if error.cloned else "passkey.login",
            actor=None,
            outcome="failure",
            detail={"reason": error.reason[:200]},
        )
        return problem(
            request, 401, "invalid_credentials", "The passkey could not be used to sign in"
        )
    token, _ = await start_session(
        session,
        settings,
        user,
        now,
        address=audit.client_address(request),
        agent=audit.client_agent(request),
    )
    audit.record(session, request, "passkey.login", actor=user, target=("passkey", passkey.id))
    set_cookie(response, settings, token)
    return UserOut.model_validate(user)

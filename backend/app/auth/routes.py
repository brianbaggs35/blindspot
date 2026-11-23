"""Sign-in, sessions and first-run setup."""

import uuid
from typing import cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from app.auth import audit
from app.auth.deps import COOKIE_NAME, PUBLIC, Anyone, SignedIn
from app.auth.passwords import password_problem, verify_password
from app.auth.ratelimit import FailureLimiter
from app.auth.schemas import (
    LoginIn,
    PasswordChangeIn,
    SessionOut,
    SetupIn,
    Status,
    UserOut,
)
from app.auth.service import (
    authenticate,
    count_users,
    create_user,
    find_user,
    is_locked,
    is_valid_username,
    live_sessions,
    normalize_username,
    revoke_sessions,
    set_password,
    start_session,
)
from app.auth.setup_code import SetupGate
from app.config import Settings, get_settings
from app.db.base import utc_now
from app.db.models import AuthSession, Role
from app.db.session import SessionDep
from app.errors import AppError, problem

router = APIRouter(prefix="/api/auth", tags=["auth"])

SETUP_LOCK_KEY = 7_204_150_001  # one number for "someone is setting the app up"
GENERIC_FAILURE = "The username or password is wrong, or the account is locked."


def _limiter(request: Request) -> FailureLimiter:
    return cast("FailureLimiter", request.app.state.limiter)


def _gate(request: Request) -> SetupGate:
    return cast("SetupGate", request.app.state.setup_gate)


def too_many(request: Request, wait: float) -> JSONResponse:
    response = problem(
        request, 429, "too_many_attempts", "Too many attempts. Try again in a few minutes."
    )
    response.headers["Retry-After"] = str(int(wait) + 1)
    return response


def set_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_total_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        COOKIE_NAME, httponly=True, secure=settings.cookie_secure, samesite="strict", path="/"
    )


@router.get("/status")
async def status(request: Request, who: Anyone, session: SessionDep) -> Status:
    """Whether setup is needed and who is signed in. The sign-in page asks this first."""
    if who is not None:
        return Status(setup_required=False, user=UserOut.model_validate(who.user))
    setup_required = await count_users(session) == 0
    if setup_required:
        _gate(request).open()  # in case the database was not up when the app started
    return Status(setup_required=setup_required, user=None)


@router.post("/setup", dependencies=[Depends(PUBLIC)], response_model=UserOut)
async def setup(
    body: SetupIn, request: Request, response: Response, session: SessionDep
) -> UserOut | JSONResponse:
    """Make the first administrator. Works once, and only with the code from the log."""
    limiter, address = _limiter(request), audit.client_address(request) or "unknown"
    if wait := limiter.blocked_for(address):
        return too_many(request, wait)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SETUP_LOCK_KEY})
    if await count_users(session) > 0:
        raise AppError(409, "setup_complete", "Setup has already been done")
    if not _gate(request).accepts(body.setup_code):
        limiter.record_failure(address)
        audit.record(session, request, "auth.setup", actor=body.username[:100], outcome="failure")
        return problem(request, 403, "setup_code_invalid", "That setup code is not right")
    username = normalize_username(body.username)
    if not is_valid_username(username):
        raise AppError(
            422, "username_invalid", "Use 3 to 64 letters, digits, dots, dashes or underscores"
        )
    if reason := password_problem(body.password, username):
        raise AppError(422, "password_rejected", reason)
    user = await create_user(
        session,
        username=username,
        display_name=body.display_name,
        role=Role.ADMIN,
        password=body.password,
    )
    settings, now = get_settings(), utc_now()
    user.last_sign_in_at = now
    token, _ = await start_session(
        session,
        settings,
        user,
        now,
        address=audit.client_address(request),
        agent=audit.client_agent(request),
    )
    audit.record(session, request, "auth.setup", actor=user, target=("user", user.id))
    _gate(request).close()
    set_cookie(response, settings, token)
    return UserOut.model_validate(user)


@router.post("/login", dependencies=[Depends(PUBLIC)], response_model=UserOut)
async def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep
) -> UserOut | JSONResponse:
    """Sign in. Every kind of failure gets the same answer."""
    limiter, address = _limiter(request), audit.client_address(request) or "unknown"
    if wait := limiter.blocked_for(address):
        return too_many(request, wait)
    settings, now = get_settings(), utc_now()
    username = normalize_username(body.username)
    user = await authenticate(session, settings, username, body.password, now)
    if user is None:
        limiter.record_failure(address)
        known = await find_user(session, username)
        audit.record(
            session,
            request,
            "auth.lockout" if known and is_locked(known, now) else "auth.login",
            actor=username[:100],
            outcome="failure",
        )
        return problem(request, 401, "invalid_credentials", GENERIC_FAILURE)
    token, _ = await start_session(
        session,
        settings,
        user,
        now,
        address=audit.client_address(request),
        agent=audit.client_agent(request),
    )
    audit.record(session, request, "auth.login", actor=user)
    set_cookie(response, settings, token)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, who: SignedIn, session: SessionDep) -> Response:
    """Sign out of this browser."""
    who.session.revoked_at = utc_now()
    audit.record(session, request, "auth.logout", actor=who.user)
    response = Response(status_code=204)
    clear_cookie(response, get_settings())
    return response


@router.get("/me")
async def me(who: SignedIn) -> UserOut:
    """Who is signed in."""
    return UserOut.model_validate(who.user)


@router.post("/password", status_code=204)
async def change_password(
    body: PasswordChangeIn, request: Request, who: SignedIn, session: SessionDep
) -> Response:
    """Change your own password. Your other browsers are signed out."""
    limiter, address = _limiter(request), audit.client_address(request) or "unknown"
    if wait := limiter.blocked_for(address):
        return too_many(request, wait)
    user = who.user
    correct, _ = await verify_password(user.password_hash, body.current_password)
    if not correct:
        limiter.record_failure(address)
        audit.record(session, request, "auth.password", actor=user, outcome="failure")
        return problem(request, 403, "current_password_wrong", "The current password is wrong")
    if reason := password_problem(body.new_password, user.username):
        raise AppError(422, "password_rejected", reason)
    now = utc_now()
    await set_password(user, body.new_password)
    await revoke_sessions(session, user.id, now, keep=who.session.id)
    audit.record(session, request, "auth.password", actor=user)
    return Response(status_code=204)


@router.get("/sessions")
async def sessions(who: SignedIn, session: SessionDep) -> list[SessionOut]:
    """Where you are signed in."""
    found = await live_sessions(session, get_settings(), who.user.id, utc_now())
    return [
        SessionOut.model_validate(one).model_copy(update={"current": one.id == who.session.id})
        for one in found
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def end_session(
    session_id: uuid.UUID, request: Request, who: SignedIn, session: SessionDep
) -> Response:
    """Sign out one of your browsers."""
    target = await session.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == who.user.id,
            AuthSession.revoked_at.is_(None),
        )
    )
    if target is None:
        raise AppError(404, "not_found", "There is no such session")
    target.revoked_at = utc_now()
    audit.record(
        session, request, "auth.session_end", actor=who.user, target=("session", target.id)
    )
    return Response(status_code=204)

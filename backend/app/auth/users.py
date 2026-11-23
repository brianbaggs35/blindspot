"""Accounts, for administrators: create, change, reset a password, sign out, delete."""

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import audit
from app.auth.deps import ADMIN, Admin
from app.auth.passwords import password_problem
from app.auth.schemas import PasswordResetIn, UserCreateIn, UserOut, UserUpdateIn
from app.auth.service import (
    create_user,
    is_valid_username,
    normalize_username,
    revoke_sessions,
    set_password,
)
from app.db.base import utc_now
from app.db.models import User
from app.db.session import SessionDep
from app.errors import AppError

router = APIRouter(prefix="/api/users", tags=["users"])


async def _get(session: SessionDep, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise AppError(404, "not_found", "There is no such account")
    return user


def _not_yourself(who: Admin, user: User, what: str) -> None:
    if who.user.id == user.id:
        raise AppError(409, "own_account", f"You cannot {what} your own account here")


@router.get("", dependencies=[Depends(ADMIN)])
async def list_users(session: SessionDep) -> list[UserOut]:
    """Every account."""
    rows = await session.scalars(select(User).order_by(User.created_at))
    return [UserOut.model_validate(row) for row in rows]


@router.post("", status_code=201)
async def add_user(
    body: UserCreateIn, request: Request, who: Admin, session: SessionDep
) -> UserOut:
    """Add an account."""
    username = normalize_username(body.username)
    if not is_valid_username(username):
        raise AppError(
            422, "username_invalid", "Use 3 to 64 letters, digits, dots, dashes or underscores"
        )
    if reason := password_problem(body.password, username):
        raise AppError(422, "password_rejected", reason)
    try:
        async with session.begin_nested():
            user = await create_user(
                session,
                username=username,
                display_name=body.display_name,
                role=body.role,
                password=body.password,
            )
    except IntegrityError:
        raise AppError(409, "username_taken", "That username is already used") from None
    audit.record(
        session,
        request,
        "user.create",
        actor=who.user,
        target=("user", user.id),
        detail={"username": username, "role": body.role.value},
    )
    return UserOut.model_validate(user)


@router.patch("/{user_id}")
async def change_user(
    user_id: uuid.UUID, body: UserUpdateIn, request: Request, who: Admin, session: SessionDep
) -> UserOut:
    """Change the name, the role or whether the account can sign in."""
    user = await _get(session, user_id)
    changes = body.model_dump(exclude_none=True)
    if "role" in changes or "is_active" in changes:
        _not_yourself(who, user, "change the role or status of")
    if body.display_name is not None:
        user.display_name = body.display_name or user.username
    if body.role is not None:
        user.role = body.role.value
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            await revoke_sessions(session, user.id, utc_now())
    audit.record(
        session,
        request,
        "user.update",
        actor=who.user,
        target=("user", user.id),
        detail={key: str(value) for key, value in changes.items()},
    )
    return UserOut.model_validate(user)


@router.post("/{user_id}/password", status_code=204)
async def reset_password(
    user_id: uuid.UUID, body: PasswordResetIn, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Set a new password for an account. Its browsers are signed out."""
    user = await _get(session, user_id)
    if reason := password_problem(body.password, user.username):
        raise AppError(422, "password_rejected", reason)
    await set_password(session, user, body.password)
    await revoke_sessions(session, user.id, utc_now())
    audit.record(session, request, "user.password_reset", actor=who.user, target=("user", user.id))
    return Response(status_code=204)


@router.post("/{user_id}/sign-out", status_code=204)
async def sign_out(
    user_id: uuid.UUID, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Sign an account out of every browser."""
    user = await _get(session, user_id)
    await revoke_sessions(session, user.id, utc_now())
    audit.record(session, request, "user.sign_out", actor=who.user, target=("user", user.id))
    return Response(status_code=204)


@router.delete("/{user_id}", status_code=204)
async def remove_user(
    user_id: uuid.UUID, request: Request, who: Admin, session: SessionDep
) -> Response:
    """Remove an account. What it did stays in the audit trail."""
    user = await _get(session, user_id)
    _not_yourself(who, user, "delete")
    await session.delete(user)
    audit.record(
        session,
        request,
        "user.delete",
        actor=who.user,
        target=("user", user.id),
        detail={"username": user.username},
    )
    return Response(status_code=204)

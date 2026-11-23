"""The rules for accounts and sessions, apart from the web layer."""

import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, spend_the_same_time, verify_password
from app.auth.tokens import hash_token, new_token
from app.config import Settings
from app.db.base import utc_now
from app.db.models import AuthSession, Role, User

USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
# A session's last-seen time is only rewritten when it is this old, so a busy page is not a write
# for every request.
TOUCH_AFTER = timedelta(seconds=60)


def normalize_username(raw: str) -> str:
    """The form a username is stored and looked up in."""
    return raw.strip().casefold()


def is_valid_username(username: str) -> bool:
    """Whether a normalized username is allowed."""
    return USERNAME.fullmatch(username) is not None


async def count_users(session: AsyncSession) -> int:
    """How many accounts exist."""
    return await session.scalar(select(func.count()).select_from(User)) or 0


async def find_user(session: AsyncSession, username: str) -> User | None:
    """The account with this (normalized) username."""
    return await session.scalar(select(User).where(User.username == username))


async def create_user(
    session: AsyncSession, *, username: str, display_name: str, role: Role, password: str
) -> User:
    """Add an account."""
    user = User(
        username=username,
        display_name=display_name.strip() or username,
        role=role.value,
        password_hash=await hash_password(password),
    )
    session.add(user)
    await session.flush()
    return user


async def set_password(user: User, password: str) -> None:
    """Change an account's password and forget any lockout."""
    user.password_hash = await hash_password(password)
    user.password_changed_at = utc_now()
    user.failed_attempts = 0
    user.locked_until = None


def is_locked(user: User, now: datetime) -> bool:
    """Whether the account is locked at the moment."""
    return user.locked_until is not None and user.locked_until > now


async def authenticate(
    session: AsyncSession, settings: Settings, username: str, password: str, now: datetime
) -> User | None:
    """The account for a username and password, or None.

    Every failure looks the same to the caller: an unknown name, a wrong password, a locked or a
    disabled account. An unknown name still costs a hash, so timing does not give it away.
    """
    user = await find_user(session, username)
    if user is None:
        await spend_the_same_time(password)
        return None
    if is_locked(user, now) or not user.is_active:
        await spend_the_same_time(password)
        return None
    correct, stale = await verify_password(user.password_hash, password)
    if not correct:
        user.failed_attempts += 1
        if user.failed_attempts >= settings.lockout_attempts:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_attempts = 0
        return None
    if stale:
        user.password_hash = await hash_password(password)
    user.failed_attempts = 0
    user.locked_until = None
    user.last_sign_in_at = now
    return user


async def start_session(
    session: AsyncSession,
    settings: Settings,
    user: User,
    now: datetime,
    *,
    address: str | None,
    agent: str | None,
) -> tuple[str, AuthSession]:
    """Sign a user in: the token for the cookie and the stored session."""
    token = new_token()
    stored = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_total_hours),
        ip_address=address,
        user_agent=agent,
    )
    session.add(stored)
    await session.flush()
    return token, stored


async def session_for_token(
    session: AsyncSession, settings: Settings, token: str, now: datetime
) -> tuple[AuthSession, User] | None:
    """The live session and its user for a cookie's token, or None when it is unknown, revoked,
    idle for too long, past its total time, or its account is disabled."""
    row = (
        await session.execute(
            select(AuthSession, User)
            .join(User, User.id == AuthSession.user_id)
            .where(AuthSession.token_hash == hash_token(token))
        )
    ).first()
    if row is None:
        return None
    found, user = row
    idle_until = found.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    if found.revoked_at is not None or found.expires_at <= now or idle_until <= now:
        return None
    if not user.is_active:
        return None
    if now - found.last_seen_at >= TOUCH_AFTER:
        found.last_seen_at = now
    return found, user


async def revoke_sessions(
    session: AsyncSession, user_id: uuid.UUID, now: datetime, *, keep: uuid.UUID | None = None
) -> int:
    """Sign a user out everywhere (except the session `keep`). Returns how many were live."""
    statement = (
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if keep is not None:
        statement = statement.where(AuthSession.id != keep)
    result = await session.execute(statement)
    return int(getattr(result, "rowcount", 0) or 0)


async def live_sessions(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID, now: datetime
) -> list[AuthSession]:
    """A user's sessions that still work, newest first."""
    idle = now - timedelta(minutes=settings.session_idle_minutes)
    rows = await session.scalars(
        select(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
            AuthSession.last_seen_at > idle,
        )
        .order_by(AuthSession.created_at.desc())
    )
    return list(rows)

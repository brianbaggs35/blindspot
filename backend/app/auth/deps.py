"""Who is making the request, and what each route requires.

Every route names its policy, so none is open by accident:

- `Anyone` (public): no sign-in needed; gives the signed-in user when there is one.
- `SignedIn`: any signed-in account, a viewer included. Used for reading, and for what a person
  does to their own account (sign out, change their password, end their own sessions).
- `Admin`: an administrator. Everything that changes the app's data or settings needs it, so a
  viewer is read-only.

A test checks that every route in the app has exactly one of these.
"""

from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Request

from app.auth.service import session_for_token
from app.config import get_settings
from app.db.base import utc_now
from app.db.models import AuthSession, Role, User
from app.db.session import SessionDep
from app.errors import AppError

COOKIE_NAME = "blindspot_session"


@dataclass(frozen=True)
class Principal:
    """The person making a request and the session they are using."""

    user: User
    session: AuthSession


async def find_principal(request: Request, session: SessionDep) -> Principal | None:
    """The signed-in person, found from the cookie, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    found = await session_for_token(session, get_settings(), token, utc_now())
    return Principal(user=found[1], session=found[0]) if found else None


class Policy:
    """What a route needs of the person calling it."""

    def __init__(self, name: Literal["public", "user", "admin"]) -> None:
        self.name = name

    async def __call__(self, request: Request, session: SessionDep) -> Principal | None:
        principal = await find_principal(request, session)
        if self.name == "public":
            return principal
        if principal is None:
            raise AppError(401, "not_signed_in", "Sign in to continue")
        if self.name == "admin" and principal.user.role != Role.ADMIN.value:
            raise AppError(403, "read_only", "Your account can look but not change things")
        return principal


PUBLIC = Policy("public")
USER = Policy("user")
ADMIN = Policy("admin")

Anyone = Annotated[Principal | None, Depends(PUBLIC)]
SignedIn = Annotated[Principal, Depends(USER)]
Admin = Annotated[Principal, Depends(ADMIN)]

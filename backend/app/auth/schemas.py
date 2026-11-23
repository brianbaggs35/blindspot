"""What the account routes accept and return."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.db.models import Role

Password = Annotated[str, Field(min_length=1, max_length=1024)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class Strict(BaseModel):
    """A request body with no extra fields."""

    model_config = ConfigDict(extra="forbid")


class UserOut(BaseModel):
    """An account, without anything secret."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    role: Role
    is_active: bool
    last_sign_in_at: datetime | None
    created_at: datetime
    terms_accepted: bool


class Status(BaseModel):
    """What the sign-in page needs to know."""

    setup_required: bool
    user: UserOut | None


class SetupIn(Strict):
    """First-run setup."""

    setup_code: Annotated[str, Field(min_length=1, max_length=64)]
    username: Username
    display_name: DisplayName = ""
    password: Password


class LoginIn(Strict):
    """A sign-in."""

    username: Username
    password: Password


class PasswordChangeIn(Strict):
    """Change your own password."""

    current_password: Password
    new_password: Password


class SessionOut(BaseModel):
    """A signed-in browser, as its owner sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    current: bool = False


class UserCreateIn(Strict):
    """A new account."""

    username: Username
    display_name: DisplayName = ""
    role: Role = Role.VIEWER
    password: Password


class UserUpdateIn(Strict):
    """Changes to an account; leave out what stays."""

    display_name: DisplayName | None = None
    role: Role | None = None
    is_active: bool | None = None


class PasswordResetIn(Strict):
    """A new password set by an administrator."""

    password: Password


class AuditOut(BaseModel):
    """One line of the audit trail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    actor_id: uuid.UUID | None
    actor_name: str | None
    action: str
    outcome: str
    target_type: str | None
    target_id: str | None
    ip_address: str | None
    user_agent: str | None
    detail: dict[str, Any] | None


class AuditPage(BaseModel):
    """A page of the audit trail, newest first."""

    items: list[AuditOut]
    next_before: uuid.UUID | None

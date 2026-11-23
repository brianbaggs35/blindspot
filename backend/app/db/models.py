"""The tables. Later changes add models here and a migration in `migrations/versions`."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func, text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, utc_now
from app.vault.seal import Purpose
from app.vault.types import SealedString

__all__ = ["AppSetting", "AuditEvent", "AuthSession", "Base", "Role", "User"]


class AppSetting(Base):
    """One named setting that the administrators can change in the app."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )


class Role(StrEnum):
    """What a person may do. Viewers read; administrators read and change."""

    ADMIN = "admin"
    VIEWER = "viewer"


class User(UUIDPrimaryKey, Timestamps, Base):
    """A person who can sign in. Never deleted by the app's own history: see AuditEvent."""

    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'viewer')", name="role"),
        CheckConstraint("failed_attempts >= 0", name="failed_attempts"),
    )

    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16), default=Role.VIEWER.value)
    # The Argon2id hash, sealed by the vault on top of being a hash.
    password_hash: Mapped[str] = mapped_column(SealedString(Purpose.AUTH))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    failed_attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AuthSession(UUIDPrimaryKey, Base):
    """One signed-in browser. The cookie holds a random token; only its SHA-256 is stored, so a
    copy of the database cannot be used to sign in."""

    __tablename__ = "auth_session"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(256), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AuditEvent(UUIDPrimaryKey, Base):
    """Who did what, when and from where. Rows are only ever added. The actor is kept by name as
    well as id, so the trail still reads after an account is removed."""

    __tablename__ = "audit_event"
    __table_args__ = (CheckConstraint("outcome IN ('success', 'failure')", name="outcome"),)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(100), default=None)
    action: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(8), default="success")
    target_type: Mapped[str | None] = mapped_column(String(32), default=None)
    target_id: Mapped[str | None] = mapped_column(String(64), default=None)
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(256), default=None)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

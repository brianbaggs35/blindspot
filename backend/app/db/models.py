"""The tables. Later changes add models here and a migration in `migrations/versions`."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, utc_now
from app.vault.seal import Purpose
from app.vault.types import SealedString

__all__ = [
    "AiModel",
    "AiProvider",
    "AiRoleDefault",
    "AppSetting",
    "AuditEvent",
    "AuthSession",
    "Base",
    "Methodology",
    "MethodologyVersion",
    "Passkey",
    "PlaybookOverride",
    "Role",
    "UsageLedger",
    "User",
    "WebAuthnChallenge",
]


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


class Passkey(UUIDPrimaryKey, Base):
    """A passkey (WebAuthn credential) that lets a person sign in. Only the public key is kept."""

    __tablename__ = "passkey"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    transports: Mapped[list[str]] = mapped_column(JSONB, default=list)
    name: Mapped[str] = mapped_column(String(64))
    backup_eligible: Mapped[bool] = mapped_column(default=False)
    backed_up: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class WebAuthnChallenge(UUIDPrimaryKey, Base):
    """A challenge handed to a browser. It works once and for a few minutes."""

    __tablename__ = "webauthn_challenge"

    challenge: Mapped[bytes] = mapped_column(LargeBinary)
    purpose: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AiProvider(UUIDPrimaryKey, Timestamps, Base):
    """A place models come from: a hosted API or an Ollama server. The key is sealed; the last
    four characters are kept apart so the page can show which key is in use."""

    __tablename__ = "ai_provider"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('anthropic', 'openai', 'ollama-local', 'ollama-cloud')", name="kind"
        ),
        CheckConstraint("monthly_budget_usd IS NULL OR monthly_budget_usd >= 0", name="budget"),
    )

    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64), unique=True)
    base_url: Mapped[str] = mapped_column(String(300))
    api_key: Mapped[str | None] = mapped_column(SealedString(Purpose.PROVIDERS), default=None)
    api_key_last4: Mapped[str | None] = mapped_column(String(4), default=None)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=true())
    monthly_budget_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), default=None)
    hard_stop: Mapped[bool] = mapped_column(default=False, server_default=false())


class AiModel(UUIDPrimaryKey, Timestamps, Base):
    """A model of a provider that can be chosen. Price columns are overrides of the catalog (USD
    per million tokens); empty means "use the catalog"."""

    __tablename__ = "ai_model"
    __table_args__ = (UniqueConstraint("provider_id", "model_id"),)

    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_provider.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200))
    context_tokens: Mapped[int | None] = mapped_column(BigInteger, default=None)
    max_output_tokens: Mapped[int | None] = mapped_column(BigInteger, default=None)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, default=list)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=true())
    price_input: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), default=None)
    price_output: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), default=None)
    price_cache_read: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), default=None)
    price_cache_write: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), default=None)
    price_cache_write_long: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), default=None)


class AiRoleDefault(Base):
    """The model used by default for one agent role."""

    __tablename__ = "ai_role_default"

    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    model_ref: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_model.id", ondelete="CASCADE")
    )


class UsageLedger(UUIDPrimaryKey, Base):
    """One model call: what it used and what it cost. Rows are only added. The provider and model
    are kept by name too, so the history reads after a provider is removed. A cost of NULL means
    the price was not known (the tokens are still real)."""

    __tablename__ = "usage_ledger"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), index=True
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_provider.id", ondelete="SET NULL"), default=None, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(200))
    agent: Mapped[str | None] = mapped_column(String(100), default=None)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None, index=True)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_write_long_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    thinking_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), default=None)


class Methodology(Timestamps, Base):
    """A methodology a pentest can follow, such as WSTG. Its content is in `MethodologyVersion`;
    the newest version is the one in use."""

    __tablename__ = "methodology"
    __table_args__ = (CheckConstraint("origin IN ('bundled', 'folder')", name="origin"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(500))
    license: Mapped[str] = mapped_column(String(200))
    origin: Mapped[str] = mapped_column(String(16))
    enabled: Mapped[bool] = mapped_column(default=True, server_default=true())


class MethodologyVersion(UUIDPrimaryKey, Base):
    """One snapshot of a methodology. Snapshots are only added, so a pentest can say exactly which
    tests it was run against. `number` counts up from 1 for each methodology."""

    __tablename__ = "methodology_version"
    __table_args__ = (UniqueConstraint("methodology_id", "number"),)

    methodology_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("methodology.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(40))
    content_hash: Mapped[str] = mapped_column(String(64))
    spec: Mapped[Any] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)


class PlaybookOverride(Base):
    """A playbook an administrator wrote to replace the one a test came with."""

    __tablename__ = "playbook_override"

    methodology_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("methodology.id", ondelete="CASCADE"), primary_key=True
    )
    test_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    playbook: Mapped[Any] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )

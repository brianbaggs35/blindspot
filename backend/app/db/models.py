"""The tables. Later changes add models here and a migration in `migrations/versions`."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedBy, SoftDelete, Timestamps, UUIDPrimaryKey, utc_now
from app.terms.text import VERSION as TERMS_VERSION
from app.vault.seal import Purpose
from app.vault.types import SealedJSON, SealedString

METHODOLOGY_ID = "methodology.id"
PENTEST_ID = "pentest.id"
EMPTY_LIST = text("'[]'::jsonb")
EMPTY_OBJECT = text("'{}'::jsonb")
SET_NULL = "SET NULL"

__all__ = [
    "AgentPrompt",
    "AiModel",
    "AiProvider",
    "AiRoleDefault",
    "AppSetting",
    "AuditEvent",
    "AuthSession",
    "Base",
    "Finding",
    "FindingEvent",
    "FindingEvidence",
    "Methodology",
    "MethodologyVersion",
    "Mission",
    "MissionEvent",
    "MissionFact",
    "MissionStep",
    "MissionTask",
    "Passkey",
    "Pentest",
    "PentestAccount",
    "PentestAttestation",
    "PentestCheck",
    "PentestLetter",
    "PentestResult",
    "PlaybookOverride",
    "Role",
    "ToolGrant",
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
    # The version of the terms of use this person accepted, and when. It is compared with the
    # current version (a fingerprint of the text), so changed words are asked for again.
    terms_version: Mapped[str | None] = mapped_column(String(16), default=None)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    @property
    def terms_accepted(self) -> bool:
        """Whether the terms of use, as they are now, were accepted."""
        return self.terms_version == TERMS_VERSION


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
        Uuid, ForeignKey("ai_provider.id", ondelete=SET_NULL), default=None, index=True
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
        String(32), ForeignKey(METHODOLOGY_ID, ondelete="CASCADE"), index=True
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
        String(32), ForeignKey(METHODOLOGY_ID, ondelete="CASCADE"), primary_key=True
    )
    test_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    playbook: Mapped[Any] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )


class PentestStatus(StrEnum):
    """Where a pentest is in its life. Only `draft` is used until the authorization gate arrives."""

    DRAFT = "draft"
    AUTHORIZED = "authorized"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETE = "complete"


class CheckStatus(StrEnum):
    """Where one test of a pentest stands. A test nobody has touched is `todo`, or
    `not_applicable` when the target lacks a feature it needs."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FINDING = "finding"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


class Box(StrEnum):
    """How much the testers know going in."""

    BLACK = "black"
    GREY = "grey"
    WHITE = "white"


class Pentest(UUIDPrimaryKey, Timestamps, SoftDelete, CreatedBy, Base):
    """One engagement: what is to be tested, under what rules and by which methodology. The scope
    and the rules are stored as written; the compiled allow-list is rebuilt from them whenever it
    is needed, so a change to how scope is read applies to old pentests too."""

    __tablename__ = "pentest"
    __table_args__ = (
        CheckConstraint("box IN ('black', 'grey', 'white')", name="box"),
        CheckConstraint(
            "status IN ('draft', 'authorized', 'running', 'paused', 'complete')", name="status"
        ),
    )

    name: Mapped[str] = mapped_column(String(120))
    client: Mapped[str | None] = mapped_column(String(120), default=None)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    methodology_id: Mapped[str] = mapped_column(
        String(32), ForeignKey(METHODOLOGY_ID, ondelete="RESTRICT"), index=True
    )
    # The snapshot of the methodology this pentest was made against.
    methodology_version: Mapped[int] = mapped_column(Integer)
    box: Mapped[str] = mapped_column(String(8), default=Box.BLACK.value)
    status: Mapped[str] = mapped_column(String(16), default=PentestStatus.DRAFT.value)
    scope: Mapped[Any] = mapped_column(JSONB)
    rules: Mapped[Any] = mapped_column(JSONB)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # What the target shows (such as "saml" or "upload"), so the checklist can tell which tests
    # apply. It does not change what may be touched, so it is not part of the attestation.
    features: Mapped[Any] = mapped_column(JSONB, default=list, server_default=EMPTY_LIST)


class PentestAccount(UUIDPrimaryKey, Timestamps, Base):
    """An account on the target that agents may sign in with. The secret is sealed and never
    returned by the API."""

    __tablename__ = "pentest_account"
    __table_args__ = (UniqueConstraint("pentest_id", "label"),)

    pentest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(PENTEST_ID, ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(80))
    username: Mapped[str] = mapped_column(String(200))
    role_hint: Mapped[str] = mapped_column(String(80), default="", server_default="")
    secret: Mapped[str | None] = mapped_column(
        SealedString(Purpose.TARGET_CREDENTIALS), default=None
    )


class PentestAttestation(UUIDPrimaryKey, Base):
    """A person's written statement that they have permission to test everything in scope. Rows
    are only added: a withdrawn attestation keeps its row, marked with when and why. `scope_hash`
    fingerprints the scope and rules that were attested, so a change to either is noticed."""

    __tablename__ = "pentest_attestation"

    pentest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(PENTEST_ID, ondelete="CASCADE"), index=True
    )
    attested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    attested_by_name: Mapped[str] = mapped_column(String(64))
    attested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
    text_version: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    confirmation: Mapped[str] = mapped_column(String(120))
    scope_hash: Mapped[str] = mapped_column(String(64))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    withdrawn_reason: Mapped[str | None] = mapped_column(String(200), default=None)


class PentestLetter(Base):
    """The signed authorization letter for a pentest, kept as a file under the data directory.
    There is at most one; uploading another replaces it."""

    __tablename__ = "pentest_letter"

    pentest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(PENTEST_ID, ondelete="CASCADE"), primary_key=True
    )
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(40))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    stored_name: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class PentestCheck(UUIDPrimaryKey, Timestamps, Base):
    """What a person or an agent recorded for one test of a pentest. A row exists once somebody
    has touched the test (or added a custom one); the rest of the checklist comes from the
    methodology snapshot the pentest is pinned to."""

    __tablename__ = "pentest_check"
    __table_args__ = (
        UniqueConstraint("pentest_id", "test_id"),
        CheckConstraint(
            "status IN ('todo', 'in_progress', 'passed', 'finding', 'blocked', 'not_applicable')",
            name="status",
        ),
    )

    pentest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(PENTEST_ID, ondelete="CASCADE"), index=True
    )
    test_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=CheckStatus.TODO.value)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    evidence: Mapped[Any] = mapped_column(JSONB, default=list, server_default=EMPTY_LIST)
    # A custom test belongs to this pentest alone: it has a name and a category of its own.
    custom: Mapped[bool] = mapped_column(default=False, server_default=false())
    name: Mapped[str | None] = mapped_column(String(200), default=None)
    category: Mapped[str | None] = mapped_column(String(80), default=None)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)


class PentestResult(UUIDPrimaryKey, Timestamps, SoftDelete, CreatedBy, Base):
    """What one tool run, one import or one note put on a pentest's record. `normalized` is the
    tool's output in the one result shape (without any secret); `raw_output` is what the tool
    printed and `credentials` what it found that must stay secret, both sealed. Facts a list needs
    to filter on (the tool, the worst severity) are columns of their own."""

    __tablename__ = "pentest_result"
    __table_args__ = (
        CheckConstraint("source IN ('tool', 'import', 'manual')", name="source"),
        CheckConstraint("status IN ('ok', 'failed', 'manual')", name="status"),
        CheckConstraint(
            "top_severity IS NULL OR top_severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="top_severity",
        ),
    )

    pentest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(PENTEST_ID, ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(200))
    tool_id: Mapped[str | None] = mapped_column(String(32), default=None)
    agent_role: Mapped[str | None] = mapped_column(String(24), default=None)
    test_id: Mapped[str | None] = mapped_column(String(64), default=None)
    parser: Mapped[str | None] = mapped_column(String(32), default=None)
    command: Mapped[Any] = mapped_column(JSONB, default=list, server_default=EMPTY_LIST)
    exit_code: Mapped[int | None] = mapped_column(Integer, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), index=True
    )
    normalized: Mapped[Any | None] = mapped_column(JSONB, default=None)
    top_severity: Mapped[str | None] = mapped_column(String(8), default=None)
    issue_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    raw_output: Mapped[str | None] = mapped_column(SealedString(Purpose.EVIDENCE), default=None)
    credentials: Mapped[Any | None] = mapped_column(
        SealedJSON(Purpose.DISCOVERED_CREDENTIALS), default=None
    )
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    tags: Mapped[Any] = mapped_column(JSONB, default=list, server_default=EMPTY_LIST)


class CustomTool(UUIDPrimaryKey, Timestamps, CreatedBy, Base):
    """A tool an administrator defined. `manifest` is the validated manifest as JSON, and the id
    always starts with `x.` so it can never replace a bundled tool."""

    __tablename__ = "custom_tool"

    tool_id: Mapped[str] = mapped_column(String(32), unique=True)
    manifest: Mapped[Any] = mapped_column(JSONB)


class ToolSetting(Base):
    """How one tool is run: whether it is on, where (Local or Docker, or whatever the global
    default says), what to run there and the limits it runs under. A missing value means the
    tool's manifest decides. The row of a tool that was never set up does not exist."""

    __tablename__ = "tool_setting"
    __table_args__ = (
        CheckConstraint("mode IS NULL OR mode IN ('local', 'docker')", name="mode"),
        CheckConstraint(
            "max_risk IS NULL OR max_risk IN ('passive', 'active', 'intrusive', 'destructive')",
            name="max_risk",
        ),
    )

    tool_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    mode: Mapped[str | None] = mapped_column(String(6), default=None)
    binary_path: Mapped[str | None] = mapped_column(String(300), default=None)
    image: Mapped[str | None] = mapped_column(String(300), default=None)
    cpus: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=None)
    memory_mb: Mapped[int | None] = mapped_column(Integer, default=None)
    timeout_s: Mapped[int | None] = mapped_column(Integer, default=None)
    max_output_mb: Mapped[int | None] = mapped_column(Integer, default=None)
    rate_per_s: Mapped[int | None] = mapped_column(Integer, default=None)
    max_risk: Mapped[str | None] = mapped_column(String(12), default=None)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )


class ToolGrant(UUIDPrimaryKey, Timestamps, CreatedBy, Base):
    """What an agent role may do with a tool: up to a risk class, on its own, after asking or not
    at all. `role` and `tool` are `*` for any. `pentest_id` limits it to one pentest and is empty
    for every pentest. Only administrators write these, never a model."""

    __tablename__ = "tool_grant"
    __table_args__ = (
        UniqueConstraint("role", "tool", "pentest_id", postgresql_nulls_not_distinct=True),
        CheckConstraint(
            "max_risk IN ('passive', 'active', 'intrusive', 'destructive')", name="max_risk"
        ),
        CheckConstraint("mode IN ('auto', 'ask', 'deny')", name="mode"),
    )

    role: Mapped[str] = mapped_column(String(24))
    tool: Mapped[str] = mapped_column(String(32))
    max_risk: Mapped[str] = mapped_column(String(12))
    mode: Mapped[str] = mapped_column(String(8))
    pentest_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(PENTEST_ID, ondelete="CASCADE"), default=None, index=True
    )


MISSION_ID = "mission.id"
MISSION_STATUSES = (
    "'pending', 'running', 'paused', 'cancelling', 'cancelled', 'completed', 'failed', 'stopped'"
)
TASK_STATUSES = "'pending', 'running', 'waiting', 'done', 'failed', 'skipped', 'cancelled'"
STEP_STATUSES = (
    "'planned', 'awaiting_approval', 'approved', 'running', 'done', 'failed', 'denied', "
    "'interrupted'"
)


class Mission(UUIDPrimaryKey, Timestamps, CreatedBy, Base):
    """One run of the agents over a pentest. The orchestrator is code that reads and writes these
    rows, so a mission survives a restart; the models only ever do the work of one step."""

    __tablename__ = "mission"
    __table_args__ = (CheckConstraint(f"status IN ({MISSION_STATUSES})", name="status"),)

    pentest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(PENTEST_ID, ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(12), default="pending", server_default="pending")
    budget: Mapped[Any] = mapped_column(JSONB)
    spent: Mapped[Any] = mapped_column(JSONB, default=dict, server_default=EMPTY_OBJECT)
    plan: Mapped[Any] = mapped_column(JSONB, default=dict, server_default=EMPTY_OBJECT)
    stop_reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    # The version of each agent prompt this mission started with, so a later change to a prompt
    # never changes a mission that is already running.
    prompts: Mapped[Any] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class MissionTask(UUIDPrimaryKey, Timestamps, Base):
    """A unit of work in the tree: the commander, a category, or one test. `phase` orders the
    categories (safer ones first); tasks of one phase may run side by side."""

    __tablename__ = "mission_task"
    __table_args__ = (
        CheckConstraint("kind IN ('commander', 'category', 'test')", name="kind"),
        CheckConstraint(f"status IN ({TASK_STATUSES})", name="status"),
    )

    mission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(MISSION_ID, ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    kind: Mapped[str] = mapped_column(String(10))
    ref: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    phase: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending")
    outcome: Mapped[Any | None] = mapped_column(JSONB, default=None)
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    spent: Mapped[Any] = mapped_column(JSONB, default=dict, server_default=EMPTY_OBJECT)


class MissionStep(UUIDPrimaryKey, Timestamps, Base):
    """One thing a test agent asked to do. A row is written before anything runs and is never run
    twice: `done` steps are read back, and a step that was running when the server stopped is
    marked `interrupted` and left for the agent to ask for again, visibly."""

    __tablename__ = "mission_step"
    __table_args__ = (
        UniqueConstraint("task_id", "seq"),
        CheckConstraint(f"status IN ({STEP_STATUSES})", name="status"),
    )

    mission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(MISSION_ID, ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("mission_task.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(18), default="planned", server_default="planned")
    tool: Mapped[str] = mapped_column(String(32))
    request: Mapped[Any] = mapped_column(JSONB)
    verdict: Mapped[Any | None] = mapped_column(JSONB, default=None)
    result_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    note: Mapped[str] = mapped_column(Text, default="", server_default="")


class MissionEvent(Base):
    """The mission's event log: what happened, in order. The web app reads it with a cursor."""

    __tablename__ = "mission_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(MISSION_ID, ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    type: Mapped[str] = mapped_column(String(32))
    data: Mapped[Any] = mapped_column(JSONB, default=dict, server_default=EMPTY_OBJECT)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class MissionFact(UUIDPrimaryKey, Base):
    """What the agents have learned about the target, with where it came from, so another agent
    can reuse it instead of finding it again."""

    __tablename__ = "mission_fact"
    __table_args__ = (
        CheckConstraint("confidence IN ('low', 'medium', 'high')", name="confidence"),
    )

    mission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(MISSION_ID, ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    subject: Mapped[str] = mapped_column(String(200))
    fact: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(6))
    source_result_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class AgentPrompt(UUIDPrimaryKey, CreatedBy, Base):
    """One version of an agent's instructions. Versions are only ever added: a mission points at
    the version it used, so what an agent was told stays readable after the prompt changes.
    Version 0 is the built-in text and is not stored."""

    __tablename__ = "agent_prompt"
    __table_args__ = (UniqueConstraint("agent", "version"),)

    agent: Mapped[str] = mapped_column(String(24))
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(String(200), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


FINDING_STATUSES = "'new', 'confirmed', 'false_positive', 'accepted_risk', 'fixed', 'retest_needed'"
SEVERITY_LEVELS = "'info', 'low', 'medium', 'high', 'critical'"
FINDING_ID = "finding.id"


class Finding(UUIDPrimaryKey, Timestamps, SoftDelete, CreatedBy, Base):
    """A weakness found in a pentest, scored, evidenced and followed until it is fixed. `number`
    counts the pentest's findings from 1 (it is what a person says: F-12). A finding that was
    merged into another is in the trash and says which one. The CVSS scores are worked out from
    the vectors by the server, never taken from a request."""

    __tablename__ = "finding"
    __table_args__ = (
        UniqueConstraint("pentest_id", "number"),
        CheckConstraint(f"status IN ({FINDING_STATUSES})", name="status"),
        CheckConstraint(f"severity IN ({SEVERITY_LEVELS})", name="severity"),
        CheckConstraint("confidence IN ('tentative', 'firm', 'certain')", name="confidence"),
        CheckConstraint("source IN ('manual', 'agent', 'result', 'import')", name="source"),
        CheckConstraint(
            "verification IN ('unverified', 'confirmed', 'unconfirmed')", name="verification"
        ),
    )

    pentest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(PENTEST_ID, ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    target: Mapped[str] = mapped_column(String(300), default="", server_default="")
    test_ids: Mapped[Any] = mapped_column(JSONB, default=list, server_default=EMPTY_LIST)
    cwe: Mapped[Any] = mapped_column(JSONB, default=list, server_default=EMPTY_LIST)
    owasp: Mapped[str | None] = mapped_column(String(12), default=None)
    cvss31_vector: Mapped[str | None] = mapped_column(String(200), default=None)
    cvss31_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), default=None)
    cvss4_vector: Mapped[str | None] = mapped_column(String(200), default=None)
    cvss4_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), default=None)
    severity: Mapped[str] = mapped_column(String(8), index=True)
    confidence: Mapped[str] = mapped_column(String(9), default="firm", server_default="firm")
    status: Mapped[str] = mapped_column(String(14), default="new", server_default="new")
    remediation: Mapped[str] = mapped_column(Text, default="", server_default="")
    references: Mapped[Any] = mapped_column(JSONB, default=list, server_default=EMPTY_LIST)
    source: Mapped[str] = mapped_column(String(8), default="manual", server_default="manual")
    result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("pentest_result.id", ondelete=SET_NULL), default=None
    )
    verification: Mapped[str] = mapped_column(
        String(12), default="unverified", server_default="unverified"
    )
    verified_by: Mapped[str | None] = mapped_column(String(8), default=None)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    merged_into: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(FINDING_ID, ondelete=SET_NULL), default=None
    )


class FindingEvidence(UUIDPrimaryKey, Timestamps, CreatedBy, Base):
    """What shows a finding is real: a tool result, a request and its response, a note or a
    screenshot. The text is sealed in the database, and what is `sealed` is hidden in lists and
    exports and shown only by a reveal that is written to the audit trail."""

    __tablename__ = "finding_evidence"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('result', 'request_response', 'note', 'screenshot')", name="kind"
        ),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(FINDING_ID, ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(SealedString(Purpose.EVIDENCE), default=None)
    mime: Mapped[str | None] = mapped_column(String(32), default=None)
    sealed: Mapped[bool] = mapped_column(default=False, server_default=false())
    result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("pentest_result.id", ondelete=SET_NULL), default=None
    )


class FindingEvent(UUIDPrimaryKey, Base):
    """One line of a finding's timeline: it was created, changed, moved to a status, verified,
    merged, or someone wrote a comment."""

    __tablename__ = "finding_event"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(FINDING_ID, ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(24))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    data: Mapped[Any] = mapped_column(JSONB, default=dict, server_default=EMPTY_OBJECT)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

"""Findings, their evidence and their timeline.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.ensure import drop_table_if_exists, ensure_index, ensure_table

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_NOW = sa.func.now()
_JSONB = postgresql.JSONB(astext_type=sa.Text())
_EMPTY_LIST = sa.text("'[]'::jsonb")
_EMPTY_OBJECT = sa.text("'{}'::jsonb")
_FINDING_ID = "finding.id"
_RESULT_ID = "pentest_result.id"
_STATUSES = "'new', 'confirmed', 'false_positive', 'accepted_risk', 'fixed', 'retest_needed'"
_SET_NULL = "SET NULL"


def upgrade() -> None:
    ensure_table(
        "finding",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("pentest_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("target", sa.String(300), server_default="", nullable=False),
        sa.Column("test_ids", _JSONB, server_default=_EMPTY_LIST, nullable=False),
        sa.Column("cwe", _JSONB, server_default=_EMPTY_LIST, nullable=False),
        sa.Column("owasp", sa.String(12), nullable=True),
        sa.Column("cvss31_vector", sa.String(200), nullable=True),
        sa.Column("cvss31_score", sa.Numeric(3, 1), nullable=True),
        sa.Column("cvss4_vector", sa.String(200), nullable=True),
        sa.Column("cvss4_score", sa.Numeric(3, 1), nullable=True),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("confidence", sa.String(9), server_default="firm", nullable=False),
        sa.Column("status", sa.String(14), server_default="new", nullable=False),
        sa.Column("remediation", sa.Text(), server_default="", nullable=False),
        sa.Column("references", _JSONB, server_default=_EMPTY_LIST, nullable=False),
        sa.Column("source", sa.String(8), server_default="manual", nullable=False),
        sa.Column("result_id", sa.Uuid(), nullable=True),
        sa.Column("verification", sa.String(12), server_default="unverified", nullable=False),
        sa.Column("verified_by", sa.String(8), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_into", sa.Uuid(), nullable=True),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name=op.f("ck_finding_status")),
        sa.CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name=op.f("ck_finding_severity"),
        ),
        sa.CheckConstraint(
            "confidence IN ('tentative', 'firm', 'certain')", name=op.f("ck_finding_confidence")
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'agent', 'result', 'import')", name=op.f("ck_finding_source")
        ),
        sa.CheckConstraint(
            "verification IN ('unverified', 'confirmed', 'unconfirmed')",
            name=op.f("ck_finding_verification"),
        ),
        sa.ForeignKeyConstraint(
            ["pentest_id"],
            ["pentest.id"],
            name=op.f("fk_finding_pentest_id_pentest"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            [_RESULT_ID],
            name=op.f("fk_finding_result_id_pentest_result"),
            ondelete=_SET_NULL,
        ),
        sa.ForeignKeyConstraint(
            ["merged_into"],
            [_FINDING_ID],
            name=op.f("fk_finding_merged_into_finding"),
            ondelete=_SET_NULL,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding")),
        sa.UniqueConstraint("pentest_id", "number", name=op.f("uq_finding_pentest_id")),
    )
    ensure_index("ix_finding_pentest_id", "finding", ["pentest_id"])
    ensure_index("ix_finding_severity", "finding", ["severity"])
    ensure_table(
        "finding_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("mime", sa.String(32), nullable=True),
        sa.Column("sealed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("result_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('result', 'request_response', 'note', 'screenshot')",
            name=op.f("ck_finding_evidence_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            [_FINDING_ID],
            name=op.f("fk_finding_evidence_finding_id_finding"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            [_RESULT_ID],
            name=op.f("fk_finding_evidence_result_id_pentest_result"),
            ondelete=_SET_NULL,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding_evidence")),
    )
    ensure_index("ix_finding_evidence_finding_id", "finding_evidence", ["finding_id"])
    ensure_table(
        "finding_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("data", _JSONB, server_default=_EMPTY_OBJECT, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            [_FINDING_ID],
            name=op.f("fk_finding_event_finding_id_finding"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding_event")),
    )
    ensure_index("ix_finding_event_finding_id", "finding_event", ["finding_id"])


def downgrade() -> None:
    drop_table_if_exists("finding_event")
    drop_table_if_exists("finding_evidence")
    drop_table_if_exists("finding")

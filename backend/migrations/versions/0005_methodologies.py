"""Methodologies: what a pentest checks, as versioned snapshots, and the playbooks changed by hand.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.db.ensure import drop_table_if_exists, ensure_index, ensure_table

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_NOW = sa.func.now()


def upgrade() -> None:
    ensure_table(
        "methodology",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("license", sa.String(200), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("origin IN ('bundled', 'folder')", name=op.f("ck_methodology_origin")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_methodology")),
    )
    ensure_table(
        "methodology_version",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("methodology_id", sa.String(32), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(40), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("spec", JSONB(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["methodology_id"],
            ["methodology.id"],
            name=op.f("fk_methodology_version_methodology_id_methodology"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_methodology_version")),
        sa.UniqueConstraint(
            "methodology_id", "number", name=op.f("uq_methodology_version_methodology_id")
        ),
    )
    ensure_index("ix_methodology_version_methodology_id", "methodology_version", ["methodology_id"])
    ensure_table(
        "playbook_override",
        sa.Column("methodology_id", sa.String(32), nullable=False),
        sa.Column("test_id", sa.String(64), nullable=False),
        sa.Column("playbook", JSONB(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["methodology_id"],
            ["methodology.id"],
            name=op.f("fk_playbook_override_methodology_id_methodology"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("methodology_id", "test_id", name=op.f("pk_playbook_override")),
    )


def downgrade() -> None:
    drop_table_if_exists("playbook_override")
    drop_table_if_exists("methodology_version")
    drop_table_if_exists("methodology")

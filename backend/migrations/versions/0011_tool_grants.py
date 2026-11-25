"""What each agent role may do with a tool, and the policy's off switch lives in app_setting.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

from app.db.ensure import drop_table_if_exists, ensure_index, ensure_table

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_NOW = sa.func.now()


def upgrade() -> None:
    ensure_table(
        "tool_grant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("tool", sa.String(32), nullable=False),
        sa.Column("max_risk", sa.String(12), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("pentest_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "max_risk IN ('passive', 'active', 'intrusive', 'destructive')",
            name=op.f("ck_tool_grant_max_risk"),
        ),
        sa.CheckConstraint("mode IN ('auto', 'ask', 'deny')", name=op.f("ck_tool_grant_mode")),
        sa.ForeignKeyConstraint(
            ["pentest_id"],
            ["pentest.id"],
            name=op.f("fk_tool_grant_pentest_id_pentest"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_grant")),
        sa.UniqueConstraint(
            "role",
            "tool",
            "pentest_id",
            name=op.f("uq_tool_grant_role"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    ensure_index("ix_tool_grant_pentest_id", "tool_grant", ["pentest_id"])


def downgrade() -> None:
    drop_table_if_exists("tool_grant")

"""The agent prompt versions, and the prompt versions a mission used.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.ensure import drop_column_if_exists, drop_table_if_exists, ensure_column, ensure_table

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_NOW = sa.func.now()
_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    ensure_column(
        "mission",
        sa.Column("prompts", _JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    ensure_table(
        "agent_prompt",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("agent", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("note", sa.String(200), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_prompt")),
        sa.UniqueConstraint("agent", "version", name=op.f("uq_agent_prompt_agent")),
    )


def downgrade() -> None:
    drop_table_if_exists("agent_prompt")
    drop_column_if_exists("mission", "prompts")

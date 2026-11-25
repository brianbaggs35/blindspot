"""Tools an administrator defined.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.db.ensure import drop_table_if_exists, ensure_table

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_NOW = sa.func.now()


def upgrade() -> None:
    ensure_table(
        "custom_tool",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("tool_id", sa.String(32), nullable=False),
        sa.Column("manifest", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custom_tool")),
        sa.UniqueConstraint("tool_id", name=op.f("uq_custom_tool_tool_id")),
    )


def downgrade() -> None:
    drop_table_if_exists("custom_tool")

"""How each tool is run: on or off, Local or Docker, what to run, and its limits.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

from app.db.ensure import drop_table_if_exists, ensure_table

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_NOW = sa.func.now()


def upgrade() -> None:
    ensure_table(
        "tool_setting",
        sa.Column("tool_id", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("mode", sa.String(6), nullable=True),
        sa.Column("binary_path", sa.String(300), nullable=True),
        sa.Column("image", sa.String(300), nullable=True),
        sa.Column("cpus", sa.Numeric(5, 2), nullable=True),
        sa.Column("memory_mb", sa.Integer(), nullable=True),
        sa.Column("timeout_s", sa.Integer(), nullable=True),
        sa.Column("max_output_mb", sa.Integer(), nullable=True),
        sa.Column("rate_per_s", sa.Integer(), nullable=True),
        sa.Column("max_risk", sa.String(12), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint(
            "mode IS NULL OR mode IN ('local', 'docker')", name=op.f("ck_tool_setting_mode")
        ),
        sa.CheckConstraint(
            "max_risk IS NULL OR max_risk IN ('passive', 'active', 'intrusive', 'destructive')",
            name=op.f("ck_tool_setting_max_risk"),
        ),
        sa.PrimaryKeyConstraint("tool_id", name=op.f("pk_tool_setting")),
    )


def downgrade() -> None:
    drop_table_if_exists("tool_setting")

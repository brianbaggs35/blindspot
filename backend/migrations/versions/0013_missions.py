"""The agent missions: the task tree, the steps, the event log and what the agents learned.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.ensure import drop_table_if_exists, ensure_index, ensure_table

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_NOW = sa.func.now()
_EMPTY_OBJECT = sa.text("'{}'::jsonb")
_JSONB = postgresql.JSONB(astext_type=sa.Text())
_MISSION_STATUSES = (
    "'pending', 'running', 'paused', 'cancelling', 'cancelled', 'completed', 'failed', 'stopped'"
)
_TASK_STATUSES = "'pending', 'running', 'waiting', 'done', 'failed', 'skipped', 'cancelled'"
_STEP_STATUSES = (
    "'planned', 'awaiting_approval', 'approved', 'running', 'done', 'failed', 'denied', "
    "'interrupted'"
)


def _stamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    ]


def upgrade() -> None:
    ensure_table(
        "mission",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_stamps(),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("pentest_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(12), server_default="pending", nullable=False),
        sa.Column("budget", _JSONB, nullable=False),
        sa.Column("spent", _JSONB, server_default=_EMPTY_OBJECT, nullable=False),
        sa.Column("plan", _JSONB, server_default=_EMPTY_OBJECT, nullable=False),
        sa.Column("stop_reason", sa.Text(), server_default="", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"status IN ({_MISSION_STATUSES})", name=op.f("ck_mission_status")),
        sa.ForeignKeyConstraint(
            ["pentest_id"],
            ["pentest.id"],
            name=op.f("fk_mission_pentest_id_pentest"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mission")),
    )
    ensure_index("ix_mission_pentest_id", "mission", ["pentest_id"])
    ensure_table(
        "mission_task",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_stamps(),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("ref", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phase", sa.Integer(), server_default="0", nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(10), server_default="pending", nullable=False),
        sa.Column("outcome", _JSONB, nullable=True),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("spent", _JSONB, server_default=_EMPTY_OBJECT, nullable=False),
        sa.CheckConstraint(
            "kind IN ('commander', 'category', 'test')", name=op.f("ck_mission_task_kind")
        ),
        sa.CheckConstraint(f"status IN ({_TASK_STATUSES})", name=op.f("ck_mission_task_status")),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["mission.id"],
            name=op.f("fk_mission_task_mission_id_mission"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mission_task")),
    )
    ensure_index("ix_mission_task_mission_id", "mission_task", ["mission_id"])
    ensure_table(
        "mission_step",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_stamps(),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(18), server_default="planned", nullable=False),
        sa.Column("tool", sa.String(32), nullable=False),
        sa.Column("request", _JSONB, nullable=False),
        sa.Column("verdict", _JSONB, nullable=True),
        sa.Column("result_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint(f"status IN ({_STEP_STATUSES})", name=op.f("ck_mission_step_status")),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["mission.id"],
            name=op.f("fk_mission_step_mission_id_mission"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["mission_task.id"],
            name=op.f("fk_mission_step_task_id_mission_task"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mission_step")),
        sa.UniqueConstraint("task_id", "seq", name=op.f("uq_mission_step_task_id")),
    )
    ensure_index("ix_mission_step_mission_id", "mission_step", ["mission_id"])
    ensure_index("ix_mission_step_task_id", "mission_step", ["task_id"])
    ensure_table(
        "mission_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("data", _JSONB, server_default=_EMPTY_OBJECT, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["mission.id"],
            name=op.f("fk_mission_event_mission_id_mission"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mission_event")),
    )
    ensure_index("ix_mission_event_mission_id", "mission_event", ["mission_id"])
    ensure_table(
        "mission_fact",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(6), nullable=False),
        sa.Column("source_result_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')", name=op.f("ck_mission_fact_confidence")
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["mission.id"],
            name=op.f("fk_mission_fact_mission_id_mission"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mission_fact")),
    )
    ensure_index("ix_mission_fact_mission_id", "mission_fact", ["mission_id"])


def downgrade() -> None:
    for table in ("mission_fact", "mission_event", "mission_step", "mission_task", "mission"):
        drop_table_if_exists(table)

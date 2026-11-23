"""AI providers, their models, the default model per role and the usage ledger.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.db.ensure import drop_table_if_exists, ensure_index, ensure_table

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_NOW = sa.func.now()


def _stamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    ]


def upgrade() -> None:
    ensure_table(
        "ai_provider",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_stamps(),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("base_url", sa.String(300), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("api_key_last4", sa.String(4), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("monthly_budget_usd", sa.Numeric(14, 4), nullable=True),
        sa.Column("hard_stop", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('anthropic', 'openai', 'ollama-local', 'ollama-cloud')",
            name=op.f("ck_ai_provider_kind"),
        ),
        sa.CheckConstraint(
            "monthly_budget_usd IS NULL OR monthly_budget_usd >= 0",
            name=op.f("ck_ai_provider_budget"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_provider")),
        sa.UniqueConstraint("name", name=op.f("uq_ai_provider_name")),
    )
    ensure_table(
        "ai_model",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_stamps(),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("context_tokens", sa.BigInteger(), nullable=True),
        sa.Column("max_output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("capabilities", JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("price_input", sa.Numeric(14, 6), nullable=True),
        sa.Column("price_output", sa.Numeric(14, 6), nullable=True),
        sa.Column("price_cache_read", sa.Numeric(14, 6), nullable=True),
        sa.Column("price_cache_write", sa.Numeric(14, 6), nullable=True),
        sa.Column("price_cache_write_long", sa.Numeric(14, 6), nullable=True),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["ai_provider.id"],
            name=op.f("fk_ai_model_provider_id_ai_provider"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_model")),
        sa.UniqueConstraint("provider_id", "model_id", name=op.f("uq_ai_model_provider_id")),
    )
    ensure_index("ix_ai_model_provider_id", "ai_model", ["provider_id"])
    ensure_table(
        "ai_role_default",
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("model_ref", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_ref"],
            ["ai_model.id"],
            name=op.f("fk_ai_role_default_model_ref_ai_model"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role", name=op.f("pk_ai_role_default")),
    )
    ensure_table(
        "usage_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=True),
        sa.Column("provider_name", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("agent", sa.String(100), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_write_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_write_long_tokens", sa.BigInteger(), nullable=False),
        sa.Column("thinking_tokens", sa.BigInteger(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(18, 8), nullable=True),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["ai_provider.id"],
            name=op.f("fk_usage_ledger_provider_id_ai_provider"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_ledger")),
    )
    ensure_index("ix_usage_ledger_created_at", "usage_ledger", ["created_at"])
    ensure_index("ix_usage_ledger_provider_id", "usage_ledger", ["provider_id"])
    ensure_index("ix_usage_ledger_run_id", "usage_ledger", ["run_id"])


def downgrade() -> None:
    for name in ("usage_ledger", "ai_role_default", "ai_model", "ai_provider"):
        drop_table_if_exists(name)

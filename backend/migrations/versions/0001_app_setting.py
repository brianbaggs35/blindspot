"""The first table: settings the administrators can change.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.db.ensure import drop_table_if_exists, ensure_table

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    ensure_table(
        "app_setting",
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("key", name="pk_app_setting"),
    )


def downgrade() -> None:
    drop_table_if_exists("app_setting")

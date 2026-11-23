"""Which version of the terms of use each person accepted.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from app.db.ensure import drop_column_if_exists, ensure_column

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ensure_column("app_user", sa.Column("terms_version", sa.String(16), nullable=True))
    ensure_column(
        "app_user", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    drop_column_if_exists("app_user", "terms_accepted_at")
    drop_column_if_exists("app_user", "terms_version")

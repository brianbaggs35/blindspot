"""The declarative base and the columns most tables share.

Every table has a UUIDv7 primary key (random, but sorted by creation time, so new rows land at
the end of the index), `created_at` and `updated_at` in UTC, and, where it makes sense, a soft
delete marker and the id of the person who created the row.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.elements import ColumnElement

# Constraint and index names are made from the table and columns, so a migration can always
# name what it drops, and `alembic check` can tell a renamed constraint from a new one.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """The parent of every model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utc_now() -> datetime:
    """The current time, always with the UTC time zone. Times are stored in UTC only."""
    return datetime.now(UTC)


class UUIDPrimaryKey:
    """A UUIDv7 primary key, made in Python so a row has its id before it is flushed."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)


class Timestamps:
    """When the row was created and last changed."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )


class SoftDelete:
    """A row that is hidden rather than removed, so reports and the audit trail keep working."""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    @classmethod
    def not_deleted(cls) -> ColumnElement[bool]:
        """A filter that keeps only the rows that have not been deleted."""
        column: Any = cls.deleted_at
        return column.is_(None)

    def mark_deleted(self) -> None:
        """Hide the row from now on."""
        self.deleted_at = utc_now()

    def restore(self) -> None:
        """Bring a hidden row back."""
        self.deleted_at = None


class CreatedBy:
    """The user who created the row. Empty for rows the system made."""

    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)

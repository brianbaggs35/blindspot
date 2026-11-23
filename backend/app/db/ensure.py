"""Migration helpers that do nothing when the change is already there.

A migration that was applied halfway, or applied by hand, can be run again. Inside a migration,
use these instead of the plain `op` calls.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Inspector


def _inspector() -> Inspector:
    return sa.inspect(op.get_bind())


def ensure_table(name: str, *columns: sa.Column[Any] | sa.Constraint, **kwargs: Any) -> None:
    """Create the table unless it exists."""
    if not _inspector().has_table(name):
        op.create_table(name, *columns, **kwargs)


def ensure_column(table: str, column: sa.Column[Any]) -> None:
    """Add the column unless the table has it."""
    if column.name not in {existing["name"] for existing in _inspector().get_columns(table)}:
        op.add_column(table, column)


def ensure_index(name: str, table: str, columns: Sequence[str], *, unique: bool = False) -> None:
    """Create the index unless the table has one with this name."""
    if name not in {index["name"] for index in _inspector().get_indexes(table)}:
        op.create_index(name, table, list(columns), unique=unique)


def ensure_unique_constraint(name: str, table: str, columns: Sequence[str]) -> None:
    """Add the unique constraint unless the table has one with this name."""
    existing = {constraint["name"] for constraint in _inspector().get_unique_constraints(table)}
    if name not in existing:
        op.create_unique_constraint(name, table, list(columns))


def drop_column_if_exists(table: str, column: str) -> None:
    """Drop the column if the table has it."""
    inspector = _inspector()
    if inspector.has_table(table) and column in {c["name"] for c in inspector.get_columns(table)}:
        op.drop_column(table, column)


def drop_table_if_exists(name: str) -> None:
    """Drop the table if it exists."""
    if _inspector().has_table(name):
        op.drop_table(name)
